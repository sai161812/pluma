"""tests/unit/test_phase13_5_stage_b_safety.py — Stage B Safety and Policy regression tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pluma.policy.elevation_broker import ElevationBroker
from pluma.policy.engine import PolicyDecision, PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools.apps import OpenAppArgs, execute_open_app
from pluma.tools.audio import SetVolumeArgs
from pluma.tools.base import RiskClass, ToolResult
from pluma.tools.files import MoveFileArgs
from pluma.tools.registry import ToolArgumentError, ToolRegistry, register_default_tools
from pluma.ui.confirmations import AutoApproveConfirmationContract, AutoDenyConfirmationContract


def test_stage_b_fail_closed_policy_engine() -> None:
    """Gate B: Verify all RiskClasses are handled explicitly without fallback ALLOW."""
    engine = PolicyEngine(confirmation_contract=AutoDenyConfirmationContract())

    # 1. READ, LOW, MEDIUM allow autonomously
    assert engine.evaluate("list_files", {}, default_risk=RiskClass.READ).decision == PolicyDecision.ALLOW
    assert engine.evaluate("focus_window", {}, default_risk=RiskClass.LOW).decision == PolicyDecision.ALLOW
    assert engine.evaluate("move_file", {"source": "a.txt", "destination": "b.txt"}, default_risk=RiskClass.MEDIUM).decision == PolicyDecision.ALLOW

    # 2. RESTRICTED & DENY are strictly denied
    assert engine.evaluate("delete_system", {}, default_risk=RiskClass.RESTRICTED).decision == PolicyDecision.DENY
    assert engine.evaluate("forbidden_op", {}, default_risk=RiskClass.DENY).decision == PolicyDecision.DENY

    # 3. ADMIN requires elevation broker
    res_admin = engine.evaluate("elevated_task", {}, default_risk=RiskClass.ADMIN)
    assert res_admin.decision == PolicyDecision.REQUIRE_ELEVATION
    assert res_admin.requires_elevation is True

    # 4. HIGH with AutoDeny -> DENY
    res_high_denied = engine.evaluate("high_risk", {}, default_risk=RiskClass.HIGH)
    assert res_high_denied.decision == PolicyDecision.DENY

    # 5. HIGH with AutoApprove -> ALLOW
    engine_approve = PolicyEngine(confirmation_contract=AutoApproveConfirmationContract())
    res_high_approved = engine_approve.evaluate("high_risk", {}, default_risk=RiskClass.HIGH)
    assert res_high_approved.decision == PolicyDecision.ALLOW


def test_stage_b_open_app_security_boundaries() -> None:
    """Gate B: Verify open_app rejects interpreters, shell escapes, metacharacters, and dangerous flags."""
    # 1. Forbidden interpreters rejected in Pydantic schema
    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="cmd.exe")

    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="powershell")

    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="python.exe")

    # 2. Shell metacharacters rejected in Pydantic schema
    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="notepad & dir")

    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="calc.exe", arguments=["1", ";", "del", "*"])

    with pytest.raises(ValidationError):
        OpenAppArgs(app_name="calc.exe", arguments=["-encodedcommand", "MQ=="])

    # 3. Runtime rejection in execute_open_app
    res_cmd = execute_open_app({"app_name": "cmd.exe"})
    assert res_cmd.ok is False
    assert "forbidden" in res_cmd.error.lower()

    res_pipe = execute_open_app({"app_name": "notepad", "arguments": ["test.txt", "|", "calc"]})
    assert res_pipe.ok is False
    assert "forbidden" in res_pipe.error.lower()


def test_stage_b_pydantic_extra_forbid() -> None:
    """Gate B: Verify extra arguments are forbidden across tool schemas."""
    # Extra field on SetVolumeArgs
    with pytest.raises(ValidationError):
        SetVolumeArgs(level=50, malicious_injection="rm -rf /")

    # Extra field on MoveFileArgs
    with pytest.raises(ValidationError):
        MoveFileArgs(source="a.txt", destination="b.txt", unexpected_key=123)

    # ToolRegistry.validate_call rejection
    registry = ToolRegistry()
    register_default_tools(registry)
    with pytest.raises(ToolArgumentError):
        registry.validate_call("set_volume", {"level": 50, "extra_payload": "hack"})


def test_stage_b_undo_recorded_only_on_verified_success() -> None:
    """Gate B: Undo records are generated only when the tool call succeeds and passes postcondition verification."""
    registry = ToolRegistry()
    register_default_tools(registry)

    # Invoking a failing tool should produce no undo record
    class DummyContext:
        task_id = "task-test-undo"
        undo_stack = []

    ctx = DummyContext()
    # Attempt to move a non-existent file
    res = registry.execute(
        "move_file",
        {"source": "C:\\non_existent_file_12345.xyz", "destination": "C:\\temp_dst.xyz"},
        task_context=ctx,
    )
    assert res.ok is False
    assert len(ctx.undo_stack) == 0
