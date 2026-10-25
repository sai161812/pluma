"""tests/unit/test_ocr_grounding_integration.py — Phase 8: OCR grounding & click_ocr_text tool tests."""

from __future__ import annotations

import os
from pathlib import Path
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest
import psutil
from pydantic import BaseModel

from pluma.adapters.base import Rect
from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.context import ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement, ScreenSnapshot
from pluma.perception.ocr_adapter import OcrResult, OcrWord
from pluma.tools.ui import (
    ALL_UI_TOOLS,
    CLICK_OCR_TEXT_SPEC,
    ClickOcrTextArgs,
    execute_click_ocr_text,
)
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult


@pytest.fixture(autouse=True)
def no_semantic_target_for_ocr_failure_fixtures(monkeypatch):
    """These OCR fixtures intentionally model text unavailable through UIA."""
    monkeypatch.setattr("pluma.tools.ui.UiaSnapshotBuilder", lambda **kwargs:
        SimpleNamespace(capture=lambda **kwargs: SimpleNamespace(controls=[])))


class _SnapshotProbeArgs(BaseModel):
    snapshot_id: str


def _p12_snapshot_probe_executor(args, task_context):
    snapshot = task_context.snapshot_registry.resolve(args["snapshot_id"])
    return ToolResult(
        ok=True,
        tool="p12_snapshot_probe",
        data={
            "snapshot_id": snapshot.snapshot_id,
            "hwnd": snapshot.hwnd,
            "image_ref": snapshot.image_ref,
        },
        factual_message="Worker resolved the task-scoped screen snapshot.",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="snapshot_registry", detail="Snapshot resolved."),
    )


def _p12_snapshot_probe_verifier(result):
    matches = result.data == {
        "snapshot_id": "p12-worker-snapshot", "hwnd": 555, "image_ref": None,
    }
    return VerifyResult(
        ok=matches,
        method="snapshot_registry",
        detail="Worker snapshot metadata matches." if matches else "Worker snapshot metadata differs.",
    )


def _p12_e10_blocking_ocr_executor(args, task_context):
    """Run the real OCR-click executor with an intentionally stuck OCR backend."""
    from unittest.mock import patch
    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture
    from pluma.tools.ui import execute_click_ocr_text

    marker = Path(os.environ["PLUMA_P12_E10_MARKER"])
    target = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )

    class OwnedContext:
        def get_active_window(self):
            return target

        def get_window_info(self, hwnd):
            return target if hwnd == target.hwnd else ActiveWindowInfo()

        def get_process_creation_time_ns(self, pid):
            return 1_000_000_000 if pid == target.pid else None

    def block_during_ocr(self, image_bytes, cancellation_token=None):
        marker.write_text(str(os.getpid()), encoding="ascii")
        time.sleep(60)  # Intentionally uncooperative; STOP must terminate the owned worker.
        return OcrResult(words=[OcrWord(
            text="Submit", confidence=0.99,
            bounds=BoundingBox(left=20, top=30, right=100, bottom=55),
        )])

    def record_click(self, x, y):
        marker.with_suffix(".click").write_text(f"{x},{y}", encoding="ascii")

    with (
        patch("pluma.tools.ui.ActiveWindowContext", OwnedContext),
        patch("pluma.tools.ui.UiaSnapshotBuilder", lambda **kwargs:
            SimpleNamespace(capture=lambda **kwargs: SimpleNamespace(controls=[]))),
        patch.object(WindowCapture, "capture_window", lambda self, hwnd: b"BM_PRIVATE"),
        patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr", block_during_ocr),
        patch.object(InputAdapter, "mouse_click", record_click),
    ):
        return execute_click_ocr_text(args, task_context)


def test_click_ocr_text_spec_registration() -> None:
    assert CLICK_OCR_TEXT_SPEC.name == "click_ocr_text"
    assert CLICK_OCR_TEXT_SPEC in ALL_UI_TOOLS
    assert CLICK_OCR_TEXT_SPEC.cancellable
    assert CLICK_OCR_TEXT_SPEC.process_isolated


def test_process_isolated_screen_tool_receives_only_registered_snapshot_metadata() -> None:
    from datetime import datetime, timedelta, timezone
    from pluma.core.task_supervisor import TaskCapsule
    from pluma.perception.snapshot_registry import SnapshotRegistry
    from pluma.tools.registry import ToolRegistry

    task_context = TaskCapsule(request_id="p12-snapshot-worker")
    task_context.snapshot_registry = SnapshotRegistry()
    task_context.snapshot_registry.register(ScreenSnapshot(
        snapshot_id="p12-worker-snapshot",
        created_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        active_process="owned_fixture.exe",
        active_window_title="Owned fixture",
        window_rect=BoundingBox(left=10, top=20, right=410, bottom=260),
        dpi_scale=1.0,
        hwnd=555,
        pid=1234,
        process_creation_time_ns=987654321,
        image_ref="private-test-capture.bmp",
    ))
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name="p12_snapshot_probe",
        description="Resolve an approved task-scoped screen snapshot in a worker.",
        args_schema=_SnapshotProbeArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=_p12_snapshot_probe_executor,
        verifier=_p12_snapshot_probe_verifier,
    ))
    try:
        result = registry.execute(
            "p12_snapshot_probe",
            {"snapshot_id": "p12-worker-snapshot"},
            task_context=task_context,
        )
        assert result.ok and result.verified, result.factual_message
        assert result.data == {
            "snapshot_id": "p12-worker-snapshot", "hwnd": 555, "image_ref": None,
        }
    finally:
        registry.close()
        task_context.close_resources(stopping=True)


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_execute_click_ocr_text_success(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500,
        process_name="custom_app.exe",
        window_title="Custom Dashboard",
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
        is_valid=True,
        pid=12345,
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.side_effect = [
        OcrResult(words=[OcrWord(
            text="Export Report", confidence=0.96,
            bounds=BoundingBox(left=200, top=300, right=300, bottom=340),
        )]),
        OcrResult(words=[]),
    ]

    result = execute_click_ocr_text({"text": "Export Report"})

    assert result.ok
    assert "Export Report" in result.factual_message
    assert result.data["matched_text"] == "Export Report"
    assert result.data["confidence"] == 0.96

    # Center of word: x = (200+300)//2 = 250, y = (300+340)//2 = 320
    # Desktop coordinates: desktop_x = 100 + 250 = 350, desktop_y = 100 + 320 = 420
    assert result.data["window_rel_x"] == 250
    assert result.data["window_rel_y"] == 320
    assert result.data["desktop_x"] == 350
    assert result.data["desktop_y"] == 420

    mock_mouse_click.assert_called_once_with(350, 420)
    assert mock_run_ocr.call_count == 2


@pytest.mark.parametrize(
    ("changed_info", "current_creation_time_ns", "expected_error"),
    [
        (
            ActiveWindowInfo(
                hwnd=500,
                process_name="custom_app.exe",
                window_title="Custom Dashboard",
                rect=BoundingBox(left=120, top=100, right=920, bottom=700),
                dpi_scale=1.0,
                is_valid=True,
                pid=12345,
            ),
            1_000_000_000,
            "WINDOW_MOVED",
        ),
        (
            ActiveWindowInfo(
                hwnd=500,
                process_name="custom_app.exe",
                window_title="Custom Dashboard",
                rect=BoundingBox(left=100, top=100, right=900, bottom=700),
                dpi_scale=1.5,
                is_valid=True,
                pid=12345,
            ),
            1_000_000_000,
            "DPI_MISMATCH",
        ),
        (
            ActiveWindowInfo(
                hwnd=500,
                process_name="other_app.exe",
                window_title="Custom Dashboard",
                rect=BoundingBox(left=100, top=100, right=900, bottom=700),
                dpi_scale=1.0,
                is_valid=True,
                pid=54321,
            ),
            1_000_000_000,
            "PROCESS_MISMATCH",
        ),
        (
            ActiveWindowInfo(
                hwnd=500,
                process_name="custom_app.exe",
                window_title="Custom Dashboard",
                rect=BoundingBox(left=100, top=100, right=900, bottom=700),
                dpi_scale=1.0,
                is_valid=True,
                pid=12345,
            ),
            2_000_000_000,
            "PROCESS_IDENTITY_MISMATCH",
        ),
    ],
)
@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_execute_click_ocr_text_refreshes_geometry_and_dpi_before_coordinate_fallback(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
    changed_info: ActiveWindowInfo,
    current_creation_time_ns: int,
    expected_error: str,
) -> None:
    original_info = ActiveWindowInfo(
        hwnd=500,
        process_name="custom_app.exe",
        window_title="Custom Dashboard",
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
        dpi_scale=1.0,
        is_valid=True,
        pid=12345,
    )
    mock_context = MagicMock()
    mock_context.get_active_window.side_effect = [original_info, changed_info]
    mock_context.get_process_creation_time_ns.side_effect = [1_000_000_000, current_creation_time_ns]
    mock_context_cls.return_value = mock_context
    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(
        words=[
            OcrWord(
                text="Export Report",
                confidence=0.96,
                bounds=BoundingBox(left=200, top=300, right=300, bottom=340),
            )
        ]
    )

    result = execute_click_ocr_text({"text": "Export Report"})

    assert not result.ok
    assert not result.verified
    assert result.error_code == expected_error
    assert mock_context.get_active_window.call_count == 2
    mock_mouse_click.assert_not_called()


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
def test_execute_click_ocr_text_no_match(
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345, rect=BoundingBox(left=0, top=0, right=800, bottom=600)
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(words=[])

    result = execute_click_ocr_text({"text": "NonExistentText", "hwnd": 500})
    assert not result.ok
    assert result.error == "OCR_NO_MATCH"
    assert "no text matching" in result.factual_message


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
def test_execute_click_ocr_text_ambiguous_duplicate_labels(
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345, rect=BoundingBox(left=0, top=0, right=800, bottom=600)
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(
        words=[
            OcrWord(text="Delete", confidence=0.9, bounds=BoundingBox(left=10, top=10, right=50, bottom=30)),
            OcrWord(text="Delete", confidence=0.9, bounds=BoundingBox(left=10, top=60, right=50, bottom=80)),
        ]
    )

    # Both exact labels match; the action must refuse to choose between them.
    result = execute_click_ocr_text({"text": "Delete", "hwnd": 500})
    assert not result.ok
    assert result.error == "OCR_AMBIGUOUS"
    assert "Ambiguous OCR result" in result.factual_message


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_region")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_execute_click_ocr_text_with_region_offset(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_region: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
        is_valid=True,
        pid=12345,
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context

    mock_capture_region.return_value = b"BM_BYTES"
    mock_run_ocr.side_effect = [
        OcrResult(words=[OcrWord(
            text="Apply", confidence=0.99,
            bounds=BoundingBox(left=10, top=20, right=50, bottom=40),
        )]),
        OcrResult(words=[]),
    ]

    # Sub-region at window-rel (50, 100, 300, 400)
    region_arg = {"left": 50, "top": 100, "right": 300, "bottom": 400}
    result = execute_click_ocr_text({"text": "Apply", "hwnd": 500, "region": region_arg})

    assert result.ok
    # Word center inside region: x = (10+50)//2 = 30, y = (20+40)//2 = 30
    # Region offset: left=50, top=100 -> Window-relative: x = 30+50 = 80, y = 30+100 = 130
    # Desktop absolute: 100+80 = 180, 100+130 = 230
    assert result.data["window_rel_x"] == 80
    assert result.data["window_rel_y"] == 130
    assert result.data["desktop_x"] == 180
    assert result.data["desktop_y"] == 230
    mock_mouse_click.assert_called_once_with(180, 230)
    assert mock_capture_region.call_count == 2
    assert all(call.kwargs["hwnd"] == 500 for call in mock_capture_region.call_args_list)
    assert all(call.args[0] == BoundingBox(left=50, top=100, right=300, bottom=400)
               for call in mock_capture_region.call_args_list)


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_ocr_postcondition_tracks_target_not_unrelated_word_count(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = OcrWord("Submit", 0.99, BoundingBox(left=20, top=30, right=100, bottom=55))
    unrelated = OcrWord("Updated", 0.99, BoundingBox(left=200, top=30, right=270, bottom=55))
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context
    mock_capture_window.return_value = b"BM_PRIVATE"
    mock_run_ocr.side_effect = [OcrResult(words=[target]), OcrResult(words=[target, unrelated])]
    monkeypatch.setattr("pluma.tools.ui.time.sleep", lambda _: None)

    result = execute_click_ocr_text({"text": "Submit", "hwnd": 500})

    assert result.ok and not result.verified
    assert result.verify_detail.method == "ocr_target_transition"
    assert "remains at the same bounds" in result.verify_detail.detail
    mock_mouse_click.assert_called_once()


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_ocr_postcondition_failure_is_not_reported_as_target_disappearance(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = OcrWord("Submit", 0.99, BoundingBox(left=20, top=30, right=100, bottom=55))
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )
    mock_context.get_process_creation_time_ns.return_value = 1_000_000_000
    mock_context_cls.return_value = mock_context
    mock_capture_window.return_value = b"BM_PRIVATE"
    mock_run_ocr.side_effect = [OcrResult(words=[target]), RuntimeError("engine failure")]
    monkeypatch.setattr("pluma.tools.ui.time.sleep", lambda _: None)

    result = execute_click_ocr_text({"text": "Submit", "hwnd": 500})

    assert result.ok and not result.verified
    assert result.verify_detail is not None and not result.verify_detail.ok
    assert "Post-click verification failed" in result.verify_detail.detail
    mock_mouse_click.assert_called_once()


def test_ocr_textless_target_refuses_without_click(monkeypatch: pytest.MonkeyPatch) -> None:
    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture
    from pluma.perception.ocr_lifecycle import OcrLifecycleManager

    info = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )
    context = MagicMock()
    context.get_active_window.return_value = info
    context.get_process_creation_time_ns.return_value = 1_000_000_000
    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: context)
    monkeypatch.setattr(WindowCapture, "capture_window", lambda self, hwnd: b"BM_PRIVATE")
    monkeypatch.setattr(OcrLifecycleManager, "run_ocr", lambda self, image, cancellation_token=None: OcrResult())
    clicks: list[tuple[int, int]] = []
    monkeypatch.setattr(InputAdapter, "mouse_click", lambda self, x, y: clicks.append((x, y)))

    result = execute_click_ocr_text({"text": "Open graphic", "hwnd": 500})

    assert not result.ok and not result.verified
    assert result.error_code == "OCR_NO_MATCH"
    assert clicks == []


def test_stop_latched_during_ocr_prevents_the_following_click(monkeypatch: pytest.MonkeyPatch) -> None:
    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture
    from pluma.perception.ocr_lifecycle import OcrLifecycleManager

    token = CancellationToken()
    info = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )
    context = MagicMock()
    context.get_active_window.return_value = info
    context.get_process_creation_time_ns.return_value = 1_000_000_000
    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: context)
    monkeypatch.setattr(WindowCapture, "capture_window", lambda self, hwnd: b"BM_PRIVATE")

    def cancel_while_recognizing(self, image, cancellation_token=None):
        token.cancel()
        return OcrResult(words=[OcrWord(
            "Submit", 0.99, BoundingBox(left=20, top=30, right=100, bottom=55)
        )])

    monkeypatch.setattr(OcrLifecycleManager, "run_ocr", cancel_while_recognizing)
    clicks: list[tuple[int, int]] = []
    monkeypatch.setattr(InputAdapter, "mouse_click", lambda self, x, y: clicks.append((x, y)))
    task_context = SimpleNamespace(cancellation_token=token)

    with pytest.raises(TaskCancelledError):
        execute_click_ocr_text({"text": "Submit", "hwnd": 500}, task_context)

    assert token.is_cancelled
    assert clicks == []


def _p12_blocking_uia_wait_executor(args, task_context):
    from pluma.tools.screen_catalog import execute_find_control_wait
    snapshot = task_context.snapshot_registry.resolve(args["snapshot_id"])
    target = ActiveWindowInfo(hwnd=snapshot.hwnd, is_valid=True, pid=snapshot.pid,
        process_name=snapshot.active_process, window_title=snapshot.active_window_title,
        class_name=snapshot.window_class, rect=snapshot.window_rect, dpi_scale=snapshot.dpi_scale)
    class OwnedContext:
        def get_active_window(self):
            return target
        def get_process_creation_time_ns(self, pid):
            return snapshot.process_creation_time_ns
    class BlockedProvider:
        def capture(self, **kwargs):
            Path(os.environ["PLUMA_P12_E10_MARKER"]).write_text(str(os.getpid()), encoding="ascii")
            time.sleep(60)
            return snapshot
    with patch("pluma.tools.screen_catalog.ActiveWindowContext", OwnedContext), patch(
            "pluma.tools.screen_catalog.UiaSnapshotBuilder", BlockedProvider):
        result = execute_find_control_wait(args, task_context)
        Path(os.environ["PLUMA_P12_E10_MARKER"]).with_suffix(".click").write_text("late completion")
        return result


@pytest.mark.parametrize("screen_mode", ["ocr", "uia_wait"])
def test_stop_terminates_owned_worker_blocked_in_registered_screen_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    screen_mode: str,
) -> None:
    from pluma.core.task_supervisor import TaskSupervisor
    from pluma.tools.base import AdapterDispatcher, AdapterPriority
    from pluma.tools.registry import ToolRegistry

    marker = tmp_path / "ocr-entered.txt"
    monkeypatch.setenv("PLUMA_P12_E10_MARKER", str(marker))
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule(request_id="p12-e10-stop-ocr")
    supervisor.start_task(capsule.task_id)
    registry = ToolRegistry()
    # The executor has inert capture/input and cannot commit an external effect.
    # This spec isolates STOP ownership; production policy is tested separately.
    spec = CLICK_OCR_TEXT_SPEC.model_copy(update={
        "risk_class": RiskClass.LOW, "non_undoable": False, "undo_builder": None,
        "executor": AdapterDispatcher(
            "click_ocr_text",
            {AdapterPriority.OCR_GROUNDED: _p12_e10_blocking_ocr_executor},
        )
    })
    tool_name = "click_ocr_text"
    args = {"text": "Submit", "hwnd": 500}
    if screen_mode == "uia_wait":
        from pluma.tools.screen_catalog import WAIT_FOR_CONTROL_SPEC
        from tests.unit.test_screen_control_catalog import _screen_context
        fixture_context, snapshot, _, _ = _screen_context()
        capsule.snapshot_registry = fixture_context.snapshot_registry
        tool_name = "wait_for_control"
        args = {"snapshot_id": snapshot.snapshot_id, "label": "Submit", "timeout_ms": 2500}
        spec = WAIT_FOR_CONTROL_SPEC.model_copy(update={"timeout_s": 15.0,
            "executor": AdapterDispatcher(tool_name, {AdapterPriority.UIA: _p12_blocking_uia_wait_executor})})
    registry.register(spec)
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(
        registry.execute,
        tool_name,
        args,
        capsule,
    )
    worker_pid = None
    stopped = False
    try:
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline and not marker.exists():
            if future.done():
                pytest.fail(f"Registered OCR call ended before reaching OCR: {future.result()!r}")
            time.sleep(0.02)
        assert marker.is_file(), "The registered OCR worker did not enter the blocked recognition fixture."
        worker_pid = int(marker.read_text(encoding="ascii"))
        controller = capsule.worker_controller
        assert controller is not None and controller._proc is not None
        assert controller._proc.pid == worker_pid

        supervisor.stop_task(capsule.task_id, grace_s=0)
        stopped = True
        result = future.result(timeout=8.0)

        assert not result.ok and not result.verified
        assert result.error_code == "TASK_CANCELLED"
        assert not marker.with_suffix(".click").exists()
        assert capsule.worker_controller is None
        with pytest.raises(psutil.NoSuchProcess):
            psutil.Process(worker_pid).status()
    finally:
        if not stopped:
            supervisor.stop_task(capsule.task_id, grace_s=0)
        if not future.done():
            future.result(timeout=8.0)
        pool.shutdown(wait=True)
        registry.close()
        capsule.close_resources(stopping=True)


def test_ocr_capture_is_ephemeral_and_tool_result_contains_no_image_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture
    from pluma.perception.ocr_lifecycle import OcrLifecycleManager
    from pluma.adapters.screen import ScreenAdapter

    info = ActiveWindowInfo(
        hwnd=500, is_valid=True, pid=12345,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
    )
    context = MagicMock()
    context.get_active_window.return_value = info
    context.get_process_creation_time_ns.return_value = 1_000_000_000
    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: context)
    monkeypatch.setattr(WindowCapture, "capture_window", lambda self, hwnd: b"BM_PRIVATE_SCREENSHOT")
    monkeypatch.setattr(
        ScreenAdapter,
        "capture_to_temp_file",
        lambda *args, **kwargs: pytest.fail("OCR fallback must not persist screenshot files."),
    )
    word = OcrWord("Submit", 0.99, BoundingBox(left=20, top=30, right=100, bottom=55))
    outcomes = iter((OcrResult(words=[word]), OcrResult(words=[])))
    monkeypatch.setattr(
        OcrLifecycleManager,
        "run_ocr",
        lambda self, image, cancellation_token=None: (image == b"BM_PRIVATE_SCREENSHOT" and next(outcomes)),
    )
    monkeypatch.setattr(InputAdapter, "mouse_click", lambda self, x, y: None)
    monkeypatch.setattr("pluma.tools.ui.time.sleep", lambda _: None)

    result = execute_click_ocr_text({"text": "Submit", "hwnd": 500})

    assert result.ok and result.verified
    assert b"BM_PRIVATE_SCREENSHOT" not in repr(result.data).encode()
    assert "image_ref" not in result.data
    assert list(tmp_path.iterdir()) == []


def test_uia_snapshot_builder_with_ocr_fallback() -> None:
    from pluma.perception.uia_snapshot import UiaSnapshotBuilder
    from pluma.perception.element_refs import ElementSource

    win_info = ActiveWindowInfo(
        hwnd=101,
        process_name="graphic_app.exe",
        window_title="Canvas Editor",
        rect=BoundingBox(left=0, top=0, right=1000, bottom=800),
        dpi_scale=1.0,
        is_valid=True,
    )
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = win_info
    mock_context.get_window_info.return_value = win_info

    mock_capture = MagicMock()
    mock_capture.capture_window.return_value = b"BM_BYTES"

    mock_ocr = MagicMock()
    mock_ocr.run_ocr.return_value = OcrResult(
        words=[
            OcrWord(text="Layers", confidence=0.91, bounds=BoundingBox(left=10, top=10, right=80, bottom=30))
        ]
    )

    builder = UiaSnapshotBuilder(context=mock_context, custom_extractor=lambda hwnd: [])
    snapshot = builder.capture(
        hwnd=101,
        include_ocr=True,
        window_capture=mock_capture,
        ocr_manager=mock_ocr,
    )

    assert len(snapshot.controls) == 0
    assert len(snapshot.ocr_words) == 1
    assert snapshot.ocr_words[0].label == "Layers"
    assert snapshot.ocr_words[0].source == ElementSource.OCR
    assert snapshot.ocr_words[0].confidence == 0.91
