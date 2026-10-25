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
from pluma.core.task_supervisor import InvalidTaskTransition, TaskCapsule, TaskState, TaskSupervisor
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
    completion_verified: bool = True
    terminal_persisted: Optional[bool] = None
    has_residual: bool = False
    rollback_performed: bool = False
    rollback_success: Optional[bool] = None
    cleanup_evidence: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """True if the task reached a SUCCEEDED terminal state."""
        return self.final_state == "SUCCEEDED" and self.completion_verified

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
        binder = getattr(self._registry, "bind_stop_service", None)
        if callable(binder):
            binder(self._supervisor.request_stop)
        self._ledger = ledger
        self._supervisor.bind_execution(ledger, rollback_engine)
        self._router = router or Router()
        self._llm_manager = llm_manager
        self._rollback_engine = rollback_engine
        self._multi_step = multi_step_orchestrator or MultiStepOrchestrator(
            registry=self._registry,
            supervisor=self._supervisor,
            ledger=self._ledger,
            rollback_engine=self._rollback_engine,
            planner=self._llm_manager if self._llm_manager and hasattr(self._llm_manager, "plan") else None,
        )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, request: PlumaRequest, capsule: Optional[TaskCapsule] = None) -> TaskExecutionResult:
        """Execute *request* through the full command lifecycle across all routes."""
        with self._supervisor.execution_gate.enter():
            return self._execute_request(request, capsule)

    def _execute_request(self, request: PlumaRequest, capsule: Optional[TaskCapsule] = None) -> TaskExecutionResult:
        wall_start = time.perf_counter()

        # 1. Use provided Task Capsule or create one
        if capsule is None:
            capsule = self._supervisor.create_task_capsule(request_id=request.request_id)
        task_id = capsule.task_id
        
        logger.info(
            "task=%s request=%s mode=%s text=%r",
            task_id, request.request_id, request.input_mode.value, redact_string(request.text[:120]),
        )

        capsule.history_expected = True
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

        # Persist the real request before cancellation can finalize its history.
        try:
            self._supervisor.start_task(task_id)
        except (TaskCancelledError, InvalidTaskTransition):
            if not capsule.cancellation_token.is_cancelled:
                raise
            self._supervisor.stop_task(task_id)
            return self._project_result(capsule, TaskExecutionResult(
                task_id=task_id, request_id=request.request_id, route=RouteMode.FAST,
                route_reason="Cancelled before routing", final_state="STOPPED",
                error="Task was stopped before routing began.",
            ))

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
            return self._project_result(capsule, self._execute_fast_route(capsule, request, route_result, wall_start))
        elif route_result.route == RouteMode.SMART:
            return self._project_result(capsule, self._execute_smart_route(capsule, request, route_result, wall_start))
        elif route_result.route == RouteMode.SCREEN:
            return self._project_result(capsule, self._execute_screen_route(capsule, request, route_result, wall_start))
        elif route_result.route == RouteMode.DEEP:
            return self._project_result(capsule, self._execute_deep_route(capsule, request, route_result, wall_start))
        else:
            return self._project_result(capsule, self._execute_fast_route(capsule, request, route_result, wall_start))

    def _project_result(self, capsule: TaskCapsule, result: TaskExecutionResult) -> TaskExecutionResult:
        requested = TaskState(result.final_state)
        if requested in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL):
            from pluma.core.cancellation import StopReason
            timed_out = capsule.cancellation_token.reason == StopReason.TASK_TIMEOUT
            # A broken worker seals native admission without a user request.
            # Route that internal fence through failure cleanup, not user STOP.
            internal_failure = capsule.cancellation_token.reason in (None, StopReason.INTERNAL_ERROR)
            if timed_out or internal_failure:
                self._supervisor.fail_task_with_rollback(capsule.task_id)
            else:
                self._supervisor.stop_task(capsule.task_id)
        if requested == TaskState.FAILED and not capsule.terminal_ready.is_set():
            self._supervisor.fail_task_with_rollback(capsule.task_id)
        if requested in (TaskState.SUCCEEDED, TaskState.FAILED, TaskState.STOPPED,
                          TaskState.STOPPED_WITH_RESIDUAL, TaskState.ABORTED_BY_CRASH):
            self._supervisor.finalize_task(capsule.task_id, requested)
        original_state = result.final_state
        for key, value in capsule.outcome_details().items():
            setattr(result, key, value)
        if (original_state != result.final_state or result.final_state.startswith("STOPPED")
                or not result.completion_verified):
            result.factual_summary = capsule.terminal_summary()
        if result.terminal_persisted is False:
            result.factual_summary = capsule.terminal_summary() + " Task history could not be verified."
        return result

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

        permitted_tool_specs = self._permitted_planner_tools(llm, request.text, RouteMode.SMART)

        context = {
            "active_process": request.active_process,
            "active_window_title": request.active_window_title,
        }

        # 1. Synthesize plan with local LLM
        try:
            plan = llm.plan(
                command=request.text,
                context=context,
                permitted_tool_specs=permitted_tool_specs,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.SMART,
            )
        except Exception as exc:
            stopped = self._planning_stop_result(capsule, request, route_result, wall_start)
            if stopped is not None:
                return stopped
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            logger.error("Task %s: SMART route planning failed: %s", task_id, exc)
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
            permitted_tool_specs=permitted_tool_specs,
            route=RouteMode.SMART,
        )

        return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

    def _capture_semantic_context(self, capsule: TaskCapsule):
        """Observe through the registered, owned UIA tool; OCR remains on demand."""
        token = capsule.cancellation_token
        if token.is_cancelled:
            return None, ToolResult.failure("inspect_window_controls", "Task stopped before screen inspection.", "TASK_CANCELLED")
        try:
            result = self._registry.execute("inspect_window_controls", {"max_controls": 50},
                task_context=capsule, ledger=self._ledger)
            if token.is_cancelled:
                return None, ToolResult.failure("inspect_window_controls", "Task stopped during screen inspection.", "TASK_CANCELLED")
            if not result.ok or not result.verified:
                return None, result
            snapshot = capsule.snapshot_registry.resolve(result.data["snapshot_id"])
            return snapshot, None
        except TaskCancelledError:
            return None, ToolResult.failure("inspect_window_controls", "Task stopped during screen inspection.", "TASK_CANCELLED")
        except Exception:
            return None, ToolResult.failure("inspect_window_controls", "A verified task-owned screen observation is unavailable.", "SCREEN_OBSERVATION_FAILED")

    @staticmethod
    def _screen_observation_failure(capsule, request, route_result, wall_start, error):
        return TaskExecutionResult(task_id=capsule.task_id, request_id=request.request_id,
            route=route_result.route, route_reason=route_result.reason,
            final_state="STOPPED" if capsule.cancellation_token.is_cancelled else "FAILED",
            error=error.factual_message, factual_summary=error.factual_message,
            duration_ms=(time.perf_counter() - wall_start) * 1000.0)

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
            permitted_tool_specs = None
            if self._multi_step.planner is not None:
                planner = self._llm_manager or self._multi_step.planner
                permitted_tool_specs = self._permitted_planner_tools(
                    planner, request.text, RouteMode.SCREEN
                )
            ms_res = self._multi_step.execute_plan(
                capsule=capsule,
                initial_plan=route_result.plan,
                command_text=request.text,
                permitted_tool_specs=permitted_tool_specs,
                route=RouteMode.SCREEN,
            )
            return self._finalize_multi_step_result(capsule, request, route_result, ms_res, wall_start)

        snapshot, perception_error = self._capture_semantic_context(capsule)
        if perception_error is not None:
            return self._screen_observation_failure(capsule, request, route_result, wall_start, perception_error)

        if self._llm_manager:
            llm = self._llm_manager
        else:
            from pluma.brain.lifecycle import get_default_llm_lifecycle_manager
            llm = get_default_llm_lifecycle_manager()

        permitted_tool_specs = self._permitted_planner_tools(llm, request.text, RouteMode.SCREEN)

        try:
            plan = llm.plan(
                command=request.text,
                permitted_tool_specs=permitted_tool_specs,
                screen_snapshot=snapshot,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.SCREEN,
            )
        except Exception as exc:
            stopped = self._planning_stop_result(capsule, request, route_result, wall_start)
            if stopped is not None:
                return stopped
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
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
            permitted_tool_specs=permitted_tool_specs,
            route=RouteMode.SCREEN,
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

        snapshot, perception_error = self._capture_semantic_context(capsule)
        if perception_error is not None:
            return self._screen_observation_failure(capsule, request, route_result, wall_start, perception_error)

        if self._llm_manager:
            llm = self._llm_manager
        else:
            from pluma.brain.lifecycle import get_default_llm_lifecycle_manager
            llm = get_default_llm_lifecycle_manager()

        permitted_tool_specs = self._permitted_planner_tools(llm, request.text, RouteMode.DEEP)

        try:
            plan = llm.plan(
                command=request.text,
                permitted_tool_specs=permitted_tool_specs,
                screen_snapshot=snapshot,
                cancellation_token=capsule.cancellation_token,
                route=RouteMode.DEEP,
            )
        except Exception as exc:
            stopped = self._planning_stop_result(capsule, request, route_result, wall_start)
            if stopped is not None:
                return stopped
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
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
            permitted_tool_specs=permitted_tool_specs,
            route=RouteMode.DEEP,
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

    @staticmethod
    def _permitted_planner_tools(llm: Any, command: str, route: RouteMode):
        """Resolve one route-specific whitelist for initial planning and replans."""
        adapter = getattr(llm, "adapter", llm)
        resolver = getattr(adapter, "get_permitted_tool_specs", None)
        return resolver(command, route) if callable(resolver) else None

    @staticmethod
    def _planning_stop_result(capsule, request, route_result, wall_start):
        """Keep a latched user STOP distinct from a planner failure."""
        if (not capsule.cancellation_token.is_cancelled
                or capsule.cancellation_token.reason != StopReason.USER_STOP):
            return None
        return TaskExecutionResult(
            task_id=capsule.task_id,
            request_id=request.request_id,
            route=route_result.route,
            route_reason=route_result.reason,
            final_state="STOPPED",
            error="Planning stopped by user request.",
            duration_ms=(time.perf_counter() - wall_start) * 1000.0,
            factual_summary="Task stopped during planning.",
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
