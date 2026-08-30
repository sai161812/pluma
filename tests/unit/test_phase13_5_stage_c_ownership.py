"""tests/unit/test_phase13_5_stage_c_ownership.py — Stage C STOP and Ownership regression tests."""

from __future__ import annotations

import os
import sys
import pytest

from pluma.brain.schemas import Plan, PlanMode, ToolCall
from pluma.core.cancellation import CancellationToken, StopReason
from pluma.core.multi_step import MAX_LIFETIME_STEPS, MultiStepOrchestrator
from pluma.core.ownership import OwnershipRegistry, get_process_creation_time
from pluma.core.task_supervisor import ResourceOwnership, TaskCapsule, TaskState, TaskSupervisor
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry


def test_stage_c_stop_and_ownership_cleanup() -> None:
    """Gate C: Verify STOP sequence cleans up owned temp directories, terminates Job Objects, and sets final state."""
    registry = OwnershipRegistry()
    supervisor = TaskSupervisor(ownership_registry=registry)

    # 1. Create task capsule and owned temp directory
    capsule = supervisor.create_task_capsule("task-stop-test", "test command")
    supervisor.transition("task-stop-test", TaskState.RUNNING)

    temp_dir = registry.create_task_temp_dir("task-stop-test")
    test_file = temp_dir / "temp_artifact.txt"
    test_file.write_text("temporary data")
    assert test_file.exists()

    # 2. Stop the task
    supervisor.stop_task("task-stop-test", reason=StopReason.USER_STOP)

    # 3. Verify final state and cleanup
    updated_cap = supervisor.get_task_capsule("task-stop-test")
    assert updated_cap.state == TaskState.STOPPED
    assert updated_cap.cancellation_token.is_cancelled is True
    assert not temp_dir.exists()


def test_stage_c_64bit_process_creation_timestamp_and_identity() -> None:
    """Gate C: Verify 64-bit creation timestamp capture and PID identity verification."""
    registry = OwnershipRegistry()
    current_pid = os.getpid()

    # Register current process
    owned = registry.register_subprocess(
        task_id="task-pid-test",
        pid=current_pid,
        ownership=ResourceOwnership.PREEXISTING,
        command_class="test_proc",
    )

    if sys.platform == "win32":
        creation_time = owned.metadata.get("creation_time")
        assert creation_time is not None
        assert isinstance(creation_time, int)
        assert creation_time > 0

        # Validating current PID identity with true timestamp succeeds
        assert registry.verify_pid_identity(current_pid, creation_time) is True

        # Validating with wrong timestamp fails closed
        assert registry.verify_pid_identity(current_pid, creation_time + 999999) is False


def test_stage_c_20_step_lifetime_cap() -> None:
    """Gate C: Verify strict 20-step lifetime cap across all steps and replans."""
    tool_registry = ToolRegistry()

    # Register a simple mock tool that fails at step 12 to trigger replanning
    step_count = 0

    def mock_step_exec(args: dict, ctx: any = None) -> ToolResult:
        nonlocal step_count
        step_count += 1
        if step_count == 12:
            return ToolResult.failure("test_step", "Step 12 trigger replan")
        return ToolResult(ok=True, tool="test_step", factual_message=f"Step {step_count}", verified=True)

    from pydantic import BaseModel

    class DummyStepArgs(BaseModel):
        model_config = {"extra": "forbid"}

    tool_registry.register(
        ToolSpec(
            name="test_step",
            description="Test step",
            args_schema=DummyStepArgs,
            risk_class=RiskClass.READ,
            timeout_s=5.0,
            executor=mock_step_exec,
            verifier=lambda r: VerifyResult(ok=True, method="mock", detail="ok"),
            cancellable=True,
        )
    )

    class MockPlanner:
        def plan(self, *args, **kwargs):
            # Return 15 new steps
            return Plan(
                mode=PlanMode.MULTI_STEP,
                steps=[ToolCall(tool="test_step", arguments={}, purpose=f"Replan step {i}") for i in range(15)],
            )

    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule("task-cap-test", "test command")
    multi_step = MultiStepOrchestrator(registry=tool_registry, supervisor=supervisor, planner=MockPlanner())

    initial_plan = Plan(
        mode=PlanMode.MULTI_STEP,
        steps=[ToolCall(tool="test_step", arguments={}, purpose=f"Initial step {i}") for i in range(15)],
    )

    result = multi_step.execute_plan(
        capsule=capsule,
        initial_plan=initial_plan,
        command_text="test command",
    )

    assert result.final_state == TaskState.FAILED
    assert len(result.steps_executed) == MAX_LIFETIME_STEPS
    assert len(result.steps_executed) == 20
    assert "exceeded" in result.error.lower()
