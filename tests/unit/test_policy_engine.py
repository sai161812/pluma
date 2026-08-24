"""tests/unit/test_policy_engine.py — Phase 11: Policy Engine, Risk Classes & Elevation Broker tests."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock
import pytest

from pluma.policy.elevation_broker import ElevationBroker
from pluma.policy.engine import PolicyDecision, PolicyEngine, PolicyEvaluationResult
from pluma.policy.rules import PolicyRules
from pluma.tools.base import RiskClass, ToolResult, ToolSpec
from pluma.tools.registry import ToolRegistry, get_default_tool_registry
from pluma.ui.confirmations import (
    AutoApproveConfirmationContract,
    AutoDenyConfirmationContract,
    CallbackConfirmationContract,
    ConfirmationRequest,
    ConfirmationResponse,
)
from pluma.verify.common import verify_noop


def test_policy_read_low_auto_allow() -> None:
    """Verify that READ and LOW risk tools are automatically approved without user confirmation."""
    engine = PolicyEngine()

    res_read = engine.evaluate(tool_name="get_system_status", arguments={}, default_risk=RiskClass.READ)
    assert res_read.decision == PolicyDecision.ALLOW
    assert res_read.risk_class == RiskClass.READ
    assert res_read.requires_confirmation is False

    res_low = engine.evaluate(tool_name="set_volume", arguments={"level": 50}, default_risk=RiskClass.LOW)
    assert res_low.decision == PolicyDecision.ALLOW
    assert res_low.risk_class == RiskClass.LOW
    assert res_low.requires_confirmation is False


def test_policy_high_requires_confirmation() -> None:
    """Verify that HIGH risk tools without a confirmation contract return REQUIRE_CONFIRMATION."""
    engine = PolicyEngine(confirmation_contract=None)

    res_high = engine.evaluate(tool_name="delete_file", arguments={"path": "C:\\test.txt"}, default_risk=RiskClass.HIGH)
    assert res_high.decision == PolicyDecision.REQUIRE_CONFIRMATION
    assert res_high.risk_class == RiskClass.HIGH
    assert res_high.requires_confirmation is True


def test_policy_restricted_paths_denied_immediately() -> None:
    """Verify that targeting critical system folders (C:\\Windows, System32) is strictly RESTRICTED and DENIED."""
    engine = PolicyEngine()

    # Even if default risk is LOW, targeting C:\Windows must be classified as RESTRICTED
    res1 = engine.evaluate(tool_name="delete_file", arguments={"path": "C:\\Windows\\System32\\calc.exe"}, default_risk=RiskClass.LOW)
    assert res1.decision == PolicyDecision.DENY
    assert res1.risk_class == RiskClass.RESTRICTED

    res2 = engine.evaluate(tool_name="list_files", arguments={"path": "C:\\Windows"}, default_risk=RiskClass.READ)
    assert res2.decision == PolicyDecision.DENY
    assert res2.risk_class == RiskClass.RESTRICTED


def test_policy_restricted_command_patterns_denied() -> None:
    """Verify that dangerous shell command patterns (format, bcdedit) are strictly RESTRICTED and DENIED."""
    engine = PolicyEngine()

    res_cmd1 = engine.evaluate(tool_name="run_script", arguments={"script": "format D: /fs:NTFS"}, default_risk=RiskClass.HIGH)
    assert res_cmd1.decision == PolicyDecision.DENY
    assert res_cmd1.risk_class == RiskClass.RESTRICTED

    res_cmd2 = engine.evaluate(tool_name="run_script", arguments={"script": "bcdedit /set {default} bootstatuspolicy ignoreallfailures"}, default_risk=RiskClass.HIGH)
    assert res_cmd2.decision == PolicyDecision.DENY
    assert res_cmd2.risk_class == RiskClass.RESTRICTED


def test_policy_confirmation_dialog_approved() -> None:
    """Verify that when a user approves a confirmation request, execution is ALLOWED."""
    confirm_called = []

    def handle_confirm(req: ConfirmationRequest) -> ConfirmationResponse:
        confirm_called.append(req)
        return ConfirmationResponse(approved=True, reason="User confirmed delete")

    contract = CallbackConfirmationContract(handle_confirm)
    engine = PolicyEngine(confirmation_contract=contract)

    res = engine.evaluate(
        tool_name="delete_file",
        arguments={"path": "C:\\Users\\test\\doc.txt"},
        default_risk=RiskClass.HIGH,
        task_id="task-confirm-1",
    )

    assert res.decision == PolicyDecision.ALLOW
    assert res.risk_class == RiskClass.HIGH
    assert len(confirm_called) == 1
    assert confirm_called[0].tool_name == "delete_file"
    assert confirm_called[0].task_id == "task-confirm-1"


def test_policy_confirmation_dialog_denied() -> None:
    """Verify that when a user denies a confirmation request, execution is DENIED."""
    contract = AutoDenyConfirmationContract()
    engine = PolicyEngine(confirmation_contract=contract)

    res = engine.evaluate(
        tool_name="delete_file",
        arguments={"path": "C:\\Users\\test\\doc.txt"},
        default_risk=RiskClass.HIGH,
    )

    assert res.decision == PolicyDecision.DENY
    assert "denied" in res.reason.lower()


def test_tool_policy_yaml_override() -> None:
    """Verify that YAML configuration overrides tool risk classes."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as tf:
        tf.write("mute: HIGH\nunmute: RESTRICTED\n")
        tf_path = tf.name

    try:
        rules = PolicyRules(config_path=tf_path)
        engine = PolicyEngine(rules=rules, confirmation_contract=AutoDenyConfirmationContract())

        # Mute is normally LOW, overridden to HIGH -> AutoDeny blocks it
        res_mute = engine.evaluate(tool_name="mute", arguments={}, default_risk=RiskClass.LOW)
        assert res_mute.risk_class == RiskClass.HIGH
        assert res_mute.decision == PolicyDecision.DENY

        # Unmute is overridden to RESTRICTED -> Denied immediately
        res_unmute = engine.evaluate(tool_name="unmute", arguments={}, default_risk=RiskClass.LOW)
        assert res_unmute.risk_class == RiskClass.RESTRICTED
        assert res_unmute.decision == PolicyDecision.DENY
    finally:
        if os.path.exists(tf_path):
            os.unlink(tf_path)


def test_policy_engine_integrated_in_registry_execution() -> None:
    """Verify that ToolRegistry.execute() enforces policy engine boundaries before running tools."""
    engine = PolicyEngine(confirmation_contract=AutoDenyConfirmationContract())
    registry = ToolRegistry(policy_engine=engine)

    def dummy_exec(args: dict, ctx: any = None) -> ToolResult:
        return ToolResult(ok=True, tool="test_tool", factual_message="Executed successfully.")

    # High-risk tool blocked by AutoDeny policy
    registry.register(ToolSpec(
        name="dangerous_tool",
        description="High risk tool",
        args_schema={"type": "object"},
        risk_class=RiskClass.HIGH,
        timeout_s=5.0,
        executor=dummy_exec,
        verifier=verify_noop,
    ))

    res = registry.execute("dangerous_tool", {})
    assert res.ok is False
    assert res.error_code == "POLICY_DENIED"
    assert "Blocked by policy" in (res.error or "")


def test_elevation_broker_execution() -> None:
    """Verify that ElevationBroker runs isolated single-operation commands."""
    broker = ElevationBroker(timeout_s=5.0)

    # Safe lightweight command (e.g. echo)
    res = broker.execute_elevated_script(
        script="Write-Output 'PLUMA_ELEVATION_TEST'",
        task_id="task-elev-test",
    )

    assert isinstance(res, ToolResult)
    assert res.tool == "elevate"
    assert res.adapter_used in ("elevation_broker", "elevation_broker_mock")
