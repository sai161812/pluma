"""Native P12 acceptance for semantic inspection and UIA invocation (E-01/E-02)."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
import psutil

from pluma.adapters.uia import UiaAdapter
from pluma.core.cancellation import CancellationToken
from pluma.perception.context import ActiveWindowContext
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenSnapshot
from pluma.perception.ocr_adapter import OcrResult, OcrWord
from pluma.perception.snapshot_registry import SnapshotRegistry
from pluma.tools.base import AdapterPriority
from pluma.tools.registry import ToolRegistry
from pluma.tools.ui import CLICK_ELEMENT_SPEC, CLICK_OCR_TEXT_SPEC, INSPECT_ACTIVE_WINDOW_SPEC

from tests.fixtures.desktop_thread import desktop_thread


@pytest.fixture
def owned_uia_window(tmp_path: Path):
    if sys.platform != "win32":
        pytest.fail("P12 native UIA acceptance requires Windows.")

    ready = tmp_path / "uia-window-ready.json"
    helper = Path(__file__).parents[1] / "fixtures" / "uia_semantic_target.py"
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = subprocess.Popen(
        [sys.executable, str(helper), str(ready)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        creationflags=creation_flags,
    )
    hwnd = None
    duplicate_hwnd = None
    fixture_pid = None
    fixture_creation_time = None
    failure = None
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if ready.is_file():
                state = json.loads(ready.read_text(encoding="utf-8"))
                fixture_pid = int(state.get("pid", 0))
                if not fixture_pid or not state.get("hwnd") or not state.get("duplicate_hwnd"):
                    raise AssertionError(
                        f"UIA fixture published invalid process/window identity {state!r}."
                    )
                if fixture_pid != process.pid and state.get("parent_pid") != process.pid:
                    raise AssertionError(
                        f"UIA fixture PID {fixture_pid} is not the owned launcher {process.pid} "
                        f"or its direct child: {state!r}."
                    )
                hwnd = int(state["hwnd"])
                duplicate_hwnd = int(state["duplicate_hwnd"])
                fixture_creation_time = psutil.Process(fixture_pid).create_time()
                break
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"Owned UIA fixture exited before readiness: {output}")
            time.sleep(0.025)
        if hwnd is None:
            raise AssertionError("Owned UIA fixture did not become ready within 10 seconds.")

        yield {
            "process": process,
            "hwnd": hwnd,
            "duplicate_hwnd": duplicate_hwnd,
            "pid": fixture_pid,
        }
    except Exception as exc:
        failure = exc
        raise
    finally:
        if process.poll() is None:
            if hwnd or duplicate_hwnd:
                import ctypes as c
                from ctypes import wintypes as w

                user = c.WinDLL("user32", use_last_error=True)
                user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
                user.PostMessageW.restype = w.BOOL
                for owned_hwnd in (hwnd, duplicate_hwnd):
                    if owned_hwnd:
                        user.PostMessageW(owned_hwnd, 0x0010, 0, 0)  # WM_CLOSE, owned fixture only
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.terminate()  # This test created and owns this exact process.
                process.wait(timeout=5.0)
                if failure is None:
                    raise AssertionError("Owned UIA fixture required forced cleanup after WM_CLOSE.")
        if fixture_pid and fixture_creation_time is not None:
            try:
                fixture_process = psutil.Process(fixture_pid)
                same_process = fixture_process.create_time() == fixture_creation_time
                if same_process and fixture_process.is_running():
                    if fixture_process.ppid() != process.pid:
                        raise AssertionError("Refusing cleanup of a UIA fixture PID with changed parent identity.")
                    fixture_process.terminate()
                    fixture_process.wait(timeout=5.0)
                    if failure is None:
                        raise AssertionError("Owned UIA child required forced cleanup after WM_CLOSE.")
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            raise AssertionError("Owned UIA fixture process remains after cleanup.")
        if process.stdout:
            process.stdout.close()


def _bind_owned_window_context(monkeypatch: pytest.MonkeyPatch, initial_hwnd: int):
    native_context = ActiveWindowContext()
    selected = {"hwnd": initial_hwnd}

    class OwnedWindowContext:
        def get_active_window(self):
            return native_context.get_window_info(selected["hwnd"])

        def get_window_info(self, hwnd: int):
            return native_context.get_window_info(hwnd)

        def get_process_creation_time_ns(self, pid: int):
            return native_context.get_process_creation_time_ns(pid)

    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: OwnedWindowContext())
    return selected, native_context


@desktop_thread
def test_p12_e01_e02_semantic_inspection_and_submit_use_uia_only(
    owned_uia_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.fail("P12 native UIA acceptance requires Windows.")

    ocr_attempts: list[str] = []

    class ForbiddenLazyModule:
        def __init__(self, name: str) -> None:
            self.name = name

        def __getattr__(self, attribute: str):
            ocr_attempts.append(f"{self.name}.{attribute}")
            raise AssertionError(f"OCR/capture path was accessed: {self.name}.{attribute}")

    monkeypatch.setitem(sys.modules, "pluma.perception.capture", ForbiddenLazyModule("capture"))
    monkeypatch.setitem(sys.modules, "pluma.perception.ocr_lifecycle", ForbiddenLazyModule("ocr_lifecycle"))

    # Bind the production tools to this exact owned HWND. Native foreground
    # state is unavailable in some test sessions; all window/process identity
    # fields still come from fresh Win32 reads of the owned fixture.
    native_context = ActiveWindowContext()

    class OwnedWindowContext:
        def get_active_window(self):
            return native_context.get_window_info(owned_uia_window["hwnd"])

        def get_window_info(self, hwnd: int):
            return native_context.get_window_info(hwnd)

        def get_process_creation_time_ns(self, pid: int):
            return native_context.get_process_creation_time_ns(pid)

    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: OwnedWindowContext())

    context = SimpleNamespace(
        task_id="p12-e01-e02-native",
        snapshot_registry=SnapshotRegistry(),
        cancellation_token=CancellationToken(),
        undo_stack=[],
    )
    registry = ToolRegistry()
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC)
    registry.register(CLICK_ELEMENT_SPEC)
    try:
        inspected = registry.execute(
            "inspect_active_window",
            {"include_controls": True, "max_controls": 50},
            task_context=context,
        )
        assert inspected.ok and inspected.verified, inspected.factual_message
        assert inspected.adapter_used == AdapterPriority.UIA.name.lower()
        assert inspected.data["hwnd"] == owned_uia_window["hwnd"]

        raw_snapshot = inspected.data.get("raw_snapshot")
        assert raw_snapshot, "Direct registered-tool execution did not return its semantic snapshot."
        snapshot = ScreenSnapshot.model_validate(raw_snapshot)
        context.snapshot_registry.register(snapshot)
        controls = [item for item in snapshot.controls if item.source is ElementSource.UIA]
        submit = [item for item in controls if item.label == "Submit" and item.control_type == "Button"]
        assert submit, f"UIA did not return the fixture Submit button: {controls!r}"
        assert snapshot.pid == owned_uia_window["pid"]
        assert snapshot.process_creation_time_ns is not None
        fresh_info = native_context.get_window_info(owned_uia_window["hwnd"])
        assert fresh_info.rect == snapshot.window_rect, (
            f"Owned fixture geometry changed before invocation: {fresh_info.rect!r} "
            f"versus snapshot {snapshot.window_rect!r}."
        )

        result = registry.execute(
            "click_element",
            {
                "snapshot_id": snapshot.snapshot_id,
                "target_ref": f"{snapshot.snapshot_id}::{submit[0].element_id}",
                "expected_enabled": False,
            },
            task_context=context,
        )
        assert result.ok and result.verified, result.factual_message
        assert result.adapter_used == AdapterPriority.UIA.name.lower()

        # Independent UIA readback confirms the native fixture transition.
        adapter = UiaAdapter()
        submit_state = adapter.find_control(
            hwnd=owned_uia_window["hwnd"], name="Submit", control_type="Button"
        )
        status = adapter.find_control(hwnd=owned_uia_window["hwnd"], name="Submitted")
        assert submit_state.is_enabled is False
        assert status.name == "Submitted"
        assert ocr_attempts == []
    finally:
        registry.close()


@desktop_thread
def test_p12_e03_duplicate_uia_labels_are_refused_without_mutation(
    owned_uia_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected, _ = _bind_owned_window_context(monkeypatch, owned_uia_window["duplicate_hwnd"])
    context = SimpleNamespace(
        task_id="p12-e03-native",
        snapshot_registry=SnapshotRegistry(),
        cancellation_token=CancellationToken(),
        undo_stack=[],
    )
    registry = ToolRegistry()
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC)
    registry.register(CLICK_ELEMENT_SPEC)
    try:
        inspected = registry.execute(
            "inspect_active_window",
            {"include_controls": True, "max_controls": 50},
            task_context=context,
        )
        assert inspected.ok and inspected.verified, inspected.factual_message
        snapshot = ScreenSnapshot.model_validate(inspected.data["raw_snapshot"])
        context.snapshot_registry.register(snapshot)
        duplicate_buttons = [
            item for item in snapshot.controls
            if item.source is ElementSource.UIA
            and item.label == "Submit"
            and item.control_type == "Button"
        ]
        assert len(duplicate_buttons) == 2, (
            f"The owned fixture must expose both duplicate Submit buttons through UIA: {duplicate_buttons!r}"
        )

        result = registry.execute(
            "click_element",
            {
                "snapshot_id": snapshot.snapshot_id,
                "target_ref": f"{snapshot.snapshot_id}::{duplicate_buttons[0].element_id}",
                "expected_enabled": False,
            },
            task_context=context,
        )
        assert not result.ok
        assert not result.verified
        assert result.error_code == "UI_AMBIGUOUS_TARGET"
        assert "2 UIA elements match" in (result.error or "")

        # Independent UIA readback proves refusal left both owned controls enabled.
        controls = UiaAdapter().get_control_tree(owned_uia_window["duplicate_hwnd"])
        native_buttons = [
            item for item in controls
            if item.name == "Submit" and item.control_type == "Button"
        ]
        assert len(native_buttons) == 2
        assert all(item.is_enabled for item in native_buttons)
        assert selected["hwnd"] == owned_uia_window["duplicate_hwnd"]
    finally:
        registry.close()


@desktop_thread
def test_p12_e04_changed_owned_window_rejects_stale_reference_before_uia(
    owned_uia_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    selected, _ = _bind_owned_window_context(monkeypatch, owned_uia_window["hwnd"])
    context = SimpleNamespace(
        task_id="p12-e04-native",
        snapshot_registry=SnapshotRegistry(),
        cancellation_token=CancellationToken(),
        undo_stack=[],
    )
    registry = ToolRegistry()
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC)
    registry.register(CLICK_ELEMENT_SPEC)
    try:
        inspected = registry.execute(
            "inspect_active_window",
            {"include_controls": True, "max_controls": 50},
            task_context=context,
        )
        assert inspected.ok and inspected.verified, inspected.factual_message
        snapshot = ScreenSnapshot.model_validate(inspected.data["raw_snapshot"])
        context.snapshot_registry.register(snapshot)
        submit = next(
            item for item in snapshot.controls
            if item.source is ElementSource.UIA
            and item.label == "Submit"
            and item.control_type == "Button"
        )

        # Change the production context to a second, independently owned HWND.
        selected["hwnd"] = owned_uia_window["duplicate_hwnd"]
        action_adapter_attempts: list[str] = []

        class ForbiddenActionAdapter:
            def __init__(self) -> None:
                action_adapter_attempts.append("constructed")
                raise AssertionError("Stale UI reference reached the UIA action adapter.")

        monkeypatch.setattr("pluma.tools.ui.UiaAdapter", ForbiddenActionAdapter)
        result = registry.execute(
            "click_element",
            {
                "snapshot_id": snapshot.snapshot_id,
                "target_ref": f"{snapshot.snapshot_id}::{submit.element_id}",
                "expected_enabled": False,
            },
            task_context=context,
        )

        assert not result.ok
        assert not result.verified
        assert result.error_code == "WINDOW_MISMATCH"
        assert action_adapter_attempts == []

        # Independent reads prove neither owned window's Submit control changed.
        adapter = UiaAdapter()
        original_submit = adapter.find_control(
            hwnd=owned_uia_window["hwnd"], name="Submit", control_type="Button"
        )
        duplicate_controls = adapter.get_control_tree(owned_uia_window["duplicate_hwnd"])
        duplicate_buttons = [
            item for item in duplicate_controls
            if item.name == "Submit" and item.control_type == "Button"
        ]
        assert original_submit.is_enabled is True
        assert len(duplicate_buttons) == 2
        assert all(item.is_enabled for item in duplicate_buttons)
    finally:
        registry.close()


@desktop_thread
def test_p12_e05_ocr_click_refuses_when_owned_window_moves_during_ocr(
    owned_uia_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hwnd = owned_uia_window["hwnd"]
    native_context = ActiveWindowContext()

    class OwnedWindowContext:
        def get_active_window(self):
            return native_context.get_window_info(hwnd)

        def get_window_info(self, target_hwnd: int):
            return native_context.get_window_info(target_hwnd)

        def get_process_creation_time_ns(self, pid: int):
            return native_context.get_process_creation_time_ns(pid)

    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: OwnedWindowContext())
    initial = native_context.get_window_info(hwnd)
    assert initial.is_valid and initial.rect.width > 0 and initial.rect.height > 0

    import ctypes as c
    from ctypes import wintypes as w

    user = c.WinDLL("user32", use_last_error=True)
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
    user.SetWindowPos.restype = w.BOOL

    def move_owned_window_during_ocr(_: object, image_bytes: bytes) -> OcrResult:
        assert image_bytes == b"BM_BYTES"
        moved = user.SetWindowPos(
            w.HWND(hwnd), None,
            initial.rect.left + 32, initial.rect.top + 20,
            initial.rect.width, initial.rect.height,
            0x0004 | 0x0010,  # SWP_NOZORDER | SWP_NOACTIVATE
        )
        assert moved, c.WinError(c.get_last_error())
        return OcrResult(words=[
            OcrWord(
                text="Submit",
                confidence=0.99,
                bounds=BoundingBox(left=24, top=28, right=174, bottom=64),
            )
        ])

    monkeypatch.setattr("pluma.perception.capture.WindowCapture.capture_window", lambda self, target: b"BM_BYTES")
    monkeypatch.setattr(
        "pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr",
        move_owned_window_during_ocr,
    )
    clicks: list[tuple[int, int]] = []
    monkeypatch.setattr("pluma.adapters.input.InputAdapter.mouse_click", lambda self, x, y: clicks.append((x, y)))

    registry = ToolRegistry()
    registry.register(CLICK_OCR_TEXT_SPEC)
    context = SimpleNamespace(
        task_id="p12-e05-native",
        cancellation_token=CancellationToken(),
        undo_stack=[],
    )
    try:
        result = registry.execute(
            "click_ocr_text",
            {"text": "Submit", "hwnd": hwnd},
            task_context=context,
        )

        assert not result.ok
        assert not result.verified
        assert result.error_code == "WINDOW_MOVED"
        assert clicks == []
        fresh = native_context.get_window_info(hwnd)
        assert fresh.rect != initial.rect
    finally:
        registry.close()
