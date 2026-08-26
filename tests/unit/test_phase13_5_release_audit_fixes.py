"""tests.unit.test_phase13_5_release_audit_fixes — Regression tests for release-blocking audit repairs."""

import os
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from pluma.config.paths import PlumaPaths
from pluma.config.loader import load_config
from pluma.core.cancellation import CancellationToken
from pluma.core.multi_step import MultiStepOrchestrator
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec
from pluma.tools.registry import ToolRegistry, register_default_tools
from pluma.app import PlumaApplicationRuntime


def test_audit_1_pre_mutation_undo_capture(tmp_path: Path) -> None:
    """Audit 1: Verify undo data is captured BEFORE file mutation occurs."""
    reg = ToolRegistry()
    register_default_tools(reg)

    src = tmp_path / "original.txt"
    src.write_text("original-content", encoding="utf-8")
    dst = tmp_path / "renamed.txt"

    capsule = TaskCapsule(request_id="req-audit-1")

    # Move file
    res = reg.execute(
        tool_name="move_file",
        arguments={"source": str(src), "destination": str(dst)},
        task_context=capsule,
    )

    assert res.ok is True
    assert res.undo_record is not None
    assert res.undo_record["source"] == str(src)
    assert res.undo_record["destination"] == str(dst)
    assert len(capsule.undo_stack) == 1


def test_audit_2_tool_timeout_enforcement() -> None:
    """Audit 2: Verify tool execution enforces spec.timeout_s."""
    reg = ToolRegistry()

    def slow_executor(args: dict, context: any) -> ToolResult:
        time.sleep(1.5)
        return ToolResult.success("slow_tool", data={"ran": True})

    from pluma.verify.common import verify_noop

    spec = ToolSpec(
        name="slow_tool",
        description="Simulates slow tool",
        version="1.0",
        args_schema={},
        risk_class=RiskClass.READ,
        timeout_s=0.2,  # 200ms timeout
        executor=slow_executor,
        verifier=verify_noop,
    )
    reg.register(spec)

    res = reg.execute(tool_name="slow_tool", arguments={})
    assert res.ok is False
    assert res.error_code == "TOOL_TIMEOUT"
    assert "timed out after 0.2" in res.error


def test_audit_2_route_specific_tool_subsets() -> None:
    """Audit 2: Verify route-specific tool permissions."""
    # SCREEN route permits UI perception and window management
    assert ToolSubsetSelector.is_tool_permitted("click_element", RouteMode.SCREEN) is True
    assert ToolSubsetSelector.is_tool_permitted("inspect_active_window", RouteMode.SCREEN) is True
    assert ToolSubsetSelector.is_tool_permitted("focus_window", RouteMode.SCREEN) is True
    assert ToolSubsetSelector.is_tool_permitted("move_file", RouteMode.SCREEN) is False

    # SMART route permits files, apps, windows, and system
    assert ToolSubsetSelector.is_tool_permitted("move_file", RouteMode.SMART) is True
    assert ToolSubsetSelector.is_tool_permitted("open_app", RouteMode.SMART) is True


def test_audit_3_stop_prevents_succeeded_state() -> None:
    """Audit 3: Verify STOP latch guarantees task is marked STOPPED, not SUCCEEDED."""
    from pluma.verify.common import verify_noop

    reg = ToolRegistry()
    supervisor = TaskSupervisor()
    multi = MultiStepOrchestrator(registry=reg, supervisor=supervisor)

    # Register mock tool that cancels token during execution
    def self_cancelling_tool(args: dict, context: any) -> ToolResult:
        if context and hasattr(context, "cancellation_token"):
            context.cancellation_token.cancel()
        return ToolResult.success("get_system_status", data={"ok": True}, factual_message="Executed successfully")

    reg.register(ToolSpec(
        name="get_system_status",
        description="Cancels task during execution",
        version="1.0",
        args_schema={},
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=self_cancelling_tool,
        verifier=verify_noop,
    ))

    capsule = supervisor.create_task_capsule(request_id="req-audit-3")
    plan = Plan(
        route=RouteMode.SMART,
        mode="direct",
        steps=[ToolCall(tool="get_system_status", arguments={}, purpose="test stop")]
    )

    res = multi.execute_plan(
        capsule=capsule,
        initial_plan=plan,
        command_text="run cancelling tool",
    )

    assert res.final_state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
    assert capsule.state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
    assert res.final_state != TaskState.SUCCEEDED


def test_audit_4_comprehensive_sqlite_redaction(tmp_path: Path) -> None:
    """Audit 4: Verify sensitive data is redacted across command_text, result, verification, and errors."""
    db_file = tmp_path / "redaction_test.db"
    db = DbConnection(str(db_file))
    db.open()

    ledger = ActivityLedger(db=db)

    # 1. Test task command_text redaction
    raw_cmd = "save api key sk-proj-12345678901234567890 to file"
    ledger.insert_task(TaskRecord(
        task_id="task-redact-1",
        request_id="req-redact-1",
        input_mode="text",
        command_text=raw_cmd,
    ))

    task_row = db.execute_read_one("SELECT command_text FROM tasks WHERE task_id = ?", ("task-redact-1",))
    assert task_row is not None
    assert "sk-proj-12345678901234567890" not in task_row[0]
    assert "[REDACTED]" in task_row[0]

    # 2. Test action result_data, verification_detail, and error_detail redaction
    action = ActionRecord(
        task_id="task-redact-1",
        step_index=1,
        tool="clipboard_read",
        args_raw={"secret_token": "ghp_123456789012345678901234567890123456"},
        risk="LOW",
        adapter="native",
        result_data={"password": "SuperSecretPassword123!", "data": "bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.do_not_leak"},
        verification_detail={"auth_token": "AKIAIOSFODNN7EXAMPLE"},
        error_detail={"error": "Failed authentication with token=sk-abcdefghijklmnopqrstuvwxyz123456"},
    )
    row_id = ledger.insert_action(action)

    action_row = db.execute_read_one(
        "SELECT args_json_sanitized, result_json, verification_json, error_json FROM actions WHERE rowid = ?",
        (row_id,)
    )
    assert action_row is not None
    for col in action_row:
        assert "SuperSecretPassword123!" not in col
        assert "ghp_123456789012345678901234567890123456" not in col
        assert "AKIAIOSFODNN7EXAMPLE" not in col
        assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in col
        assert "[REDACTED]" in col

    db.close()


def test_audit_5_production_runtime_lifecycle_wiring(tmp_path: Path) -> None:
    """Audit 5: Verify production runtime wires LLM lifecycle and model parameters."""
    paths = PlumaPaths(local_app_data=tmp_path)
    runtime = PlumaApplicationRuntime(paths=paths)

    assert runtime.llm_lifecycle is not None
    assert runtime.voice_lifecycle is not None
    assert runtime.orchestrator._llm_manager is runtime.llm_lifecycle

    runtime.close()


def test_audit_6_config_path_loading(tmp_path: Path) -> None:
    """Audit 6: Verify load_config() accepts custom config path argument."""
    custom_yaml = tmp_path / "custom.yaml"
    custom_yaml.write_text("agent:\n  max_plan_steps: 15\n", encoding="utf-8")

    cfg = load_config(user_config_path=custom_yaml)
    assert cfg["agent"]["max_plan_steps"] == 15


def test_audit_immediate_timeout_no_blocking() -> None:
    """Audit: Verify 50ms tool timeout returns immediately without blocking caller."""
    reg = ToolRegistry()
    from pluma.verify.common import verify_noop

    def very_slow_executor(args: dict, context: any) -> ToolResult:
        time.sleep(1.0)
        return ToolResult.success("very_slow", {})

    reg.register(ToolSpec(
        name="very_slow",
        description="Simulates long slow call",
        version="1.0",
        args_schema={},
        risk_class=RiskClass.READ,
        timeout_s=0.05,  # 50 ms
        executor=very_slow_executor,
        verifier=verify_noop,
    ))

    t0 = time.perf_counter()
    res = reg.execute("very_slow", {})
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert res.ok is False
    assert res.error_code == "TOOL_TIMEOUT"
    assert elapsed_ms < 200.0, f"Expected non-blocking timeout under 200ms, took {elapsed_ms:.1f}ms"


def test_audit_multi_step_automatic_rollback_restores_files(tmp_path: Path) -> None:
    """Audit: Verify failed multi-step execution automatically rolls back and restores moved files."""
    src = tmp_path / "original_file.txt"
    src.write_text("critical data", encoding="utf-8")
    dst = tmp_path / "moved_file.txt"

    from pluma.tools.registry import get_default_tool_registry
    reg = get_default_tool_registry()
    supervisor = TaskSupervisor()
    multi = MultiStepOrchestrator(registry=reg, supervisor=supervisor)

    capsule = supervisor.create_task_capsule(request_id="req-rollback-test")

    # Step 1 moves file; Step 2 fails on non-existent app
    plan = Plan(
        route=RouteMode.SMART,
        mode="multi_step",
        steps=[
            ToolCall(tool="move_file", arguments={"source": str(src), "destination": str(dst)}, purpose="move"),
            ToolCall(tool="open_app", arguments={"app_name": "non_existent_fake_app_xyz_999"}, purpose="fail"),
        ],
    )

    res = multi.execute_plan(capsule=capsule, initial_plan=plan, command_text="move and fail")

    assert res.final_state == TaskState.FAILED
    assert res.rollback_performed is True
    assert res.rollback_success is True
    # The source file MUST be restored back to existence
    assert src.exists() is True
    assert src.read_text(encoding="utf-8") == "critical data"
    assert dst.exists() is False


def test_audit_task_capsule_owned_resources() -> None:
    """Audit: Verify TaskCapsule carries owned resources directly."""
    from pluma.core.task_supervisor import ResourceOwnership
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule(request_id="req-res-test")

    res = capsule.register_owned_resource(
        resource_type="subprocess",
        ownership=ResourceOwnership.PLUMA_CREATED,
        external_id="12345",
        metadata={"cmd": "worker.exe"},
    )
    assert len(capsule.owned_resources) == 1
    assert capsule.owned_resources[0].resource_type == "subprocess"
    assert capsule.owned_resources[0].external_id == "12345"


def test_audit_terminal_task_memory_bounding() -> None:
    """Audit: Verify TaskSupervisor memory bounds terminal tasks to MAX_TERMINAL_TASKS_RETAINED."""
    supervisor = TaskSupervisor(max_retained_terminal_tasks=25)
    for i in range(100):
        cap = supervisor.create_task_capsule(request_id=f"req-{i}")
        supervisor.start_task(cap.task_id)
        supervisor.mark_succeeded(cap.task_id)

    assert len(supervisor._tasks) == 25


def test_audit_registry_exposes_33_tools() -> None:
    """Audit: Verify the default tool registry exposes exactly 33 registered tools."""
    from pluma.tools.registry import get_default_tool_registry
    reg = get_default_tool_registry()

    assert len(reg) == 33
    assert len(reg.list_tools()) == 33
    assert len(reg.list_tool_names()) == 33
    assert "move_file" in reg.list_tool_names()
    assert "inspect_active_window" in reg.list_tool_names()
    assert "undo_last" in reg.list_tool_names()
