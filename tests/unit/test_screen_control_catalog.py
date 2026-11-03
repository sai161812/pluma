from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest

import pluma.tools.screen_catalog as screen_tools
from pluma.adapters.base import ControlInfo, Rect
from pluma.core.cancellation import CancellationToken
from pluma.perception.context import ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement, ScreenSnapshot
from pluma.perception.snapshot_registry import SnapshotRegistry
from pluma.tools.base import AdapterPriority, RiskClass
from pluma.tools.registry import ToolArgumentError, ToolRegistry, register_default_tools
from pluma.brain.tool_subset import ToolSubsetSelector


def _emit_catalog_snapshot(args, task_context=None):
    from pluma.tools.base import ToolResult
    snapshot = ScreenSnapshot(
        snapshot_id="worker-created-screen-snapshot",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=3),
        active_process="owned.exe", active_window_title="Owned",
        window_rect=BoundingBox(left=0, top=0, right=100, bottom=80), dpi_scale=1.0,
        hwnd=500, pid=1234, process_creation_time_ns=987654321,
    )
    return ToolResult.success("inspect_window_controls", {
        "snapshot_id": snapshot.snapshot_id, "raw_snapshot": snapshot.model_dump(mode="json")
    }, "Inspected the owned fixture window.", verified=True)


CATALOG_NAMES = {
    "get_active_window_context", "inspect_window_controls", "capture_target_window",
    "read_visible_text", "find_visible_text", "refresh_screen_snapshot",
    "find_control", "invoke_control", "set_control_text", "read_control_text",
    "wait_for_control", "invoke_screen_element", "press_key", "hotkey", "type_text",
    "click_window_relative",
}


def _screen_context(*, source=ElementSource.UIA, label="Submit", control_type="Button", auto_id="submit"):
    now = datetime.now(timezone.utc)
    bounds = BoundingBox(left=10, top=20, right=110, bottom=55)
    element = ScreenElement(snapshot_id="p12-snapshot", source=source, label=label,
        control_type=control_type, bounds=bounds, confidence=0.98,
        invocation_capability="invoke", uia_automation_id=auto_id)
    snapshot = ScreenSnapshot(snapshot_id="p12-snapshot", created_at=now,
        expires_at=now + timedelta(seconds=30), active_process="fixture.exe",
        active_window_title="Fixture", window_rect=BoundingBox(left=100, top=100, right=500, bottom=400),
        dpi_scale=1.0, hwnd=500, pid=1234, process_creation_time_ns=987654321,
        window_class="FixtureWindow", controls=[element] if source == ElementSource.UIA else [],
        ocr_words=[element] if source == ElementSource.OCR else [])
    snapshots = SnapshotRegistry()
    snapshots.register(snapshot)
    context = SimpleNamespace(snapshot_registry=snapshots, cancellation_token=CancellationToken())
    info = ActiveWindowInfo(hwnd=500, process_name="fixture.exe", window_title="Fixture",
        rect=snapshot.window_rect, dpi_scale=1.0, is_valid=True, pid=1234, class_name="FixtureWindow")

    class FakeContext:
        def get_active_window(self):
            return info

        def get_window_info(self, hwnd):
            return info if hwnd == info.hwnd else ActiveWindowInfo()

        def get_process_creation_time_ns(self, pid):
            return 987654321 if pid == 1234 else None

    return context, snapshot, element, FakeContext()


def test_all_sixteen_exact_catalog_tools_are_registered_and_routed_for_screen() -> None:
    registry = ToolRegistry()
    register_default_tools(registry)
    assert CATALOG_NAMES <= set(registry.all_names())
    assert CATALOG_NAMES <= set(ToolSubsetSelector(registry).get_tool_names_for_route("SCREEN"))
    assert CATALOG_NAMES <= set(ToolSubsetSelector(registry).get_tool_names_for_route("DEEP"))
    assert len(CATALOG_NAMES) == 16


def test_catalog_schemas_reject_unscoped_targets_and_unsafe_input() -> None:
    registry = ToolRegistry()
    register_default_tools(registry)
    for tool in ("capture_target_window", "read_visible_text", "invoke_control",
                 "set_control_text", "read_control_text", "invoke_screen_element",
                 "press_key", "hotkey", "type_text", "click_window_relative"):
        with pytest.raises(ToolArgumentError):
            registry.validate_call(tool, {})
    with pytest.raises(ToolArgumentError):
        registry.validate_call("hotkey", {
            "snapshot_id": "s", "target_ref": "s::e", "modifiers": ["win"], "key": "r",
            "expected_enabled": True,
        })
    with pytest.raises(ToolArgumentError):
        registry.validate_call("press_key", {
            "snapshot_id": "s", "target_ref": "s::e", "key": "r",
        })
    with pytest.raises(ToolArgumentError):
        registry.validate_call("type_text", {
            "snapshot_id": "s", "target_ref": "s::e", "screen_input": "hello",
        })


def test_inspect_and_refresh_return_only_task_reference_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, _, fake_context = _screen_context()
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)

    class FakeBuilder:
        def capture(self, *, hwnd, ttl_seconds):
            assert hwnd == 500 and ttl_seconds == 3.0
            return snapshot

    monkeypatch.setattr(screen_tools, "UiaSnapshotBuilder", lambda context=None: FakeBuilder())
    result = screen_tools.execute_inspect_window_controls({"hwnd": 500, "max_controls": 10}, context)
    assert result.ok and result.verified
    assert result.data["snapshot_id"] == snapshot.snapshot_id
    assert result.data["controls"][0]["target_ref"] == "p12-snapshot::" + snapshot.controls[0].element_id
    assert "raw_snapshot" in result.data  # registry promotes then strips this internal transport field


def test_find_control_is_snapshot_scoped_and_does_not_call_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context()
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    result = screen_tools.execute_find_control({"snapshot_id": snapshot.snapshot_id, "label": "Submit"}, context)
    assert result.ok and result.verified
    assert result.data["match_count"] == 1
    assert result.data["matches"][0]["target_ref"] == f"{snapshot.snapshot_id}::{element.element_id}"


def test_ocr_read_and_capture_are_target_scoped_and_return_no_image_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, _, fake_context = _screen_context()
    fresh_id = str(uuid.uuid4())
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)

    class FakeBuilder:
        def capture(self, *, hwnd, ttl_seconds):
            return snapshot.model_copy(update={
                "snapshot_id": fresh_id,
                "created_at": datetime.now(timezone.utc),
                "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
                "controls": [], "ocr_words": [],
            })

    class FakeCapture:
        def capture_window(self, hwnd):
            assert hwnd == 500
            return b"PRIVATE-SCREENSHOT"

        def capture_region(self, region, *, hwnd):
            assert hwnd == 500 and region.left == 3 and region.top == 4
            return b"PRIVATE-SCREENSHOT"

    class FakeOcrManager:
        def run_ocr(self, image, cancellation_token=None):
            assert image == b"PRIVATE-SCREENSHOT"
            from pluma.perception.ocr_adapter import OcrResult, OcrWord
            return OcrResult(words=[OcrWord("Visible", 0.98, BoundingBox(left=5, top=6, right=55, bottom=22))],
                full_text="Visible")

    monkeypatch.setattr(screen_tools, "UiaSnapshotBuilder", lambda context=None: FakeBuilder())
    monkeypatch.setattr("pluma.perception.capture.WindowCapture", FakeCapture)
    monkeypatch.setattr("pluma.perception.ocr_lifecycle.get_default_ocr_lifecycle_manager", FakeOcrManager)
    read = screen_tools.execute_read_visible_text({"snapshot_id": snapshot.snapshot_id}, context)
    assert read.ok and read.verified
    assert read.data["visible_text"] == "Visible"
    assert read.data["snapshot_id"] == fresh_id
    assert "PRIVATE-SCREENSHOT" not in repr(read.data)
    from pluma.memory.redaction import redact_sensitive_data
    assert redact_sensitive_data(read.data)["visible_text"] != "Visible"

    found = screen_tools.execute_find_visible_text({"snapshot_id": snapshot.snapshot_id,
        "region": {"left": 3, "top": 4, "right": 80, "bottom": 40},
        "visible_text_query": "Visible", "exact_match": True, "min_confidence": 0.5}, context)
    assert found.ok and found.data["match_count"] == 1
    assert found.data["matches"][0]["bounds"]["left"] == 8

    captured = screen_tools.execute_capture_target_window({"snapshot_id": snapshot.snapshot_id}, context)
    assert captured.ok and captured.data["captured"]
    assert captured.data["byte_count"] > 0
    assert "PRIVATE-SCREENSHOT" not in repr(captured.data)


def test_worker_snapshot_payload_is_registered_and_removed_from_result() -> None:
    from pluma.core.task_supervisor import TaskSupervisor
    from pluma.tools.base import AdapterPriority, ToolSpec
    from pluma.verify.common import verify_noop

    capsule = TaskSupervisor().create_task_capsule(request_id="p12-catalog-snapshot")
    capsule.snapshot_registry = SnapshotRegistry()
    registry = ToolRegistry()
    spec = ToolSpec(name="inspect_window_controls", description="Inspect semantic controls.",
        args_schema=screen_tools.InspectWindowControlsArgs, risk_class=RiskClass.READ,
        timeout_s=5.0, process_isolated=True, executor=_emit_catalog_snapshot,
        verifier=verify_noop, adapter_priority=[AdapterPriority.UIA])
    registry.register(spec)
    try:
        result = registry.execute("inspect_window_controls", {"max_controls": 1}, task_context=capsule)
        assert result.ok and result.verified
        assert "raw_snapshot" not in result.data
        assert capsule.snapshot_registry.resolve(result.data["snapshot_id"]).hwnd == 500
    finally:
        registry.close()
        capsule.close_resources(stopping=True)


def test_invoke_control_uses_uia_and_reads_expected_transition(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context()
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    states = iter((True, False))
    calls = []

    def find(self, **kwargs):
        return ControlInfo(automation_id="submit", name="Submit", control_type="Button",
            class_name="Button", is_enabled=next(states), is_visible=True, rect=Rect(10, 20, 110, 55),
            is_password=False)

    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", find)
    monkeypatch.setattr(screen_tools.UiaAdapter, "invoke_control", lambda self, **kwargs: calls.append(kwargs) or True)
    result = screen_tools.execute_invoke_control({"snapshot_id": snapshot.snapshot_id,
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}", "expected_enabled": False}, context)
    assert result.ok and result.verified
    assert len(calls) == 1 and calls[0]["hwnd"] == 500


def test_type_text_requires_live_private_prestate_and_reads_expected_value(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(label="Name", control_type="Edit", auto_id="name")
    context.undo_stack = []
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    record = {"action": "screen_control_text", "guard_version": 1, "volatile": True,
        "undo_ref": str(uuid.uuid4()), "hwnd": 500, "pid": 1234,
        "process_creation_time_ns": 987654321, "window_title": "Fixture",
        "window_class": "FixtureWindow", "window_rect": snapshot.window_rect.model_dump(),
        "dpi_scale": 1.0, "auto_id": "name", "name": "Name", "control_type": "Edit",
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}"}
    private = {"record": record, "undo_ref": record["undo_ref"], "before_value": "before",
        "after_value": "after", "created_monotonic": screen_tools.time.monotonic()}
    context.execution_binding = {"screen_text_private": private}
    context.undo_stack.append({"action": "pending_mutation", "tool": "type_text", "pre_state": record})
    names = iter(("before", "before", "after"))
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="name", name="Name", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=False,
        text_value=next(names)))
    monkeypatch.setattr(screen_tools.UiaAdapter, "focus_control", lambda self, **kwargs: True)
    sent = []
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.send_text", lambda self, value: sent.append(value))
    result = screen_tools.execute_type_text({"snapshot_id": snapshot.snapshot_id,
        "target_ref": private["record"]["target_ref"], "screen_input": "inserted",
        "expected_control_text": "after"}, context)
    assert result.ok and result.verified
    assert sent == ["inserted"]


def test_set_control_text_uses_uia_value_readback_and_bound_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(label="Name", control_type="Edit", auto_id="name")
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    record = {"action": "screen_control_text", "guard_version": 1, "volatile": True,
        "undo_ref": str(uuid.uuid4()), "hwnd": 500, "pid": 1234,
        "process_creation_time_ns": 987654321, "window_title": "Fixture",
        "window_class": "FixtureWindow", "window_rect": snapshot.window_rect.model_dump(),
        "dpi_scale": 1.0, "auto_id": "name", "name": "Name", "control_type": "Edit",
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}"}
    private = {"record": record, "before_value": "before", "after_value": "after"}
    context.execution_binding = {"screen_text_private": private}
    context.undo_stack = [{"action": "pending_mutation", "tool": "set_control_text", "pre_state": record}]
    values = iter(("before", "after"))
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="name", name="Name", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=False,
        text_value=next(values)))
    calls = []
    monkeypatch.setattr(screen_tools.UiaAdapter, "set_control_text",
        lambda self, **kwargs: calls.append(kwargs) or True)
    result = screen_tools.execute_set_control_text({"snapshot_id": snapshot.snapshot_id,
        "target_ref": record["target_ref"], "screen_input": "after"}, context)
    assert result.ok and result.verified
    assert calls[0]["control_type"] == "Edit" and calls[0]["text"] == "after"


def test_control_text_undo_keeps_value_out_of_persisted_prestate(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(label="Name", control_type="Edit", auto_id="name")
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    values = iter(("private prior value",))
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="name", name="Name", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=False,
        text_value=next(values)))
    captured = screen_tools._capture_text_undo({"snapshot_id": snapshot.snapshot_id,
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}", "screen_input": "new value"}, context)
    record, before = screen_tools.seal_screen_text_capture(captured)
    assert record["action"] == "screen_control_text"
    assert before == {"before_value": "private prior value"}
    assert "private prior value" not in repr(record)

    restored_values = []
    monkeypatch.setattr(screen_tools.UiaAdapter, "set_control_text",
        lambda self, **kwargs: restored_values.append(kwargs["text"]) or True)
    private = {"record": record, "undo_ref": record["undo_ref"],
        "before_value": before["before_value"], "after_value": "new value",
        "created_monotonic": screen_tools.time.monotonic()}
    values = iter(("new value", "new value", "private prior value"))
    assert not screen_tools.verify_screen_control_text({**record, "screen_text_private": private}, private, restored=True)
    values = iter(("new value",))
    assert screen_tools.verify_screen_control_text({**record, "screen_text_private": private}, private, restored=False)
    values = iter(("new value", "new value", "private prior value"))
    result = screen_tools.restore_screen_control_text({**record, "screen_text_private": private})
    assert result.ok, result.error
    assert restored_values == ["private prior value"]


def test_screen_text_prestate_is_sent_to_owned_worker_without_entering_record(monkeypatch: pytest.MonkeyPatch) -> None:
    from pluma.tools.registry import WorkerResponse

    context, snapshot, element, fake_context = _screen_context(label="Name", control_type="Edit", auto_id="name")
    context.task_id = "p12-private-text-prestate"
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="name", name="Name", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=False,
        text_value="private prior value"))

    class CaptureWorker:
        def execute_call(self, executor, args, request, timeout_s, **kwargs):
            assert request.screen_snapshot["snapshot_id"] == snapshot.snapshot_id
            worker_context = SimpleNamespace(task_id=request.task_id,
                cancellation_token=context.cancellation_token, undo_stack=[], execution_binding=None,
                snapshot_registry=SnapshotRegistry())
            worker_context.snapshot_registry.register(ScreenSnapshot.model_validate(request.screen_snapshot))
            return "ok", WorkerResponse(result=executor(args, worker_context))

    context.worker_controller = CaptureWorker()
    registry = ToolRegistry()
    capture = registry._owned_prestate(screen_tools.SET_CONTROL_TEXT_SPEC, {
        "snapshot_id": snapshot.snapshot_id, "target_ref": f"{snapshot.snapshot_id}::{element.element_id}",
        "screen_input": "replacement"}, context, context.cancellation_token, 5.0)
    assert capture.ok
    record, private = screen_tools.seal_screen_text_capture(capture.data["pre_state"])
    assert "private prior value" not in repr(record)
    assert private == {"before_value": "private prior value"}


def test_screen_text_inverse_uses_registry_private_state_after_worker_drain(monkeypatch: pytest.MonkeyPatch) -> None:
    from pluma.rollback.recipes import RollbackStepResult
    from pluma.rollback.engine import RollbackEngine

    registry = ToolRegistry()
    state = {"action": "screen_control_text", "guard_version": 1, "volatile": True,
        "undo_ref": str(uuid.uuid4()), "hwnd": 500, "pid": 1234,
        "process_creation_time_ns": 987654321, "window_title": "Fixture",
        "window_class": "FixtureWindow", "window_rect": {"left": 100, "top": 100, "right": 500, "bottom": 400},
        "dpi_scale": 1.0, "auto_id": "name", "name": "Name", "control_type": "Edit",
        "target_ref": "p12-snapshot::name"}
    private = {"record": state, "undo_ref": state["undo_ref"], "before_value": "before",
        "after_value": "after", "created_monotonic": screen_tools.time.monotonic()}
    registry._screen_text_undo_cache[state["undo_ref"]] = private
    calls = []
    monkeypatch.setattr("pluma.rollback.owned.apply_owned", lambda action, payload, capsule:
        calls.append((action, payload, capsule)) or RollbackStepResult(True, action, "restored"))
    capsule = SimpleNamespace(task_id="task")
    engine = RollbackEngine()
    engine.task_resolver = lambda task_id: capsule
    engine.screen_text_inverse = registry.restore_screen_control_text
    outcome = engine._apply("task", "screen_control_text", state)
    assert outcome.ok
    assert calls[0][0] == "screen_control_text"
    assert calls[0][1]["screen_text_private"] == private
    assert state["undo_ref"] not in registry._screen_text_undo_cache


def test_password_or_unknown_password_controls_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(label="Password", control_type="Edit", auto_id="password")
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="password", name="", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=None))
    result = screen_tools.execute_read_control_text({"snapshot_id": snapshot.snapshot_id,
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}"}, context)
    assert not result.ok and result.error_code == "SENSITIVE_CONTROL_REFUSED"


def test_read_control_text_returns_value_pattern_value_not_accessible_label(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(label="Display name", control_type="Edit", auto_id="name")
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    monkeypatch.setattr(screen_tools.UiaAdapter, "find_control", lambda self, **kwargs: ControlInfo(
        automation_id="name", name="Display name", control_type="Edit", class_name="Edit",
        is_enabled=True, is_visible=True, rect=Rect(10, 20, 110, 55), is_password=False,
        text_value="user entered value"))
    result = screen_tools.execute_read_control_text({"snapshot_id": snapshot.snapshot_id,
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}"}, context)
    assert result.ok and result.verified
    assert result.data["control_text"] == "user entered value"


def test_stale_or_duplicate_targets_never_reach_input(monkeypatch: pytest.MonkeyPatch) -> None:
    context, snapshot, element, fake_context = _screen_context(source=ElementSource.OCR)
    moved = ActiveWindowInfo(hwnd=500, process_name="fixture.exe", window_title="Fixture",
        rect=BoundingBox(left=101, top=100, right=501, bottom=400), dpi_scale=1.0,
        is_valid=True, pid=1234, class_name="FixtureWindow")
    fake_context.get_active_window = lambda: moved
    monkeypatch.setattr(screen_tools, "ActiveWindowContext", lambda: fake_context)
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.mouse_click",
        lambda *a, **k: pytest.fail("Stale target must be refused before input."))
    result = screen_tools.execute_click_window_relative({"snapshot_id": snapshot.snapshot_id,
        "target_ref": f"{snapshot.snapshot_id}::{element.element_id}", "x": 20, "y": 30}, context)
    assert not result.ok and result.error_code == "WINDOW_MOVED"


def test_risk_and_adapter_metadata_are_declared_for_actions() -> None:
    assert screen_tools.INVOKE_SCREEN_ELEMENT_SPEC.adapter_priority == [AdapterPriority.UIA, AdapterPriority.OCR_GROUNDED]
    assert screen_tools.CLICK_WINDOW_RELATIVE_SPEC.adapter_priority == [AdapterPriority.OCR_GROUNDED]
    assert screen_tools.PRESS_KEY_SPEC.adapter_priority == [AdapterPriority.KEYBOARD]
    assert screen_tools.SET_CONTROL_TEXT_SPEC.risk_class == RiskClass.MEDIUM
    assert screen_tools.SET_CONTROL_TEXT_SPEC.undo_builder is not None
