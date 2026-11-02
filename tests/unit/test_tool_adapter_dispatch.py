"""Runtime adapter fallback is ordered, declared and side-effect conservative."""

import pytest
from pydantic import BaseModel, ValidationError

from pluma.tools.base import (
    AdapterDispatcher,
    AdapterPriority,
    AdapterUnavailable,
    RiskClass,
    ToolResult,
    ToolSpec,
)
from pluma.tools.registry import ToolRegistry
from pluma.verify.common import verify_noop
from pluma.tools.ui import ALL_UI_TOOLS, INSPECT_ACTIVE_WINDOW_SPEC
from unittest.mock import MagicMock
from pluma.perception.context import ActiveWindowInfo


class EmptyArgs(BaseModel):
    model_config = {"extra": "forbid", "strict": True}


def _registry_for(executor, priorities):
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="adapter_probe", description="Inert ordered adapter fixture.",
        args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=2,
        executor=executor, verifier=verify_noop, adapter_priority=priorities,
    ))
    return registry


def test_dispatch_retries_only_before_dispatch_and_in_declared_order():
    calls = []

    def native(args, context):
        calls.append("native")
        raise AdapterUnavailable()

    def uia(args, context):
        calls.append("uia")
        return ToolResult.success("adapter_probe", data={"selected": "uia"},
            factual_message="Inert UIA result.")

    dispatcher = AdapterDispatcher("adapter_probe", {
        AdapterPriority.NATIVE_API: native,
        AdapterPriority.UIA: uia,
    })
    registry = _registry_for(dispatcher, [AdapterPriority.NATIVE_API, AdapterPriority.UIA])
    try:
        result = registry.execute("adapter_probe", {})
    finally:
        registry.close()

    assert result.ok and result.verified
    assert result.adapter_used == "uia"
    assert calls == ["native", "uia"]


def test_result_failure_never_retries_after_possible_effect():
    calls = []

    def native(args, context):
        calls.append("native")
        return ToolResult.failure("adapter_probe", "Native call failed after dispatch.", "NATIVE_FAILED")

    def uia(args, context):
        calls.append("uia")
        return ToolResult.success("adapter_probe", factual_message="Must not run.")

    dispatcher = AdapterDispatcher("adapter_probe", {
        AdapterPriority.NATIVE_API: native,
        AdapterPriority.UIA: uia,
    })
    registry = _registry_for(dispatcher, [AdapterPriority.NATIVE_API, AdapterPriority.UIA])
    try:
        result = registry.execute("adapter_probe", {})
    finally:
        registry.close()

    assert not result.ok and result.error_code == "NATIVE_FAILED"
    assert calls == ["native"]


def test_dispatch_never_uses_an_undeclared_lower_priority_adapter():
    calls = []

    def native(args, context):
        calls.append("native")
        raise AdapterUnavailable()

    def uia(args, context):
        calls.append("uia")
        raise AdapterUnavailable()

    def raw_coordinate(args, context):
        calls.append("raw_coordinate")
        return ToolResult.success("adapter_probe", factual_message="Must not run.")

    dispatcher = AdapterDispatcher("adapter_probe", {
        AdapterPriority.NATIVE_API: native,
        AdapterPriority.UIA: uia,
    })
    registry = _registry_for(dispatcher, [AdapterPriority.NATIVE_API, AdapterPriority.UIA])
    try:
        result = registry.execute("adapter_probe", {})
    finally:
        registry.close()

    assert not result.ok and result.error_code == "ADAPTERS_UNAVAILABLE"
    assert calls == ["native", "uia"]
    assert "raw_coordinate" not in calls


def test_dispatcher_order_must_match_registered_tool_priority():
    dispatcher = AdapterDispatcher("adapter_probe", {
        AdapterPriority.NATIVE_API: lambda args, context: ToolResult.success(
            "adapter_probe", factual_message="Inert."),
        AdapterPriority.UIA: lambda args, context: ToolResult.success(
            "adapter_probe", factual_message="Inert."),
    })
    with pytest.raises(ValidationError, match="exactly match"):
        ToolSpec(
            name="adapter_probe", description="Mismatched inert adapter fixture.",
            args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=2,
            executor=dispatcher, verifier=verify_noop,
            adapter_priority=[AdapterPriority.NATIVE_API, AdapterPriority.POWERSHELL],
        )


def test_multi_adapter_metadata_cannot_bypass_runtime_dispatch():
    with pytest.raises(ValidationError, match="require an AdapterDispatcher"):
        _registry_for(lambda args: None, [AdapterPriority.NATIVE_API, AdapterPriority.UIA])
    assert all(isinstance(spec.executor, AdapterDispatcher) for spec in ALL_UI_TOOLS)
    assert all(spec.executor.priorities == tuple(spec.adapter_priority) for spec in ALL_UI_TOOLS)


@pytest.mark.parametrize("controls,expected", [(False, "native_api"), (True, "uia")])
def test_registered_production_inspection_dispatches_actual_declared_adapters(monkeypatch, controls, expected):
    from pluma.tools import ui
    context = MagicMock()
    context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=123, pid=321, process_name="fixture.exe", window_title="Fixture", is_valid=True)
    monkeypatch.setattr(ui, "ActiveWindowContext", lambda: context)
    builder = MagicMock()
    snapshot = builder.capture.return_value
    snapshot.controls = []
    snapshot.snapshot_id = "owned-fixture"
    snapshot.model_dump.return_value = {}
    monkeypatch.setattr(ui, "UiaSnapshotBuilder", lambda **kwargs: builder)
    registry = ToolRegistry()
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC.model_copy(update={"process_isolated": False}))
    try:
        result = registry.execute("inspect_active_window", {"include_controls": controls})
    finally:
        registry.close()
    assert result.ok and result.adapter_used == expected
    assert builder.capture.called is controls


def test_stop_between_adapter_attempts_blocks_fallback():
    from pluma.core.cancellation import CancellationToken, TaskCancelledError
    from types import SimpleNamespace
    token = CancellationToken()
    calls = []
    def native(args, context):
        token.cancel()
        raise AdapterUnavailable()
    def uia(args, context):
        calls.append("uia")
    dispatcher = AdapterDispatcher("adapter_probe", {
        AdapterPriority.NATIVE_API: native, AdapterPriority.UIA: uia})
    with pytest.raises(TaskCancelledError):
        dispatcher({}, SimpleNamespace(cancellation_token=token))
    assert calls == []
