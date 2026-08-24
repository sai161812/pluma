"""pluma.brain.llama_cpp_adapter — llama.cpp planner adapter.

Spec §10: "Runtime baseline: llama.cpp launched locally through a replaceable adapter."
PLUMA_TECH_STACK.md: "Planner model: Qwen3-4B / Llama 3.2 3B GGUF Q4_K_M."
Boundary: Zero llama_cpp or ML libraries imported at module level.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence, Union

from pluma.brain.interface import (
    PlannerCancelledError,
    PlannerError,
    PlannerInterface,
    PlannerTimeoutError,
)
from pluma.brain.prompt_builder import PromptBuilder
from pluma.brain.schemas import Plan, RouteMode
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import ScreenSnapshot
from pluma.tools.registry import ToolRegistry, get_default_tool_registry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend Protocol for dependency injection
# ---------------------------------------------------------------------------

class LlamaCppBackend(Protocol):
    """Protocol for local LLM text generation backends."""

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.1,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> str:
        """Generate text completion from the local model."""
        ...


class _NativeLlamaCppBackend:
    """llama-cpp-python backend loaded lazily inside method bodies."""

    def __init__(self, model_path: str, n_ctx: int = 2048, n_threads: int = 4) -> None:
        self.model_path = model_path
        self.n_ctx = n_ctx
        self.n_threads = n_threads
        self._llm: Optional[Any] = None

    def load(self) -> None:
        """Load the GGUF model into memory via llama-cpp-python."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"LLM model file not found at '{self.model_path}'. "
                f"Configure brain.model_path with a valid GGUF file."
            )
        try:
            from llama_cpp import Llama  # type: ignore[import-not-found]
            self._llm = Llama(
                model_path=self.model_path,
                n_ctx=self.n_ctx,
                n_threads=self.n_threads,
                verbose=False,
            )
            logger.info("llama.cpp model loaded: %s", self.model_path)
        except ImportError:
            logger.error(
                "llama-cpp-python is not installed. Install it with: pip install llama-cpp-python"
            )
            raise

    def unload(self) -> None:
        """Release the model from memory."""
        self._llm = None
        logger.info("llama.cpp model unloaded from memory.")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.1,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> str:
        if self._llm is None:
            raise RuntimeError("llama.cpp model is not loaded. Call load() first.")

        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return str(response["choices"][0]["message"]["content"])


# ---------------------------------------------------------------------------
# LlamaCppAdapter
# ---------------------------------------------------------------------------

class LlamaCppAdapter(PlannerInterface):
    """Local planner adapter using llama.cpp with grammar/schema constrained generation.

    Complies with Spec §10:
    - Route-specific tool schema subsets.
    - Token-efficient sanitized prompt construction.
    - Strict second-pass validation before returning Plan.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        custom_backend: Optional[LlamaCppBackend] = None,
        registry: Optional[ToolRegistry] = None,
        prompt_builder: Optional[PromptBuilder] = None,
        validator: Optional[PlanValidator] = None,
        subset_selector: Optional[ToolSubsetSelector] = None,
    ) -> None:
        self.model_path = model_path
        self._backend = custom_backend
        self._native_backend: Optional[_NativeLlamaCppBackend] = None
        self._registry = registry or get_default_tool_registry()
        self._subset_selector = subset_selector or ToolSubsetSelector(self._registry)
        self._prompt_builder = prompt_builder or PromptBuilder(self._subset_selector)
        self._validator = validator or PlanValidator(self._registry)

    @property
    def is_loaded(self) -> bool:
        """Return True if model is loaded and ready."""
        if self._backend is not None:
            return True
        return self._native_backend is not None and self._native_backend._llm is not None

    def load(self) -> None:
        """Load the underlying model. No-op if custom backend injected."""
        if self._backend is not None:
            return
        if self._native_backend is None:
            if not self.model_path:
                raise ValueError("model_path must be configured to load native llama.cpp backend.")
            self._native_backend = _NativeLlamaCppBackend(self.model_path)
        self._native_backend.load()

    def unload(self) -> None:
        """Unload the underlying model to reclaim memory."""
        if self._backend is not None:
            return
        if self._native_backend is not None:
            self._native_backend.unload()
            self._native_backend = None

    def plan(
        self,
        command: str,
        context: Optional[Dict[str, Any]] = None,
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
        screen_snapshot: Optional[ScreenSnapshot] = None,
        prior_step_results: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional[CancellationToken] = None,
        route: Union[RouteMode, str] = RouteMode.SMART,
    ) -> Plan:
        """Translate command into a validated multi-step or single-step Plan."""
        if cancellation_token is not None:
            if cancellation_token.is_cancelled:
                raise PlannerCancelledError("Planning cancelled before model execution.")

        # 1. Resolve permitted tool schemas for the route if not explicitly supplied
        if permitted_tool_specs is None:
            permitted_tool_specs = self._subset_selector.select_schemas(
                route=route,
                registry=self._registry,
                command=command,
            )

        if not permitted_tool_specs:
            raise PlannerError(
                f"No tools permitted for route '{route}'. Cannot synthesize plan."
            )

        # 2. Build system and user prompts
        system_prompt = self._prompt_builder.build_system_prompt(permitted_tool_specs)
        user_prompt = self._prompt_builder.build_user_prompt(
            command=command,
            context=context,
            screen_snapshot=screen_snapshot,
            prior_step_results=prior_step_results,
        )

        active_backend = self._backend or self._native_backend
        if active_backend is None:
            raise PlannerError("LlamaCppAdapter is not loaded. Call load() first.")

        # 3. Generate structured response
        start_t = time.perf_counter()
        try:
            raw_output = active_backend.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                max_tokens=512,
                temperature=0.1,
                cancellation_token=cancellation_token,
            )
        except TaskCancelledError as cancel_err:
            raise PlannerCancelledError(f"Planning was cancelled: {cancel_err}") from cancel_err
        except Exception as exc:
            raise PlannerError(f"Model generation failed: {exc}") from exc

        duration_ms = (time.perf_counter() - start_t) * 1000.0
        logger.debug("Local planner generation completed in %.1f ms", duration_ms)

        # 4. Strict second-pass validation
        try:
            plan = self._validator.parse_and_validate_json(
                raw_text=raw_output,
                registry=self._registry,
            )
        except PlanValidationError as val_err:
            raise PlannerError(f"Planner output validation failed: {val_err}") from val_err

        return plan
