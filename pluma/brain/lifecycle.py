"""pluma.brain.lifecycle — On-demand warm/cold lifecycle manager for local LLM planner.

Spec §4: "Zero-ML-at-idle law: LLM weights must not reside in memory during idle."
Spec §10, Appendix A: runtime.model_idle_unload_seconds = 30
"""

from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pluma.brain.interface import PlannerCancelledError, PlannerError
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter, LlamaCppBackend
from pluma.brain.schemas import Plan, RouteMode
from pluma.core.cancellation import CancellationToken
from pluma.perception.element_refs import ScreenSnapshot
from pluma.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MODEL_IDLE_UNLOAD_SECONDS: float = 30.0


class LlmLifecycleState(str, Enum):
    """Lifecycle states of the local LLM planner."""
    COLD = "COLD"           # Model not loaded; 0 MB VRAM/RAM consumed.
    LOADING = "LOADING"     # Model is being loaded into memory.
    WARM = "WARM"           # Model loaded, waiting for commands in grace period.
    GENERATING = "GENERATING"  # Inference actively running.
    UNLOADING = "UNLOADING" # Model being freed.


class LlmLifecycleManager:
    """Manages on-demand loading, warm grace periods, and automatic idle unloading of the LLM."""

    def __init__(
        self,
        adapter: Optional[LlamaCppAdapter] = None,
        model_path: Optional[str] = None,
        custom_backend: Optional[LlamaCppBackend] = None,
        registry: Optional[ToolRegistry] = None,
        idle_unload_seconds: float = DEFAULT_MODEL_IDLE_UNLOAD_SECONDS,
    ) -> None:
        self.adapter = adapter or LlamaCppAdapter(
            model_path=model_path,
            custom_backend=custom_backend,
            registry=registry,
        )
        self.idle_unload_seconds = idle_unload_seconds
        self._state = LlmLifecycleState.COLD
        self._lock = threading.Lock()
        self._idle_timer: Optional[threading.Timer] = None

    @property
    def state(self) -> LlmLifecycleState:
        with self._lock:
            return self._state

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
        """Ensure model is warm and execute planning under lifecycle guard."""
        if cancellation_token is not None and cancellation_token.is_cancelled:
            raise PlannerCancelledError("Planning cancelled before model warm-up.")

        self._ensure_warm()

        with self._lock:
            self._cancel_idle_timer()
            self._state = LlmLifecycleState.GENERATING

        try:
            plan = self.adapter.plan(
                command=command,
                context=context,
                permitted_tool_specs=permitted_tool_specs,
                screen_snapshot=screen_snapshot,
                prior_step_results=prior_step_results,
                cancellation_token=cancellation_token,
                route=route,
            )
            return plan
        finally:
            with self._lock:
                if self._state == LlmLifecycleState.GENERATING:
                    self._state = LlmLifecycleState.WARM
                    self._schedule_idle_unload()

    def shutdown(self) -> None:
        """Immediately unload LLM and stop background timers."""
        with self._lock:
            self._cancel_idle_timer()
            if self._state in (LlmLifecycleState.WARM, LlmLifecycleState.GENERATING):
                self._state = LlmLifecycleState.UNLOADING

        try:
            self.adapter.unload()
        except Exception as exc:
            logger.debug("Error during LLM adapter unload: %s", exc)

        with self._lock:
            self._state = LlmLifecycleState.COLD
        logger.info("LlmLifecycleManager: shutdown complete (COLD).")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_warm(self) -> None:
        """Load model into memory if currently cold."""
        with self._lock:
            if self._state == LlmLifecycleState.WARM:
                return
            if self._state == LlmLifecycleState.GENERATING:
                return
            if self._state == LlmLifecycleState.LOADING:
                raise RuntimeError("LLM is already loading.")
            self._state = LlmLifecycleState.LOADING

        logger.info("LlmLifecycleManager: loading LLM model (COLD -> WARM).")
        try:
            self.adapter.load()
        except Exception as exc:
            with self._lock:
                self._state = LlmLifecycleState.COLD
            raise RuntimeError(f"Failed to load LLM model: {exc}") from exc

        with self._lock:
            self._state = LlmLifecycleState.WARM
        logger.info("LlmLifecycleManager: LLM model warm and ready.")

    def _schedule_idle_unload(self) -> None:
        """Schedule automatic unload after idle_unload_seconds."""
        if self.idle_unload_seconds > 0:
            self._idle_timer = threading.Timer(
                self.idle_unload_seconds,
                self._idle_unload_callback,
            )
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_unload_callback(self) -> None:
        with self._lock:
            if self._state != LlmLifecycleState.WARM:
                return
            self._state = LlmLifecycleState.UNLOADING

        logger.info(
            "LlmLifecycleManager: idle timeout (%.1fs) reached — unloading model.",
            self.idle_unload_seconds,
        )
        try:
            self.adapter.unload()
        except Exception as exc:
            logger.debug("Error during idle unload: %s", exc)

        with self._lock:
            self._state = LlmLifecycleState.COLD
        logger.info("LlmLifecycleManager: LLM model unloaded (COLD).")

    def shutdown(self) -> None:
        """Immediately unload the LLM model and cancel any pending idle timer."""
        self._cancel_idle_timer()
        with self._lock:
            if self._state in (LlmLifecycleState.WARM, LlmLifecycleState.GENERATING):
                self._state = LlmLifecycleState.UNLOADING
        try:
            self.adapter.unload()
        except Exception as exc:
            logger.debug("Error during shutdown: %s", exc)
        with self._lock:
            self._state = LlmLifecycleState.COLD
        logger.info("LlmLifecycleManager: shutdown complete (COLD).")

    # Alias for uniform lifecycle interface
    unload = shutdown


# ---------------------------------------------------------------------------
# Process-wide Default Instance
# ---------------------------------------------------------------------------

_default_llm_manager: Optional[LlmLifecycleManager] = None
_default_llm_manager_lock = threading.Lock()


def get_default_llm_lifecycle_manager() -> LlmLifecycleManager:
    """Get or create the process-wide default LLM lifecycle manager."""
    global _default_llm_manager
    with _default_llm_manager_lock:
        if _default_llm_manager is None:
            _default_llm_manager = LlmLifecycleManager()
        return _default_llm_manager


def set_default_llm_lifecycle_manager(manager: Optional[LlmLifecycleManager]) -> None:
    """Override or reset the process-wide default LLM lifecycle manager."""
    global _default_llm_manager
    with _default_llm_manager_lock:
        if _default_llm_manager is not None and _default_llm_manager is not manager:
            _default_llm_manager.shutdown()
        _default_llm_manager = manager
