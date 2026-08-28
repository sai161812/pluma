"""pluma.core.orchestrator — Command lifecycle coordinator for all execution routes.

Spec §6 command lifecycle:
  1. Receive PlumaRequest (voice or text — same path).
  2. Create TaskCapsule via TaskSupervisor.
  3. Insert task record into ActivityLedger.
  4. Classify route via Router (FAST, SMART, SCREEN, DEEP).
  5. FAST: execute plan steps directly through ToolRegistry.
  6. SMART: local LLM planning + bounded multi-step execution.
  7. SCREEN: UIA/OCR perception + targeted interaction.
  8. DEEP: combined perception + local LLM planning + multi-step orchestration.
  9. Transition task state and update ActivityLedger.
 10. Return TaskExecutionResult.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.multi_step import (
    MultiStepExecutionResult,
    MultiStepOrchestrator,
    StepExecutionRecord,
)
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult, Router
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
from pluma.memory.redaction import redact_string
from pluma.rollback.engine import RollbackEngine
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolRegistry, register_default_tools

if TYPE_CHECKING:
    from pluma.brain.lifecycle import LlmLifecycleManager
    from pluma.perception.context import ActiveWindowContext
    from pluma.perception.uia_snapshot import UiaSnapshotBuilder

logger = logging.getLogger(__name__)


def _format_planning_error(exc: Exception, command: str) -> str:
    """Format an intelligent, user-friendly factual summary for failed planning."""
    msg = str(exc)
    cmd_preview = command[:40] if command else "empty command"
    if "not configured" in msg.lower() or "missing model" in msg.lower():
        return f"Cannot execute '{cmd_preview}': local planner model is not configured."
    if "at least one step" in msg.lower() or "empty plan" in msg.lower():
        return f"Cannot execute '{cmd_preview}': no actionable steps could be determined."
    if "unknown tool" in msg.lower() or "unsupported" in msg.lower() or "validation" in msg.lower():
        return f"Cannot execute '{cmd_preview}': no supported capability or tool available."
    return f"Cannot execute '{cmd_preview}': {msg}"


# ---------------------------------------------------------------------------
# TaskExecutionResult
# ---------------------------------------------------------------------------

@dataclass
class StepRecord:
    """Result of one plan step execution."""
    step_index: int
    tool: str
    result: ToolResult
    duration_ms: float


@dataclass
class TaskExecutionResult:
    """Full outcome of running one command through the orchestrator."""
    task_id: str
    request_id: str
    route: RouteMode
    route_reason: str
    final_state: str        # SUCCEEDED | FAILED | STOPPED | STOPPED_WITH_RESIDUAL | DEFERRED
    steps: List[StepRecord] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0
    factual_summary: str = ""
    replan_count: int = 0

    @property
    def success(self) -> bool:
        """True if the task reached a SUCCEEDED terminal state."""
        return self.final_state == "SUCCEEDED"

    @property
    def user_message(self) -> str:
        """User-visible factual response message."""
        return self.factual_summary or (self.error or "")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Coordinates the end-to-end lifecycle of a single PLUMA command across all 4 routes."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        supervisor: Optional[TaskSupervisor] = None,
        ledger: Optional[ActivityLedger] = None,
        router: Optional[Router] = None,
        multi_step_orchestrator: Optional[MultiStepOrchestrator] = None,
        llm_manager: Optional[Any] = None,
        rollback_engine: Optional[RollbackEngine] = None,
    ) -> None:
        self._registry = registry or _build_default_registry()
        self._supervisor = supervisor or TaskSupervisor(ledger=ledger, rollback_engine=rollback_engine)
        self._ledger = ledger
        self._router = router or Router()
        self._llm_manager = llm_manager
        self._rollback_engine = rollback_engine
        self._multi_step = multi_step_orchestrator or MultiStepOrchestrator(
            registry=self._registry,
            supervisor=self._supervisor,
            ledger=self._ledger,
            rollback_engine=self._rollback_engine,
            planner=self._llm_manager.adapter if self._llm_manager and hasattr(self._llm_manager, "adapter") else None,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, request: PlumaRequest, capsule: Optional[TaskCapsule] = None) -> TaskExecutionResult:
        """Execute *request* through the full command lifecycle across all routes."""
        wall_start = time.perf_counter()

        # 1. Use provided Task Capsule or create one
        if capsule is None:
            capsule = self._supervisor.create_task_capsule(request_id=request.request_id)
        task_id = capsule.task_id
        
        # Start the task immediately before any routing/planning/perception
        self._supervisor.start_task(task_id)
        if capsule.cancellation_token.is_cancelled:
            self._supervisor.stop_task(task_id)
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=RouteMode.FAST,
                route_reason="Cancelled before routing",
                final_state="STOPPED",
                error="Task was stopped before routing began.",
            )

        logger.info(
            "task=%s request=%s mode=%s text=%r",
            task_id, request.request_id, request.input_mode.value, redact_string(request.text[:120]),
        )

        # 2. Insert task record into Activity Ledger
        if self._ledger:
            try:
                self._ledger.insert_task(TaskRecord(
                    task_id=task_id,
                    request_id=request.request_id,
                    input_mode=request.input_mode.value,
                    command_text=request.text,
                    active_process=request.active_process,
                    active_window=request.active_window_title,
                ))
            except Exception as e:
                logger.error("Ledger insert_task failed: %s", e)

        # 3. Classify route
        route_result: RouteResult = self._router.route(request)
        logger.info("task=%s route=%s reason=%r", task_id, route_result.route.value, route_result.reason)

        if self._ledger:
            try:
                self._ledger.update_task(task_id, route=route_result.route.value)
            except Exception as e:
                logger.error("Ledger update_task (route) failed: %s", e)

        # 4. Route Dispatch
        if route_result.route == RouteMode.FAST:
            return self._execute_fast_route(capsule, request, route_result, wall_start)
        elif route_result.route == RouteMode.SMART:
            return self._execute_smart_route(capsule, request, route_result, wall_start)
        elif route_result.route == RouteMode.SCREEN:
            return self._execute_screen_route(capsule, request, route_result, wall_start)
        elif route_result.route == RouteMode.DEEP:
            return self._execute_deep_route(capsule, request, route_result, wall_start)
        else:
            return self._execute_fast_route(capsule, request, route_result, wall_start)

    # ------------------------------------------------------------------
    # Route Implementations
    # ------------------------------------------------------------------

    def _execute_fast_route(
        self,
        capsule: TaskCapsule,
        request: PlumaRequest,
        route_result: RouteResult,
        wall_start: float,
    ) -> TaskExecutionResult:
        """FAST route: Direct deterministic execution (zero-ML, zero-OCR)."""
        task_id = capsule.task_id
        plan = route_result.plan
        if plan is None or not plan.steps:
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=RouteMode.FAST,
                route_reason=route_result.reason,
                final_state="FAILED",
                error="FAST route produced no plan steps.",
                duration_ms=duration_ms,
            )

        steps_executed: List[StepRecord] = []
        final_state = "SUCCEEDED"
        last_error: Optional[str] = None
        last_message = ""

        for idx, step in enumerate(plan.steps):
            if capsule.cancellation_token.is_cancelled:
                final_state = "STOPPED"
                last_error = "Task was stopped before this step could run."
                break

            step_start = time.perf_counter()
            try:
                result = self._registry.execute(
                    tool_name=step.tool,
                    arguments=step.arguments,
                    task_context=capsule,
                    ledger=self._ledger,
                    step_index=idx,
                )
            except TaskCancelledError as e:
                final_state = "STOPPED"
                last_error = str(e)
                break
            except Exception as e:
                logger.exception("task=%s step=%d tool=%s unhandled error", task_id, idx, step.tool)
                result = ToolResult.failure(step.tool, f"Unhandled executor error: {e}")

            step_ms = (time.perf_counter() - step_start) * 1000.0
            steps_executed.append(StepRecord(
                step_index=idx,
                tool=step.tool,
                result=result,
                duration_ms=step_ms,
            ))

            if not result.ok:
                final_state = "FAILED"
                last_error = result.error
                break

            last_message = result.factual_message

        duration_ms = (time.perf_counter() - wall_start) * 1000.0

        if capsule.cancellation_token.is_cancelled:
            final_state = "STOPPED"
            if not last_error:
                last_error = "Task was stopped by user request."

        if final_state == "STOPPED":
            self._supervisor.stop_task(task_id)
        else:
            try:
                if final_state == "SUCCEEDED":
                    self._supervisor.mark_succeeded(task_id)
                else:
                    self._supervisor.mark_failed(task_id)
            except Exception:
                pass

        if self._ledger:
            try:
                self._ledger.update_task(
                    task_id,
                    final_state=final_state,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    stop_reason=capsule.cancellation_token.reason.value if capsule.cancellation_token.is_cancelled and capsule.cancellation_token.reason else None,
                    error_code="TOOL_FAILED" if final_state == "FAILED" else None,
                )
            except Exception as e:
                logger.error("Ledger update_task (final) failed: %s", e)

        summary = last_message if final_state == "SUCCEEDED" else (last_error or "Task completed.")
        return TaskExecutionResult(
            task_id=task_id,
            request_id=request.request_id,
            route=RouteMode.FAST,
            route_reason=route_result.reason,
            final_state=final_state,
            steps=steps_executed,
            error=last_error,
            duration_ms=duration_ms,
            factual_summary=summary,
        )

    def _execute_smart_route(
        self,
        capsule: TaskCapsule,
        request: PlumaRequest,
        route_result: RouteResult,
        wall_start: float,
    ) -> TaskExecutionResult:
        """SMART route: Local LLM planning + bounded multi-step execution."""
        task_id = capsule.task_id

        if self._llm_manager:
            llm = self._llm_manager
        else:
            from pluma.brain.lifecycle import get_default_llm_lifecycle_manager
            llm = get_default_llm_lifecycle_manager()

        context = {
            "active_process": request.active_process,
            "active_window_title": request.active_window_title,
        }

        # 1. Synthesize plan with local LLM
        try:
            plan = llm.plan(
                command=request.text,
                context=context,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.SMART,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            logger.error("Task %s: SMART route planning failed: %s", task_id, exc)
            self._supervisor.transition(task_id, TaskState.FAILED)
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=RouteMode.SMART,
                route_reason=route_result.reason,
                final_state="FAILED",
                error=f"Planning failed: {exc}",
                duration_ms=duration_ms,
                factual_summary=_format_planning_error(exc, request.text),
            )

        # 2. Execute bounded plan via MultiStepOrchestrator
        ms_res = self._multi_step.execute_plan(
            capsule=capsule,
            initial_plan=plan,
            command_text=request.text,
            context=context,
        )

        return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

    def _execute_screen_route(
        self,
        capsule: TaskCapsule,
        request: PlumaRequest,
        route_result: RouteResult,
        wall_start: float,
    ) -> TaskExecutionResult:
        """SCREEN route: UIA / OCR perception + targeted interaction."""
        task_id = capsule.task_id

        # If deterministic router already produced an unambiguous plan
        if route_result.plan and route_result.plan.steps:
            ms_res = self._multi_step.execute_plan(
                capsule=capsule,
                initial_plan=route_result.plan,
                command_text=request.text,
            )
            return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

        # Otherwise capture UIA snapshot and query planner
        snapshot = None
        try:
            from pluma.perception.context import ActiveWindowContext
            from pluma.perception.uia_snapshot import UiaSnapshotBuilder
            context_inspector = ActiveWindowContext()
            builder = UiaSnapshotBuilder(context=context_inspector)
            snapshot = builder.capture(ttl_seconds=3.0)
        except Exception as exc:
            logger.debug("Active window snapshot capture failed: %s", exc)

        if self._llm_manager:
            llm = self._llm_manager
        else:
            from pluma.brain.lifecycle import get_default_llm_lifecycle_manager
            llm = get_default_llm_lifecycle_manager()

        try:
            plan = llm.plan(
                command=request.text,
                screen_snapshot=snapshot,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.SCREEN,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            self._supervisor.transition(task_id, TaskState.FAILED)
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=RouteMode.SCREEN,
                route_reason=route_result.reason,
                final_state="FAILED",
                error=f"SCREEN planning failed: {exc}",
                duration_ms=duration_ms,
                factual_summary=_format_planning_error(exc, request.text),
            )

        ms_res = self._multi_step.execute_plan(
            capsule=capsule,
            initial_plan=plan,
            command_text=request.text,
        )
        return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

    def _execute_deep_route(
        self,
        capsule: TaskCapsule,
        request: PlumaRequest,
        route_result: RouteResult,
        wall_start: float,
    ) -> TaskExecutionResult:
        """DEEP route: UIA + OCR + Local LLM + Bounded Multi-Step Execution."""
        task_id = capsule.task_id

        # Capture snapshot with OCR fallback enabled
        snapshot = None
        try:
            from pluma.perception.context import ActiveWindowContext
            from pluma.perception.uia_snapshot import UiaSnapshotBuilder
            context_inspector = ActiveWindowContext()
            builder = UiaSnapshotBuilder(context=context_inspector)
            snapshot = builder.capture(ttl_seconds=5.0, include_ocr=True)
        except Exception as exc:
            logger.debug("DEEP route perception capture failed: %s", exc)

        if self._llm_manager:
            llm = self._llm_manager
        else:
            from pluma.brain.lifecycle import get_default_llm_lifecycle_manager
            llm = get_default_llm_lifecycle_manager()

        try:
            plan = llm.plan(
                command=request.text,
                screen_snapshot=snapshot,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.DEEP,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            self._supervisor.transition(task_id, TaskState.FAILED)
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=RouteMode.DEEP,
                route_reason=route_result.reason,
                final_state="FAILED",
                error=f"DEEP planning failed: {exc}",
                duration_ms=duration_ms,
                factual_summary=_format_planning_error(exc, request.text),
            )

        ms_res = self._multi_step.execute_plan(
            capsule=capsule,
            initial_plan=plan,
            command_text=request.text,
        )
        return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

    def _finalize_multi_step_result(
        self,
        capsule: TaskCapsule,
        request: PlumaRequest,
        route_result: RouteResult,
        ms_res: MultiStepExecutionResult,
        wall_start: float,
    ) -> TaskExecutionResult:
        """Convert MultiStepExecutionResult to TaskExecutionResult and update ledger."""
        duration_ms = (time.perf_counter() - wall_start) * 1000.0
        final_state_str = ms_res.final_state.value

        if self._ledger:
            try:
                self._ledger.update_task(
                    capsule.task_id,
                    final_state=final_state_str,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    stop_reason=capsule.cancellation_token.reason.value if capsule.cancellation_token.is_cancelled and capsule.cancellation_token.reason else None,
                    error_code="TOOL_FAILED" if final_state_str == "FAILED" else None,
                )
            except Exception as e:
                logger.error("Ledger update_task failed: %s", e)

        step_records = [
            StepRecord(
                step_index=s.step_index,
                tool=s.tool,
                result=s.result,
                duration_ms=s.duration_ms,
            )
            for s in ms_res.steps_executed
        ]

        return TaskExecutionResult(
            task_id=capsule.task_id,
            request_id=request.request_id,
            route=route_result.route,
            route_reason=route_result.reason,
            final_state=final_state_str,
            steps=step_records,
            error=ms_res.error,
            duration_ms=duration_ms,
            factual_summary=ms_res.factual_summary,
            replan_count=ms_res.replan_count,
        )


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: Optional[ToolRegistry] = None


def _build_default_registry() -> ToolRegistry:
    """Build and cache the default ToolRegistry with all standard tools registered."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        reg = ToolRegistry()
        register_default_tools(reg)
        _DEFAULT_REGISTRY = reg
    return _DEFAULT_REGISTRY
