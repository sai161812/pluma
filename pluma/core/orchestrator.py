"""pluma.core.orchestrator — Command lifecycle coordinator.

Spec §6 command lifecycle for the FAST route:
  1. Receive PlumaRequest (voice or text — same path).
  2. Create TaskCapsule via TaskSupervisor.
  3. Insert task record into ActivityLedger.
  4. Classify route via Router.
  5. For FAST: execute plan steps through ToolRegistry (validate → undo-capture
     → execute → verify → ledger-record) while checking the cancellation latch
     before each step.
  6. Transition task state (RUNNING → SUCCEEDED / FAILED / STOPPED).
  7. Update ActivityLedger with final task state and timing.
  8. Return TaskExecutionResult.

For non-FAST routes the orchestrator records the routing decision and returns
a result indicating the route class; higher-level phases will handle SCREEN /
SMART / DEEP execution.

No ML, OCR, or screen-capture code is used here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pluma.brain.schemas import RouteMode
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult, Router
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolRegistry, register_default_tools

logger = logging.getLogger(__name__)


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
    final_state: str        # SUCCEEDED | FAILED | STOPPED | DEFERRED
    steps: List[StepRecord] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: float = 0.0
    factual_summary: str = ""


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Coordinates the end-to-end lifecycle of a single PLUMA command.

    Phase 3 implements the FAST route path (zero-ML, zero-OCR, zero-screen-scan).
    Non-FAST routes return DEFERRED results; later phases will implement them.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        supervisor: Optional[TaskSupervisor] = None,
        ledger: Optional[ActivityLedger] = None,
        router: Optional[Router] = None,
    ) -> None:
        self._registry = registry or _build_default_registry()
        self._supervisor = supervisor or TaskSupervisor()
        self._ledger = ledger
        self._router = router or Router()

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(self, request: PlumaRequest) -> TaskExecutionResult:
        """Execute *request* through the full command lifecycle.

        Thread-safe: each call creates its own TaskCapsule and returns
        when the task has reached a terminal state.
        """
        wall_start = time.perf_counter()

        # 1. Create Task Capsule
        capsule = self._supervisor.create_task(request.request_id)
        task_id = capsule.task_id
        logger.info(
            "task=%s request=%s mode=%s text=%r",
            task_id, request.request_id, request.input_mode.value, request.text[:120],
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

        # Update ledger with route
        if self._ledger:
            try:
                self._ledger.update_task(task_id, route=route_result.route.value)
            except Exception as e:
                logger.error("Ledger update_task (route) failed: %s", e)

        # 4. Non-FAST routes: defer (later phases implement SCREEN/SMART/DEEP)
        if route_result.route != RouteMode.FAST:
            duration_ms = (time.perf_counter() - wall_start) * 1000.0
            if self._ledger:
                try:
                    self._ledger.update_task(task_id, final_state="DEFERRED")
                except Exception:
                    pass
            return TaskExecutionResult(
                task_id=task_id,
                request_id=request.request_id,
                route=route_result.route,
                route_reason=route_result.reason,
                final_state="DEFERRED",
                factual_summary=f"Routed to {route_result.route.value} (not yet implemented in Phase 3).",
                duration_ms=duration_ms,
            )

        # 5. FAST route: execute the plan
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

        self._supervisor.start_task(task_id)
        steps_executed: List[StepRecord] = []
        final_state = "SUCCEEDED"
        last_error: Optional[str] = None
        last_message = ""

        for idx, step in enumerate(plan.steps):
            # Check STOP latch before every step
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

        # 6. Finalise task state
        duration_ms = (time.perf_counter() - wall_start) * 1000.0

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

        # Update ledger final state
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
        logger.info(
            "task=%s final_state=%s duration_ms=%.1f summary=%r",
            task_id, final_state, duration_ms, summary,
        )

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


# ---------------------------------------------------------------------------
# Default registry factory (cached lazily)
# ---------------------------------------------------------------------------

_DEFAULT_REGISTRY: Optional[ToolRegistry] = None


def _build_default_registry() -> ToolRegistry:
    """Build and cache the default ToolRegistry with all 19+ tools registered."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        reg = ToolRegistry()
        register_default_tools(reg)
        _DEFAULT_REGISTRY = reg
    return _DEFAULT_REGISTRY
