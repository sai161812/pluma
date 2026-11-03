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
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolRegistry, WorkerResponse, get_default_tool_registry

logger = logging.getLogger(__name__)

# Keep planner STOP responsive while waiting on the owned inference future.
_INFERENCE_WAIT_POLL_S = 0.025
DEFAULT_INFERENCE_TIMEOUT_S = 60.0
DEFAULT_PLANNER_TEMPERATURE = 0.0


def _planner_generation_schema(max_steps: int) -> Dict[str, Any]:
    """Return the Plan contract with fields needed for strict generation required."""
    schema = Plan.model_json_schema()
    plan_required = set(schema.get("required", []))
    plan_required.update({"mode", "steps"})
    schema["required"] = sorted(plan_required)
    steps = schema.get("properties", {}).get("steps")
    if isinstance(steps, dict):
        steps["maxItems"] = max_steps
    tool_call = schema.get("$defs", {}).get("ToolCall")
    if isinstance(tool_call, dict):
        call_required = set(tool_call.get("required", []))
        call_required.add("arguments")
        tool_call["required"] = sorted(call_required)
    return schema


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
        temperature: float = DEFAULT_PLANNER_TEMPERATURE,
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
        import gc
        gc.collect()
        logger.info("llama.cpp model unloaded from memory.")

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = DEFAULT_PLANNER_TEMPERATURE,
        cancellation_token: Optional[CancellationToken] = None,
        max_plan_steps: int = 8,
    ) -> str:
        if self._llm is None:
            raise RuntimeError("llama.cpp model is not loaded. Call load() first.")

        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response_format = {
            "type": "json_object",
            "schema": _planner_generation_schema(max_plan_steps),
        }
        response = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            response_format=response_format,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("llama.cpp returned no structured planner response.") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llama.cpp returned no structured planner response.")
        return content


def _native_planner_executor(arguments: Dict[str, Any], _task_context: Any) -> ToolResult:
    """Load, run and release one native generation inside its task-owned worker."""
    backend = _NativeLlamaCppBackend(arguments["model_path"])
    raw_output: Optional[str] = None
    try:
        backend.load()
        raw_output = backend.generate(
            prompt=arguments["prompt"],
            system_prompt=arguments["system_prompt"],
            max_tokens=arguments["max_tokens"],
            temperature=arguments["temperature"],
            max_plan_steps=arguments["max_plan_steps"],
        )
    finally:
        backend.unload()

    if backend._llm is not None or raw_output is None:
        return ToolResult.failure(
            "planner_inference",
            "Native planner runtime cleanup was not verified.",
            error_code="PLANNER_CLEANUP_UNVERIFIED",
        )
    return ToolResult.success(
        "planner_inference",
        data={"raw_output": raw_output, "runtime_unloaded": True},
        factual_message="Native planner generation finished and its model reference was released.",
        verified=False,
    )


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
        inference_timeout_s: float = DEFAULT_INFERENCE_TIMEOUT_S,
        max_plan_steps: int = 8,
    ) -> None:
        self.model_path = model_path
        self._backend = custom_backend
        self._native_backend: Optional[_NativeLlamaCppBackend] = None
        self._registry = registry or get_default_tool_registry()
        self._subset_selector = subset_selector or ToolSubsetSelector(self._registry)
        self._prompt_builder = prompt_builder or PromptBuilder(self._subset_selector)
        self.max_plan_steps = max_plan_steps
        self._validator = validator or PlanValidator(self._registry, max_steps=max_plan_steps)
        self.inference_timeout_s = inference_timeout_s

    @property
    def is_loaded(self) -> bool:
        """Return True if model is loaded and ready."""
        if self._backend is not None:
            return True
        return self._native_backend is not None and self._native_backend._llm is not None

    @property
    def uses_task_owned_native_runtime(self) -> bool:
        return self._backend is None

    def load(self) -> None:
        """Load the underlying model. No-op if custom backend injected."""
        if self._backend is not None:
            return
        if self._native_backend is None:
            if not self.model_path:
                raise ValueError("model_path must be configured to load native llama.cpp backend.")
            self._native_backend = _NativeLlamaCppBackend(self.model_path)
        # Native weights are loaded only in the task-owned worker, never in
        # PLUMA's resident process.
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(
                "Configured planner model file is unavailable. Set brain.model_path to a GGUF file."
            )

    def get_permitted_tool_specs(
        self,
        command: str,
        route: Union[RouteMode, str],
    ) -> List[Dict[str, Any]]:
        """Return the same route-scoped schemas used by generation and replan."""
        return self._subset_selector.select_schemas(
            route=route,
            registry=self._registry,
            command=command,
        )

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
            permitted_tool_specs = self.get_permitted_tool_specs(command, route)

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

        # 3. Generate structured response with hard inference timeout
        start_t = time.perf_counter()
        try:
            if self._backend is None:
                raw_output = self._generate_task_owned_native(
                    user_prompt=user_prompt,
                    system_prompt=system_prompt,
                    cancellation_token=cancellation_token,
                )
            else:
                import concurrent.futures

                future = self._registry.submit_owned(
                    active_backend.generate,
                    command_class="planner_inference",
                    task_id=getattr(cancellation_token, "task_id", None),
                    _task_context=getattr(cancellation_token, "_capsule", lambda: None)(),
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    max_tokens=512,
                    temperature=DEFAULT_PLANNER_TEMPERATURE,
                    cancellation_token=cancellation_token,
                )
                deadline = start_t + max(0.0, self.inference_timeout_s)
                while True:
                    if cancellation_token is not None:
                        try:
                            cancellation_token.raise_if_cancelled(
                                "Planning was stopped during model inference.")
                        except TaskCancelledError:
                            future.cancel()
                            raise
                    remaining = deadline - time.perf_counter()
                    if remaining <= 0:
                        if future.done():
                            raw_output = future.result()
                            break
                        future.cancel()
                        raise PlannerTimeoutError(
                            f"LLM planning inference timed out after {self.inference_timeout_s:.1f}s."
                        )
                    try:
                        raw_output = future.result(timeout=min(_INFERENCE_WAIT_POLL_S, remaining))
                        break
                    except concurrent.futures.TimeoutError:
                        if future.done():
                            raw_output = future.result()
                            break
                        continue
        except PlannerTimeoutError:
            raise
        except PlannerError:
            raise
        except TaskCancelledError as cancel_err:
            raise PlannerCancelledError(f"Planning was cancelled: {cancel_err}") from cancel_err
        except Exception as exc:
            if self._backend is None:
                raise PlannerError("Native model generation failed or its worker stopped.") from None
            raise PlannerError(f"Model generation failed: {exc}") from exc

        if cancellation_token is not None:
            try:
                cancellation_token.raise_if_cancelled("Planning was stopped before plan validation.")
            except TaskCancelledError as cancel_err:
                raise PlannerCancelledError(f"Planning was cancelled: {cancel_err}") from cancel_err

        duration_ms = (time.perf_counter() - start_t) * 1000.0
        logger.debug("Local planner generation completed in %.1f ms", duration_ms)

        # 4. Strict second-pass validation
        try:
            plan = self._validator.parse_and_validate_json(
                raw_text=raw_output,
                registry=self._registry,
                permitted_tool_specs=permitted_tool_specs,
                max_steps=self.max_plan_steps,
            )
        except PlanValidationError as val_err:
            raise PlannerError(f"Planner output validation failed: {val_err}") from val_err

        if cancellation_token is not None:
            try:
                cancellation_token.raise_if_cancelled("Planning was stopped before returning a plan.")
            except TaskCancelledError as cancel_err:
                raise PlannerCancelledError(f"Planning was cancelled: {cancel_err}") from cancel_err

        return plan

    def _generate_task_owned_native(
        self,
        *,
        user_prompt: str,
        system_prompt: str,
        cancellation_token: Optional[CancellationToken],
    ) -> str:
        if cancellation_token is None:
            raise PlannerError("Native planner inference requires an owned task capsule.")
        cancellation_token.raise_if_cancelled("Planning was stopped before native worker admission.")
        task_id = getattr(cancellation_token, "task_id", None)
        capsule_ref = getattr(cancellation_token, "_capsule", None)
        capsule = capsule_ref() if callable(capsule_ref) else None
        if capsule is None or not task_id or capsule.task_id != task_id:
            raise PlannerError("Native planner inference requires its matching task capsule.")
        if self._native_backend is None or self.model_path is None:
            raise PlannerError("Native planner model is not configured.")

        from pluma.tools.registry import WorkerRequest

        controller = self._registry.get_worker(task_id)
        capsule.worker_controller = controller
        capsule.tool_registry = self._registry
        request = WorkerRequest(
            task_id=task_id,
            tool_name="planner_inference",
            validated_args={
                "model_path": self.model_path,
                "prompt": user_prompt,
                "system_prompt": system_prompt,
                "max_tokens": 512,
                "temperature": DEFAULT_PLANNER_TEMPERATURE,
                "max_plan_steps": self.max_plan_steps,
            },
            timeout_s=self.inference_timeout_s,
            supervisor_pid=os.getpid(),
        )
        status, payload = controller.execute_call(
            _native_planner_executor,
            request.validated_args,
            request,
            timeout_s=self.inference_timeout_s,
            job_object=getattr(capsule, "job_object", None),
            cancellation_token=cancellation_token,
        )
        if status == "timeout":
            raise PlannerTimeoutError(
                f"LLM planning inference timed out after {self.inference_timeout_s:.1f}s."
            )
        if status == "cancelled" or cancellation_token.is_cancelled:
            raise PlannerCancelledError("Planning was cancelled during native inference.")
        if status != "ok" or not isinstance(payload, WorkerResponse):
            raise PlannerError("Native planner worker failed before returning a result.")
        result = payload.result
        if (not result.ok or result.data.get("runtime_unloaded") is not True
                or not isinstance(result.data.get("raw_output"), str)):
            raise PlannerError("Native planner generation or runtime cleanup failed.")
        return result.data["raw_output"]
