"""Failure regressions for P12 input grounding and truthful inspection."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import sys

import pytest

import pluma.tools.screen_catalog as screen
from pluma.adapters.base import ControlInfo, Rect
from pluma.perception.context import ActiveWindowInfo
from tests.unit.test_screen_control_catalog import _screen_context


def _control(enabled=True):
    return ControlInfo(automation_id="submit", name="Submit", control_type="Button",
        class_name="Button", is_enabled=enabled, is_visible=True,
        rect=Rect(10, 20, 110, 55), is_password=False)


@pytest.mark.parametrize("denial", [PermissionError("denied"), OSError(-2147024891, "denied")])
def test_denied_inspection_is_not_verified_empty_success(monkeypatch, denial):
    ctx, _, _, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    def denied(*args, **kwargs):
        raise denial
    monkeypatch.setitem(sys.modules, "pywinauto", SimpleNamespace(Application=denied))
    result = screen.execute_inspect_window_controls({"hwnd": 500, "max_controls": 10}, ctx)
    assert not result.ok and not result.verified
    assert result.error_code == "ACCESS_DENIED"


@pytest.mark.parametrize("tool", ["press_key", "hotkey"])
@pytest.mark.parametrize("change", ["foreground", "expiry", "geometry", "process"])
def test_changes_during_focus_prevent_global_input(monkeypatch, tool, change):
    ctx, snap, element, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    monkeypatch.setattr(screen.UiaAdapter, "find_control", lambda self, **kwargs: _control())
    def focus(self, **kwargs):
        if change == "expiry":
            ctx.snapshot_registry._snapshots[snap.snapshot_id] = snap.model_copy(update={
                "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        elif change == "process":
            native.get_process_creation_time_ns = lambda pid: 100
        elif change == "geometry":
            prior = native.get_active_window()
            prior.rect = BoundingBox(left=101, top=100, right=501, bottom=400)
        else:
            native.get_active_window = lambda: ActiveWindowInfo()
        return True
    from pluma.perception.element_refs import BoundingBox
    monkeypatch.setattr(screen.UiaAdapter, "focus_control", focus)
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.press_key",
        lambda *args: pytest.fail("Stale target reached SendInput"))
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.send_hotkey",
        lambda *args: pytest.fail("Stale target reached SendInput"))
    args = {"snapshot_id": snap.snapshot_id, "target_ref": f"{snap.snapshot_id}::{element.element_id}",
            "key": "enter", "expected_enabled": False}
    if tool == "hotkey":
        args["modifiers"] = ["ctrl"]
    result = getattr(screen, "execute_" + tool)(args, ctx)
    assert not result.ok and not result.verified


def test_already_present_input_postcondition_refuses_before_focus(monkeypatch):
    ctx, snap, element, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    monkeypatch.setattr(screen.UiaAdapter, "find_control", lambda self, **kwargs: _control())
    monkeypatch.setattr(screen.UiaAdapter, "focus_control", lambda *a, **k: pytest.fail("No-op must not focus"))
    result = screen.execute_press_key({"snapshot_id": snap.snapshot_id,
        "target_ref": f"{snap.snapshot_id}::{element.element_id}", "key": "enter",
        "expected_enabled": True}, ctx)
    assert not result.ok and not result.verified
    assert result.error_code == "UI_NO_EXPECTED_TRANSITION"


def test_failed_sendinput_never_reads_back_success(monkeypatch):
    from pluma.adapters.input import InputAdapter
    ctx, snap, element, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    monkeypatch.setattr(screen.UiaAdapter, "find_control", lambda self, **kwargs: _control())
    monkeypatch.setattr(screen.UiaAdapter, "focus_control", lambda self, **kwargs: True)
    adapter = InputAdapter()
    adapter._user32 = SimpleNamespace(SendInput=lambda *args: 0)
    monkeypatch.setattr("pluma.adapters.input.InputAdapter", lambda: adapter)
    result = screen.execute_press_key({"snapshot_id": snap.snapshot_id,
        "target_ref": f"{snap.snapshot_id}::{element.element_id}", "key": "enter",
        "expected_enabled": False}, ctx)
    assert not result.ok and not result.verified
    assert result.error_code == "INPUT_ACTION_FAILED"


def test_target_change_during_lookup_prevents_uia_invoke(monkeypatch):
    ctx, snap, element, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    def find(self, **kwargs):
        native.get_active_window = lambda: ActiveWindowInfo()
        return _control()
    monkeypatch.setattr(screen.UiaAdapter, "find_control", find)
    monkeypatch.setattr(screen.UiaAdapter, "invoke_control", lambda *a, **k: pytest.fail("Changed target invoked"))
    result = screen.execute_invoke_control({"snapshot_id": snap.snapshot_id,
        "target_ref": f"{snap.snapshot_id}::{element.element_id}", "expected_enabled": False}, ctx)
    assert not result.ok and not result.verified


def test_wait_refuses_recycled_window_identity(monkeypatch):
    ctx, snap, _, native = _screen_context()
    monkeypatch.setattr(screen, "ActiveWindowContext", lambda: native)
    replacement = snap.model_copy(update={"pid": 999, "process_creation_time_ns": 100})
    monkeypatch.setattr(screen, "UiaSnapshotBuilder", lambda: SimpleNamespace(capture=lambda **kwargs: replacement))
    result = screen.execute_find_control_wait({"snapshot_id": snap.snapshot_id,
        "label": "Submit", "timeout_ms": 100}, ctx)
    assert not result.ok and result.error_code == "WINDOW_MISMATCH"


@pytest.mark.parametrize("stage", ["device_context", "window_context", "pixel_copy", "bitmap_read"])
def test_target_capture_failure_never_returns_a_blank_success(monkeypatch, stage):
    from unittest.mock import MagicMock
    from pluma.adapters.base import AdapterError
    from pluma.adapters.screen import ScreenAdapter
    adapter = ScreenAdapter.__new__(ScreenAdapter)
    adapter._win32 = SimpleNamespace(is_window=lambda hwnd: True, get_window_rect=lambda hwnd: Rect(0, 0, 100, 100))
    adapter._user32 = MagicMock()
    adapter._gdi32 = MagicMock()
    adapter._user32.GetDC.return_value = 0 if stage == "device_context" else 1
    adapter._user32.PrintWindow.return_value = 1 if stage == "bitmap_read" else 0
    adapter._user32.GetWindowDC.return_value = 0 if stage == "window_context" else 2
    adapter._gdi32.CreateCompatibleDC.return_value = 3
    adapter._gdi32.CreateCompatibleBitmap.return_value = 4
    adapter._gdi32.SelectObject.return_value = 5
    adapter._gdi32.BitBlt.return_value = 0
    adapter._gdi32.GetDIBits.return_value = 0
    monkeypatch.setattr(adapter, "_create_blank_bmp_bytes", lambda *args: pytest.fail("Synthetic image must not replace failed capture"))
    with pytest.raises(AdapterError):
        adapter.capture_window(500)


def test_ocr_action_cannot_bypass_a_semantic_control(monkeypatch):
    from pluma.tools.ui import execute_click_ocr_text
    ctx, snap, _, native = _screen_context()
    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: native)
    monkeypatch.setattr("pluma.tools.ui.UiaSnapshotBuilder", lambda **kwargs:
        SimpleNamespace(capture=lambda **kwargs: snap))
    monkeypatch.setattr("pluma.perception.capture.WindowCapture.capture_window",
        lambda *args: pytest.fail("Semantic target must not trigger OCR capture"))
    result = execute_click_ocr_text({"text": "Submit", "hwnd": 500}, ctx)
    assert not result.ok and result.error_code == "UIA_TARGET_AVAILABLE"


def test_legacy_click_rechecks_process_after_lookup(monkeypatch):
    from pluma.tools.ui import execute_click_element
    ctx, snap, element, native = _screen_context()
    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: native)
    ctx.grounded_ui_target = {"snapshot_hwnd": snap.hwnd, "snapshot_pid": snap.pid,
        "snapshot_creation_time_ns": snap.process_creation_time_ns, "snapshot_dpi_scale": snap.dpi_scale,
        "auto_id": element.uia_automation_id, "name": element.label, "control_type": element.control_type}
    def find(self, **kwargs):
        native.get_process_creation_time_ns = lambda pid: None
        return _control()
    monkeypatch.setattr(screen.UiaAdapter, "find_control", find)
    monkeypatch.setattr(screen.UiaAdapter, "invoke_control", lambda *args, **kwargs: pytest.fail("Recycled process must not be invoked"))
    result = execute_click_element({"snapshot_id": snap.snapshot_id,
        "target_ref": f"{snap.snapshot_id}::{element.element_id}", "expected_enabled": False}, ctx)
    assert not result.ok and not result.verified


def test_legacy_text_alias_refuses_without_private_undo():
    from pluma.tools.ui import execute_type_into_element, TYPE_INTO_ELEMENT_SPEC
    assert TYPE_INTO_ELEMENT_SPEC.undo_builder is not None
    assert TYPE_INTO_ELEMENT_SPEC.process_isolated
    result = execute_type_into_element({"text": "new", "snapshot_id": "s", "target_ref": "s::e"})
    assert not result.ok and result.error_code == "SCREEN_TEXT_UNDO_UNAVAILABLE"


@pytest.mark.parametrize("failure,expected", [("partial_label", "OCR_NO_MATCH"), ("low_confidence", "OCR_NO_MATCH"),
    ("expired", "STALE_SNAPSHOT"), ("title", "WINDOW_MISMATCH"), ("dpi", "DPI_MISMATCH")])
def test_ocr_requires_exact_current_label_and_bounded_pixel_age(monkeypatch, failure, expected):
    import pluma.tools.ui as ui
    from pluma.perception.ocr_adapter import OcrResult, OcrWord
    from pluma.perception.element_refs import BoundingBox
    ctx, _, _, native = _screen_context()
    monkeypatch.setattr(ui, "ActiveWindowContext", lambda: native)
    monkeypatch.setattr(ui, "UiaSnapshotBuilder", lambda **kwargs:
        SimpleNamespace(capture=lambda **kwargs: SimpleNamespace(controls=[])))
    monkeypatch.setattr("pluma.perception.capture.WindowCapture.capture_window", lambda *a: b"fixture")
    def recognize(image, cancellation_token=None):
        if failure == "title":
            native.get_active_window().window_title = "Changed"
        if failure == "dpi":
            native.get_active_window().dpi_scale = 1.01
        return OcrResult(words=[OcrWord("Save As" if failure == "partial_label" else "Save",
            0.85 if failure == "low_confidence" else 0.99, BoundingBox(left=10, top=10, right=70, bottom=40))])
    monkeypatch.setattr("pluma.perception.ocr_lifecycle.get_default_ocr_lifecycle_manager", lambda:
        SimpleNamespace(run_ocr=recognize))
    if failure == "expired":
        clock = iter((0.0, 4.0))
        monkeypatch.setattr(ui, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.mouse_click", lambda *a:
        pytest.fail("Invalid OCR observation reached input"))
    result = ui.execute_click_ocr_text({"text": "Save", "hwnd": 500}, ctx)
    assert not result.ok and not result.verified and result.error_code == expected


def test_all_legacy_perception_actions_require_an_owned_process_boundary():
    from pluma.tools.ui import INSPECT_ACTIVE_WINDOW_SPEC, CLICK_ELEMENT_SPEC, TYPE_INTO_ELEMENT_SPEC
    assert all(spec.process_isolated for spec in (INSPECT_ACTIVE_WINDOW_SPEC, CLICK_ELEMENT_SPEC, TYPE_INTO_ELEMENT_SPEC))


def test_legacy_clicks_cannot_bypass_policy_or_irreversible_intent():
    from pluma.tools.ui import CLICK_ELEMENT_SPEC, CLICK_OCR_TEXT_SPEC
    from pluma.tools.base import RiskClass
    from pluma.tools.registry import ToolRegistry
    ctx, snap, element, _ = _screen_context()
    for spec, args in [(CLICK_ELEMENT_SPEC, {"snapshot_id": snap.snapshot_id,
            "target_ref": f"{snap.snapshot_id}::{element.element_id}", "expected_enabled": False}),
            (CLICK_OCR_TEXT_SPEC, {"text": "Save", "hwnd": 500})]:
        assert spec.risk_class == RiskClass.HIGH and spec.non_undoable and spec.undo_builder is not None
        registry = ToolRegistry()
        registry.register(spec)
        try:
            result = registry.execute(spec.name, args, ctx)
            assert not result.ok and result.error_code == "POLICY_REQUIRED"
        finally:
            registry.close()


def test_planner_cannot_lower_action_ocr_confidence():
    from pydantic import ValidationError
    from pluma.tools.ui import ClickOcrTextArgs
    with pytest.raises(ValidationError):
        ClickOcrTextArgs(text="Save", min_confidence=0.5)


def _denied_initial_observation(args, task_context):
    from pluma.tools.base import ToolResult
    return ToolResult.failure("inspect_window_controls", "Windows denied UI Automation access.", "ACCESS_DENIED")


@pytest.mark.parametrize("route", ["SCREEN", "DEEP"])
@pytest.mark.parametrize("denied", [False, True])
def test_routed_perception_is_owned_uia_only_and_registered_before_planning(tmp_path, monkeypatch, route, denied):
    from unittest.mock import MagicMock
    from pluma.brain.schemas import Plan, ToolCall, RouteMode
    from pluma.core.orchestrator import Orchestrator
    from pluma.core.request import PlumaRequest
    from pluma.core.router import RouteResult
    from pluma.core.task_supervisor import TaskSupervisor
    from pluma.tools.registry import ToolRegistry, register_default_tools
    from tests.unit.test_multi_step_orchestrator import _owned_semantic_fixture
    registry = ToolRegistry()
    register_default_tools(registry)
    monkeypatch.setattr(registry.lookup("inspect_window_controls"), "executor",
        _denied_initial_observation if denied else _owned_semantic_fixture)
    route_enum = RouteMode(route)
    observed = []
    def plan(**kwargs):
        snapshot = kwargs["screen_snapshot"]
        capsule = kwargs["cancellation_token"]._capsule()
        assert capsule.snapshot_registry.resolve(snapshot.snapshot_id) == snapshot
        assert snapshot.ocr_words == []
        observed.append(snapshot.snapshot_id)
        return Plan(route=route_enum, steps=[ToolCall(tool="list_files", arguments={"path": str(tmp_path)},
            purpose="Read only the isolated fixture directory")])
    planner = SimpleNamespace(plan=MagicMock(side_effect=plan))
    supervisor = TaskSupervisor()
    router = SimpleNamespace(route=lambda request: RouteResult(route=route_enum, reason="Typed screen fixture"))
    orchestrator = Orchestrator(registry=registry, supervisor=supervisor, router=router, llm_manager=planner)
    try:
        result = orchestrator.execute(PlumaRequest(input_mode="text", text="Inspect this owned screen"))
        if denied:
            assert not result.success and "denied" in result.error.lower()
            planner.plan.assert_not_called()
        else:
            assert result.success, result.error
            assert len(observed) == 1
            planner.plan.assert_called_once()
    finally:
        supervisor.stop_all_active_tasks()
        registry.close()
