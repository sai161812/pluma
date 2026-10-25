from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pluma.perception.element_refs import (
    BoundingBox,
    ElementSource,
    ScreenElement,
    ScreenSnapshot,
)
from pluma.perception.snapshot_registry import SnapshotRegistry
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.multi_step import MultiStepOrchestrator
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry
from pluma.verify.common import verify_noop


def _snapshot(snapshot_id: str, *, expired: bool = False) -> ScreenSnapshot:
    now = datetime.now(timezone.utc)
    element = ScreenElement(
        element_id="save-button",
        snapshot_id=snapshot_id,
        source=ElementSource.UIA,
        label="Save",
        control_type="Button",
        bounds=BoundingBox(left=1, top=1, right=10, bottom=10),
        confidence=1.0,
        invocation_capability="invoke",
    )
    return ScreenSnapshot(
        snapshot_id=snapshot_id,
        created_at=now,
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(seconds=30),
        active_process="fixture.exe",
        active_window_title="Fixture",
        window_rect=BoundingBox(left=0, top=0, right=200, bottom=100),
        dpi_scale=1.0,
        controls=[element],
    )


@pytest.mark.parametrize("reference_kind", ["unknown", "expired"])
def test_planner_target_reference_is_rejected_at_registry_admission(reference_kind: str) -> None:
    executions: list[dict] = []
    policy_calls: list[str] = []

    def execute(args, _context=None):
        executions.append(args)
        return ToolResult.success("fixture_read", {"value": args["value"]}, "Read fixture.")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="fixture_read",
        description="Read a fixture value.",
        args_schema={"type": "object", "properties": {"value": {"type": "string"}},
                     "additionalProperties": False},
        risk_class=RiskClass.READ,
        timeout_s=2,
        executor=execute,
        verifier=verify_noop,
    ))
    snapshots = SnapshotRegistry()
    registered = _snapshot("registered")
    snapshots.register(registered)

    if reference_kind == "expired":
        expired = _snapshot("expired", expired=True)
        snapshots.register(expired)
        target_ref = "expired::save-button"
    else:
        target_ref = "unknown::save-button"

    class PolicySpy:
        def evaluate(self, **_kwargs):
            policy_calls.append("called")
            raise AssertionError("Policy must not run for an invalid planner target.")

    class Context:
        snapshot_registry = snapshots
        cancellation_token = None
        task_id = "p13-target-ref-fixture"

    result = registry.execute(
        "fixture_read",
        {"value": "safe"},
        task_context=Context(),
        policy_engine=PolicySpy(),
        planner_target_ref=target_ref,
    )

    assert not result.ok
    assert result.error_code == "STALE_TARGET_REF"
    assert executions == []
    assert policy_calls == []


def test_valid_planner_target_reference_reaches_admission() -> None:
    executed: list[bool] = []

    def execute(_args, _context=None):
        executed.append(True)
        return ToolResult.success("fixture_read", {"value": "ok"}, "Read fixture.")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="fixture_read",
        description="Read a fixture value.",
        args_schema={"type": "object", "properties": {"value": {"type": "string"}},
                     "additionalProperties": False},
        risk_class=RiskClass.READ,
        timeout_s=2,
        executor=execute,
        verifier=verify_noop,
    ))
    snapshot = _snapshot("current")
    snapshots = SnapshotRegistry()
    snapshots.register(snapshot)

    class Context:
        snapshot_registry = snapshots
        cancellation_token = None
        task_id = "p13-target-ref-valid"

    result = registry.execute(
        "fixture_read",
        {"value": "safe"},
        task_context=Context(),
        planner_target_ref="current::save-button",
    )

    assert result.ok
    assert executed == [True]


def test_multistep_planner_reference_reaches_registry_admission() -> None:
    executions: list[bool] = []

    def execute(_args, _context=None):
        executions.append(True)
        return ToolResult.success("fixture_read", {"value": "ok"}, "Read fixture.")

    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="fixture_read",
        description="Read a fixture value.",
        args_schema={"type": "object", "properties": {"value": {"type": "string"}},
                     "additionalProperties": False},
        risk_class=RiskClass.READ,
        timeout_s=2,
        executor=execute,
        verifier=verify_noop,
    ))
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule(request_id="p13-target-ref-plan")
    supervisor.start_task(capsule.task_id)
    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(
            tool="fixture_read",
            arguments={"value": "safe"},
            target_ref="unknown::save-button",
            purpose="Read the fixture.",
        )],
    )

    result = MultiStepOrchestrator(registry=registry, supervisor=supervisor).execute_plan(
        capsule, plan, command_text="Read the fixture.")

    assert result.final_state == TaskState.FAILED
    assert len(result.steps_executed) == 1
    assert result.steps_executed[0].result.error_code == "STALE_TARGET_REF"
    assert executions == []
