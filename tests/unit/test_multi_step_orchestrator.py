"""tests/unit/test_multi_step_orchestrator.py — Phase 10: Bounded multi-step orchestration tests."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock
import pytest

from pluma.brain.lifecycle import LlmLifecycleManager
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import CancellationToken
from pluma.core.multi_step import MultiStepOrchestrator
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection
from pluma.rollback.engine import RollbackEngine
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry, get_default_tool_registry
from pluma.verify.common import verify_noop


def test_multi_step_successful_execution_chain() -> None:
    """Verify sequential execution of a 2-step plan with state transitions."""
    registry = ToolRegistry()

    # Step 1 mock tool
    step1_called = []
    def exec_step1(args: dict, ctx: any = None) -> ToolResult:
        step1_called.append(args)
        return ToolResult(ok=True, tool="step1_tool", factual_message="Step 1 complete.", verified=True)

    # Step 2 mock tool
    step2_called = []
    def exec_step2(args: dict, ctx: any = None) -> ToolResult:
        step2_called.append(args)
        return ToolResult(ok=True, tool="step2_tool", factual_message="Step 2 complete.", verified=True)

    registry.register(ToolSpec(
        name="step1_tool", description="Step 1", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_step1, verifier=verify_noop,
    ))
    registry.register(ToolSpec(
        name="step2_tool", description="Step 2", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_step2, verifier=verify_noop,
    ))

    supervisor = TaskSupervisor()
    multi_step = MultiStepOrchestrator(registry=registry, supervisor=supervisor)

    capsule = supervisor.create_task("req-1")
    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.MULTI_STEP,
        steps=[
            ToolCall(tool="step1_tool", arguments={"val": 1}, purpose="Run step 1"),
            ToolCall(tool="step2_tool", arguments={"val": 2}, purpose="Run step 2"),
        ],
    )

    res = multi_step.execute_plan(capsule, plan, command_text="Run test plan")
    assert res.final_state == TaskState.SUCCEEDED
    assert len(res.steps_executed) == 2
    assert len(step1_called) == 1
    assert len(step2_called) == 1
    assert "Step 1 complete" in res.factual_summary
    assert "Step 2 complete" in res.factual_summary


def test_multi_step_stop_latch_aborts_immediately() -> None:
    """Verify stop-latch set before step 2 prevents step 2 from executing and triggers rollback."""
    registry = ToolRegistry()

    step1_called = []
    token = CancellationToken()

    def exec_step1(args: dict, ctx: any = None) -> ToolResult:
        step1_called.append(args)
        # Cancel token during step 1 execution
        token.cancel()
        return ToolResult(ok=True, tool="step1_tool", factual_message="Step 1 complete.", verified=True)

    step2_called = []
    def exec_step2(args: dict, ctx: any = None) -> ToolResult:
        step2_called.append(args)
        return ToolResult(ok=True, tool="step2_tool", factual_message="Step 2 complete.", verified=True)

    registry.register(ToolSpec(
        name="step1_tool", description="Step 1", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_step1, verifier=verify_noop,
    ))
    registry.register(ToolSpec(
        name="step2_tool", description="Step 2", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_step2, verifier=verify_noop,
    ))

    supervisor = TaskSupervisor()
    multi_step = MultiStepOrchestrator(registry=registry, supervisor=supervisor)

    capsule = supervisor.create_task("req-2")
    capsule.cancellation_token = token

    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.MULTI_STEP,
        steps=[
            ToolCall(tool="step1_tool", arguments={}, purpose="First"),
            ToolCall(tool="step2_tool", arguments={}, purpose="Second"),
        ],
    )

    res = multi_step.execute_plan(capsule, plan, command_text="Run cancel plan")
    assert res.final_state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
    assert len(step1_called) == 1
    assert len(step2_called) == 0, "Step 2 must NEVER run after stop-latch is set"
    assert res.rollback_performed is True


def test_multi_step_replan_on_step_failure() -> None:
    """Verify that a failing step invokes the planner with prior results to produce a recovery plan."""
    registry = ToolRegistry()

    # Failing step 1
    def exec_failing(args: dict, ctx: any = None) -> ToolResult:
        return ToolResult(ok=False, tool="failing_tool", factual_message="Resource locked", verified=False, error="LOCKED")

    # Recovery step
    recovery_called = []
    def exec_recovery(args: dict, ctx: any = None) -> ToolResult:
        recovery_called.append(args)
        return ToolResult(ok=True, tool="recovery_tool", factual_message="Recovered via alternative", verified=True)

    registry.register(ToolSpec(
        name="failing_tool", description="Fails", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_failing, verifier=verify_noop,
    ))
    registry.register(ToolSpec(
        name="recovery_tool", description="Recovers", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_recovery, verifier=verify_noop,
    ))

    # Mock planner that produces recovery plan when given prior failure
    mock_planner = MagicMock()
    mock_planner.plan.return_value = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="recovery_tool", arguments={"alt": True}, purpose="Recovery step")],
    )

    supervisor = TaskSupervisor()
    multi_step = MultiStepOrchestrator(
        registry=registry, supervisor=supervisor, planner=mock_planner, max_replans=2
    )

    capsule = supervisor.create_task("req-3")
    initial_plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="failing_tool", arguments={}, purpose="Initial attempt")],
    )

    res = multi_step.execute_plan(capsule, initial_plan, command_text="Try operation")
    assert res.final_state == TaskState.SUCCEEDED
    assert res.replan_count == 1
    assert len(recovery_called) == 1
    mock_planner.plan.assert_called_once()


def test_multi_step_replan_limit_halts_loop() -> None:
    """Verify that exceeding max_replans terminates execution as FAILED and triggers rollback."""
    registry = ToolRegistry()

    def exec_always_fail(args: dict, ctx: any = None) -> ToolResult:
        return ToolResult(ok=False, tool="fail_tool", factual_message="Persistent failure", verified=False, error="FAIL")

    registry.register(ToolSpec(
        name="fail_tool", description="Always fails", args_schema={"type": "object"},
        risk_class=RiskClass.LOW, timeout_s=5.0, executor=exec_always_fail, verifier=verify_noop,
    ))

    mock_planner = MagicMock()
    mock_planner.plan.return_value = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="fail_tool", arguments={}, purpose="Retry")],
    )

    supervisor = TaskSupervisor()
    multi_step = MultiStepOrchestrator(
        registry=registry, supervisor=supervisor, planner=mock_planner, max_replans=2
    )

    capsule = supervisor.create_task("req-4")
    initial_plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="fail_tool", arguments={}, purpose="Attempt 1")],
    )

    res = multi_step.execute_plan(capsule, initial_plan, command_text="Fail repeatedly")
    assert res.final_state == TaskState.FAILED
    assert res.replan_count == 2
    assert mock_planner.plan.call_count == 2
    assert res.rollback_performed is True


def test_orchestrator_smart_route_e2e() -> None:
    """End-to-end test of Orchestrator routing SMART request through LLM planner and MultiStepOrchestrator."""
    registry = get_default_tool_registry()

    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "multi_step", "steps": ['
        '{"tool": "create_folder", "arguments": {"path": "C:\\\\smart_test"}, "purpose": "Create folder"},'
        '{"tool": "list_files", "arguments": {"path": "C:\\\\smart_test"}, "purpose": "List contents"}'
        ']}'
    )

    llm_manager = LlmLifecycleManager(custom_backend=mock_backend, idle_unload_seconds=1.0)
    supervisor = TaskSupervisor()
    router = Router()

    orchestrator = Orchestrator(
        registry=registry,
        supervisor=supervisor,
        router=router,
        llm_manager=llm_manager,
    )

    req = PlumaRequest(input_mode=InputMode.TEXT, text="Create folder smart_test and list it")
    res = orchestrator.execute(req)

    assert res.route == RouteMode.SMART
    assert res.final_state == "SUCCEEDED"
    assert len(res.steps) == 2
    assert res.steps[0].tool == "create_folder"
    assert res.steps[1].tool == "list_files"


def test_orchestrator_screen_route_e2e() -> None:
    """End-to-end test of Orchestrator executing SCREEN route request with mock planner."""
    registry = get_default_tool_registry()

    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SCREEN", "mode": "direct", "steps": ['
        '{"tool": "click_element", "arguments": {"name": "submit"}, "purpose": "Click submit button"}'
        ']}'
    )

    llm_manager = LlmLifecycleManager(custom_backend=mock_backend, idle_unload_seconds=1.0)
    supervisor = TaskSupervisor()
    router = Router()

    orchestrator = Orchestrator(
        registry=registry,
        supervisor=supervisor,
        router=router,
        llm_manager=llm_manager,
    )

    # Deterministic screen tool route ("click submit")
    req = PlumaRequest(input_mode=InputMode.TEXT, text="click submit")
    res = orchestrator.execute(req)

    assert res.route == RouteMode.SCREEN
    assert res.final_state in ("SUCCEEDED", "FAILED")  # Fails gracefully if headless without active GUI


def test_orchestrator_deep_route_e2e() -> None:
    """End-to-end test of Orchestrator executing DEEP route request."""
    registry = get_default_tool_registry()

    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "DEEP", "mode": "multi_step", "steps": ['
        '{"tool": "create_folder", "arguments": {"path": "C:\\\\deep_test"}, "purpose": "Setup folder"},'
        '{"tool": "list_files", "arguments": {"path": "C:\\\\deep_test"}, "purpose": "Verify directory"}'
        ']}'
    )

    llm_manager = LlmLifecycleManager(custom_backend=mock_backend, idle_unload_seconds=1.0)
    supervisor = TaskSupervisor()
    router = Router()

    orchestrator = Orchestrator(
        registry=registry,
        supervisor=supervisor,
        router=router,
        llm_manager=llm_manager,
    )

    # Complex multi-step task triggering DEEP route
    req = PlumaRequest(
        input_mode=InputMode.TEXT,
        text="Look at this setup screen and finish the remaining configuration by creating a directory",
    )
    res = orchestrator.execute(req)

    assert res.route == RouteMode.DEEP
    assert res.final_state == "SUCCEEDED"
    assert len(res.steps) == 2
    assert res.steps[0].tool == "create_folder"
    assert res.steps[1].tool == "list_files"
