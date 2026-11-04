"""Read-only C# native identity/geometry checks against an owned isolated window.

No foreground activation or personal window access. Presentation eligibility is
covered separately by deterministic C# task/clock/probe cases, not claimed here.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess

from tests.windows.test_p12_uia_semantic_controls import owned_uia_window
from tests.fixtures.desktop_thread import desktop_thread


@desktop_thread
def test_native_presentation_probe_reads_owned_target_and_refuses_hidden(owned_uia_window):
    from pluma.core.ownership import get_process_creation_time
    from pluma.perception.context import ActiveWindowContext
    hwnd = owned_uia_window['hwnd']
    context = ActiveWindowContext()
    expected = context.get_window_info(hwnd)
    dll = Path('PLUMA.UI/CoreIpc.Tests/bin/Release/net8.0-windows/CoreIpc.Tests.dll').resolve()
    assert dll.is_file(), 'Build the declared CoreIpc.Tests Release target before native acceptance.'

    def probe():
        # Bounded foreground-less managed test child; no child processes are created.
        result = subprocess.run(['dotnet', str(dll), '--perception-probe', str(hwnd)],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    actual = probe()
    assert actual is not None
    assert actual['Hwnd'] == hwnd and actual['Pid'] == owned_uia_window['pid']
    assert actual['CreationTime'] == get_process_creation_time(expected.pid)
    assert actual['WindowClass'] == expected.class_name and actual['DpiScale'] == expected.dpi_scale
    assert actual['Bounds'] == dict(Left=expected.rect.left, Top=expected.rect.top,
        Right=expected.rect.right, Bottom=expected.rect.bottom)
    assert actual['TitleHash'] == 'sha256:' + hashlib.sha256(expected.window_title.encode()).hexdigest()
    assert expected.window_title not in json.dumps(actual)
    # Mutate only this positively identified owned fixture, in its own DPI space.
    from pluma.adapters.window_geometry import _window_coordinates
    with _window_coordinates(hwnd) as (c, w, api):
        assert api.SetWindowPos(w.HWND(hwnd), None, expected.rect.left + 17, expected.rect.top + 19,
            0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE | NOZORDER | NOACTIVATE
    moved = probe()
    assert moved['Bounds']['Left'] == expected.rect.left + 17
    assert moved['Bounds']['Top'] == expected.rect.top + 19
    assert moved['CreationTime'] == actual['CreationTime'] and moved['Bounds'] != actual['Bounds']
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    assert user.SetWindowTextW(hwnd, 'Owned P23 renamed target')
    renamed = probe()
    assert renamed['TitleHash'] == 'sha256:' + hashlib.sha256(b'Owned P23 renamed target').hexdigest()
    assert renamed['TitleHash'] != actual['TitleHash']
    user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user.ShowWindow(hwnd, 0)  # This exact fixture HWND only, never a user window.
    assert not user.IsWindowVisible(hwnd)
    assert probe() is None
