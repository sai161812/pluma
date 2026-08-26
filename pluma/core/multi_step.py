"""pluma.core.multi_step — Bounded multi-step task execution coordinator.

Spec §6, §10, §12:
- Execute -> Observe -> Replan loop.
- Stop-latch evaluated before every step and before every replan.
- Bounded replanning limit (replan count <= max_replans, default 3).
- Reverse rollback on failure or abort with residual changes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from pluma.brain.interface import PlannerCancelledError, PlannerError, PlannerInterface
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskStep, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, UndoRecord
from pluma.rollback.engine import RollbackEngine
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.base import RiskClass, ToolResult
from pluma.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_MAX_REPLANS: int = 3
HARD_CAP_MAX_REPLANS: int = 5
MAX_LIFETIME_STEPS: int = 20


@dataclass
class StepExecutionRecord:
    """Record of a single step execution within a multi-step plan."""
    step_index: int
    tool: str
    arguments: Dict[str, Any]
    purpose: str
    result: ToolResult
    duration_ms: float
    replan_iteration: int = 0


@dataclass
class MultiStepExecutionResult:
    """Outcome of running a multi-step plan through the coordinator."""
    task_id: str
    final_state: TaskState
    steps_executed: List[StepExecutionRecord] = field(default_factory=list)
    replan_count: int = 0
    error: Optional[str] = None
    duration_ms: float = 0.0
    factual_summary: str = ""
    rollback_performed: bool = False
    rollback_success: bool = True


class MultiStepOrchestrator:
    """Coordinates bounded sequential execution, per-step verification, and replanning."""

    def __init__(
        self,
        registry: ToolRegistry,
        supervisor: TaskSupervisor,
        ledger: Optional[ActivityLedger] = None,
        rollback_engine: Optional[RollbackEngine] = None,
        planner: Optional[PlannerInterface] = None,
        policy_engine: Optional[Any] = None,
        max_replans: int = DEFAULT_MAX_REPLANS,
    ) -> None:
        self.registry = registry
        self.supervisor = supervisor
        self.ledger = ledger
        self.rollback_engine = rollback_engine or RollbackEngine(
            ledger=ledger,
        )
        self.planner = planner
        self.policy_engine = policy_engine
        self.max_replans = min(max_replans, HARD_CAP_MAX_REPLANS)

    def execute_plan(
        self,
        capsule: TaskCapsule,
        initial_plan: Plan,
        command_text: str,
        context: Optional[Dict[str, Any]] = None,
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
    ) -> MultiStepExecutionResult:
        """Execute a multi-step Plan with per-step observation, stop-latch checks, and replanning."""
        start_time = time.perf_counter()
        task_id = capsule.task_id
        token = capsule.cancellation_token

        # Transition to RUNNING
        if capsule.state == TaskState.CREATED:
            self.supervisor.transition(task_id, TaskState.RUNNING)

        executed_records: List[StepExecutionRecord] = []
        prior_results_for_replan: List[Dict[str, Any]] = []
        current_plan = initial_plan
        replan_count = 0
        overall_error: Optional[str] = None

        while True:
            plan_succeeded = True
            step_offset = len(executed_records)

            for idx, tool_call in enumerate(current_plan.steps):
                step_idx = step_offset + idx + 1

                # Lifetime step limit check
                if len(executed_records) >= MAX_LIFETIME_STEPS:
                    logger.warning("Task %s: Reached maximum lifetime step limit (%d). Terminating.", task_id, MAX_LIFETIME_STEPS)
                    overall_error = f"Exceeded maximum task lifetime limit of {MAX_LIFETIME_STEPS} steps."
                    plan_succeeded = False
                    break

                # 1. Stop-Latch Check Before Every Step
                if token.is_cancelled:
                    logger.info("Task %s: Stop-latch detected before step %d (%s). Aborting.", task_id, step_idx, tool_call.tool)
                    return self._handle_stop(
                        capsule=capsule,
                        executed_records=executed_records,
                        start_time=start_time,
                        replan_count=replan_count,
                        reason="Stopped by user request",
                    )

                # Route-specific tool subset check
                from pluma.brain.tool_subset import ToolSubsetSelector
                plan_route = getattr(current_plan, "route", None) or (context.get("route") if context else None)
                if plan_route and not ToolSubsetSelector.is_tool_permitted(tool_call.tool, plan_route):
                    logger.warning("Task %s: Tool '%s' not permitted for route '%s'.", task_id, tool_call.tool, plan_route)
                    tool_result = ToolResult.failure(
                        tool_call.tool,
                        f"Tool '{tool_call.tool}' is not permitted in {plan_route} route.",
                        error_code="TOOL_NOT_PERMITTED_FOR_ROUTE",
                    )
                    record = StepExecutionRecord(
                        step_index=step_idx,
                        tool=tool_call.tool,
                        arguments=tool_call.arguments,
                        purpose=tool_call.purpose,
                        result=tool_result,
                        duration_ms=0.0,
                        replan_iteration=replan_count,
                    )
                    executed_records.append(record)
                    plan_succeeded = False
                    overall_error = tool_result.error
                    break

                step_start = time.perf_counter()
                logger.info(
                    "Task %s [Step %d/%d (Lifetime %d/%d)]: Executing '%s' (purpose: %s)",
                    task_id, idx + 1, len(current_plan.steps),
                    step_idx, MAX_LIFETIME_STEPS,
                    tool_call.tool, tool_call.purpose,
                )

                # 2. Execute Step through ToolRegistry (with policy evaluation)
                tool_result = self.registry.execute(
                    tool_name=tool_call.tool,
                    arguments=tool_call.arguments,
                    task_context=capsule,
                    ledger=self.ledger,
                    step_index=step_idx,
                    policy_engine=self.policy_engine,
                )
                step_duration_ms = (time.perf_counter() - step_start) * 1000.0

                record = StepExecutionRecord(
                    step_index=step_idx,
                    tool=tool_call.tool,
                    arguments=tool_call.arguments,
                    purpose=tool_call.purpose,
                    result=tool_result,
                    duration_ms=round(step_duration_ms, 1),
                    replan_iteration=replan_count,
                )
                executed_records.append(record)

                prior_results_for_replan.append({
                    "step_index": step_idx,
                    "tool": tool_call.tool,
                    "ok": tool_result.ok,
                    "verified": tool_result.verified,
                    "factual_message": tool_result.factual_message,
                    "data": tool_result.data,
                    "error": tool_result.error,
                })

                # Check cancellation right after step execution
                if token.is_cancelled:
                    logger.info("Task %s: Stop-latch detected after step %d (%s). Aborting.", task_id, step_idx, tool_call.tool)
                    return self._handle_stop(
                        capsule=capsule,
                        executed_records=executed_records,
                        start_time=start_time,
                        replan_count=replan_count,
                        reason="Stopped by user request",
                    )

                # 3. Check for Step Failure or Verification Rejection
                if not tool_result.ok or not tool_result.verified:
                    logger.warning(
                        "Task %s: Step %d (%s) failed or unverified: %s (error: %s)",
                        task_id, step_idx, tool_call.tool,
                        tool_result.factual_message, tool_result.error,
                    )
                    plan_succeeded = False
                    overall_error = tool_result.error or tool_result.factual_message
                    break

            # If all steps in current plan succeeded, complete task
            if plan_succeeded:
                if token.is_cancelled:
                    return self._handle_stop(
                        capsule=capsule,
                        executed_records=executed_records,
                        start_time=start_time,
                        replan_count=replan_count,
                        reason="Stopped by user request",
                    )
                total_duration_ms = (time.perf_counter() - start_time) * 1000.0
                self.supervisor.transition(task_id, TaskState.SUCCEEDED)
                summary_msgs = [r.result.factual_message for r in executed_records if r.result.factual_message]
                summary = " ".join(summary_msgs) or "Task completed successfully."
                return MultiStepExecutionResult(
                    task_id=task_id,
                    final_state=TaskState.SUCCEEDED,
                    steps_executed=executed_records,
                    replan_count=replan_count,
                    error=None,
                    duration_ms=round(total_duration_ms, 1),
                    factual_summary=summary,
                )

            # 4. Handle Replanning
            if (
                replan_count < self.max_replans
                and len(executed_records) < MAX_LIFETIME_STEPS
                and self.planner is not None
                and not token.is_cancelled
            ):
                replan_count += 1
                logger.info(
                    "Task %s: Attempting bounded replan (%d/%d)...",
                    task_id, replan_count, self.max_replans,
                )

                # Stop latch check before calling planner
                if token.is_cancelled:
                    return self._handle_stop(
                        capsule=capsule,
                        executed_records=executed_records,
                        start_time=start_time,
                        replan_count=replan_count,
                        reason="Stopped by user request",
                    )

                try:
                    replan_plan = self.planner.plan(
                        command=command_text,
                        context=context or {},
                        permitted_tool_specs=permitted_tool_specs or [],
                        prior_step_results=prior_results_for_replan,
                        cancellation_token=token,
                    )
                    if replan_plan and replan_plan.steps:
                        logger.info("Task %s: Replan yielded %d new steps.", task_id, len(replan_plan.steps))
                        current_plan = replan_plan
                        continue
                except (PlannerCancelledError, TaskCancelledError):
                    return self._handle_stop(
                        capsule=capsule,
                        executed_records=executed_records,
                        start_time=start_time,
                        replan_count=replan_count,
                        reason="Stopped during replanning",
                    )
                except Exception as replan_err:
                    logger.warning("Task %s: Replanning failed: %s", task_id, replan_err)
                    overall_error = f"Replanning failed: {replan_err}"

            # Replanning exhausted or unavailable -> Rollback & Fail
            logger.error("Task %s: Execution failed and replan exhausted. Initiating reverse rollback.", task_id)
            return self._handle_failure(
                capsule=capsule,
                executed_records=executed_records,
                start_time=start_time,
                replan_count=replan_count,
                error_msg=overall_error or "Step execution failed",
            )

    # ------------------------------------------------------------------
    # Abort / Failure / Stop Handlers
    # ------------------------------------------------------------------

    def _handle_stop(
        self,
        capsule: TaskCapsule,
        executed_records: List[StepExecutionRecord],
        start_time: float,
        replan_count: int,
        reason: str,
    ) -> MultiStepExecutionResult:
        """Handle STOP triggered during execution: reverse rollback & terminal transition."""
        task_id = capsule.task_id
        self.supervisor.transition(task_id, TaskState.STOPPING)
        self.supervisor.transition(task_id, TaskState.ROLLING_BACK)

        rb_success = True
        try:
            rb_result = self.rollback_engine.rollback_task(task_id, memory_undo_stack=capsule.undo_stack)
            rb_success = rb_result.all_ok
        except Exception as exc:
            logger.error("Task %s: Rollback failed during stop: %s", task_id, exc)
            rb_success = False

        final_state = TaskState.STOPPED if rb_success else TaskState.STOPPED_WITH_RESIDUAL
        self.supervisor.transition(task_id, final_state)

        total_duration_ms = (time.perf_counter() - start_time) * 1000.0
        return MultiStepExecutionResult(
            task_id=task_id,
            final_state=final_state,
            steps_executed=executed_records,
            replan_count=replan_count,
            error=reason,
            duration_ms=round(total_duration_ms, 1),
            factual_summary=f"Task stopped by user. Rollback {'completed' if rb_success else 'partial'}.",
            rollback_performed=True,
            rollback_success=rb_success,
        )

    def _handle_failure(
        self,
        capsule: TaskCapsule,
        executed_records: List[StepExecutionRecord],
        start_time: float,
        replan_count: int,
        error_msg: str,
    ) -> MultiStepExecutionResult:
        """Handle execution failure: reverse rollback of reversible prior steps & transition to FAILED."""
        task_id = capsule.task_id
        self.supervisor.transition(task_id, TaskState.STOPPING)
        self.supervisor.transition(task_id, TaskState.ROLLING_BACK)

        rb_success = True
        try:
            rb_result = self.rollback_engine.rollback_task(task_id, memory_undo_stack=capsule.undo_stack)
            rb_success = rb_result.all_ok
        except Exception as exc:
            logger.error("Task %s: Rollback failed during error recovery: %s", task_id, exc)
            rb_success = False

        self.supervisor.transition(task_id, TaskState.FAILED)
        total_duration_ms = (time.perf_counter() - start_time) * 1000.0
        return MultiStepExecutionResult(
            task_id=task_id,
            final_state=TaskState.FAILED,
            steps_executed=executed_records,
            replan_count=replan_count,
            error=error_msg,
            duration_ms=round(total_duration_ms, 1),
            factual_summary=f"Task failed: {error_msg}. Rollback {'completed' if rb_success else 'partial'}.",
            rollback_performed=True,
            rollback_success=rb_success,
        )
