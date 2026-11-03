"""Native P12 acceptance for semantic inspection of an owned WPF window."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
import pytest

from pluma.adapters.uia import UiaAdapter
from pluma.core.cancellation import CancellationToken
from pluma.perception.context import ActiveWindowContext
from pluma.perception.element_refs import ElementSource, ScreenSnapshot
from pluma.tools.base import AdapterPriority
from pluma.tools.registry import ToolRegistry
from pluma.tools.ui import INSPECT_ACTIVE_WINDOW_SPEC

from tests.fixtures.desktop_thread import desktop_thread


@pytest.fixture
def owned_wpf_window(tmp_path: Path):
    if sys.platform != "win32":
        pytest.fail("P12 native WPF UIA acceptance requires Windows.")

    project = Path(__file__).parents[1] / "fixtures" / "wpf_semantic_target" / "Pluma.WpfSemanticTarget.csproj"
    artifacts = tmp_path / "artifacts"
    build = subprocess.run(
        [
            "dotnet", "build", str(project), "--configuration", "Release",
            "--output", str(artifacts / "bin"),
            f"-p:BaseIntermediateOutputPath={artifacts / 'obj'}{os.sep}",
            f"-p:MSBuildProjectExtensionsPath={artifacts / 'obj'}{os.sep}",
            "--verbosity", "quiet",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert build.returncode == 0, f"WPF fixture build failed:\n{build.stdout}\n{build.stderr}"

    executable = artifacts / "bin" / "Pluma.WpfSemanticTarget.exe"
    assert executable.is_file(), f"WPF fixture executable was not produced at {executable}."
    ready = tmp_path / "wpf-window-ready.json"
    process = subprocess.Popen(
        [str(executable), str(ready)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    hwnd = None
    fixture_pid = None
    fixture_creation_time = None
    failure = None
    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if ready.is_file():
                state = json.loads(ready.read_text(encoding="utf-8"))
                fixture_pid = int(state.get("pid", 0))
                if fixture_pid != process.pid or not state.get("hwnd"):
                    raise AssertionError(
                        f"WPF fixture identity does not match owned process {process.pid}: {state!r}."
                    )
                hwnd = int(state["hwnd"])
                fixture_creation_time = psutil.Process(fixture_pid).create_time()
                break
            if process.poll() is not None:
                raise AssertionError(f"Owned WPF fixture exited before readiness with {process.returncode}.")
            time.sleep(0.025)
        if hwnd is None:
            raise AssertionError("Owned WPF fixture did not become ready within 15 seconds.")

        yield {"process": process, "hwnd": hwnd, "pid": fixture_pid}
    except Exception as exc:
        failure = exc
        raise
    finally:
        if process.poll() is None:
            if hwnd:
                import ctypes as c
                from ctypes import wintypes as w

                user = c.WinDLL("user32", use_last_error=True)
                user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
                user.PostMessageW.restype = w.BOOL
                user.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE, owned WPF fixture only
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.terminate()  # This test created and owns this exact process.
                process.wait(timeout=5.0)
                if failure is None:
                    raise AssertionError("Owned WPF fixture required forced cleanup after WM_CLOSE.")
        if fixture_pid and fixture_creation_time is not None:
            try:
                fixture_process = psutil.Process(fixture_pid)
                same_process = fixture_process.create_time() == fixture_creation_time
                if same_process and fixture_process.is_running():
                    fixture_process.terminate()
                    fixture_process.wait(timeout=5.0)
                    if failure is None:
                        raise AssertionError("Owned WPF process required forced cleanup after WM_CLOSE.")
            except psutil.NoSuchProcess:
                pass
        if process.poll() is None:
            raise AssertionError("Owned WPF fixture process remains after cleanup.")


@desktop_thread
def test_p12_e01_wpf_semantic_inspection_uses_uia(
    owned_wpf_window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name != "nt":
        pytest.fail("P12 native WPF UIA acceptance requires Windows.")

    native_context = ActiveWindowContext()

    class OwnedWindowContext:
        def get_active_window(self):
            return native_context.get_window_info(owned_wpf_window["hwnd"])

        def get_window_info(self, hwnd: int):
            return native_context.get_window_info(hwnd)

        def get_process_creation_time_ns(self, pid: int):
            return native_context.get_process_creation_time_ns(pid)

    monkeypatch.setattr("pluma.tools.ui.ActiveWindowContext", lambda: OwnedWindowContext())

    context = SimpleNamespace(
        task_id="p12-e01-wpf-native",
        cancellation_token=CancellationToken(),
        undo_stack=[],
    )
    registry = ToolRegistry()
    # Bind this exact owned WPF HWND in the test thread; this test proves the
    # native UIA provider, not foreground focus or the separate worker boundary.
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC.model_copy(update={"process_isolated": False}))
    try:
        result = registry.execute(
            "inspect_active_window",
            {"include_controls": True, "max_controls": 50},
            task_context=context,
        )
        assert result.ok and result.verified, result.factual_message
        assert result.adapter_used == AdapterPriority.UIA.name.lower()
        assert result.data["hwnd"] == owned_wpf_window["hwnd"]

        raw_snapshot = result.data.get("raw_snapshot")
        assert raw_snapshot, "WPF inspection did not return its semantic snapshot."
        snapshot = ScreenSnapshot.model_validate(raw_snapshot)
        assert snapshot.pid == owned_wpf_window["pid"]
        controls = [item for item in snapshot.controls if item.source is ElementSource.UIA]
        submit = [item for item in controls if item.label == "Submit" and item.control_type == "Button"]
        assert submit, f"WPF UIA provider did not return its Submit Button: {controls!r}"

        native_control = UiaAdapter().find_control(
            hwnd=owned_wpf_window["hwnd"], name="Submit", control_type="Button"
        )
        assert native_control.name == "Submit"
        assert native_control.is_enabled is True
    finally:
        registry.close()
