"""tests/unit/test_perception_context.py — Phase 7: ActiveWindowContext unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import ctypes
from types import SimpleNamespace
import pytest

from pluma.adapters.base import Rect, WindowInfo, WindowState
from pluma.adapters.win32 import Win32Adapter
from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo


@pytest.mark.parametrize('dpi', [96, 120, 131, 144])
def test_positive_dpi_is_read_without_guessing_or_rounding(monkeypatch, dpi):
    native = MagicMock(spec=Win32Adapter)
    native.is_window.return_value = True
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=SimpleNamespace(
        GetDpiForWindow=lambda _hwnd: dpi)))
    assert ActiveWindowContext(win32_adapter=native).get_dpi_scale(500) == dpi / 96


@pytest.mark.parametrize('failure', ['zero', 'error', 'missing'])
def test_unknown_dpi_invalidates_window_context(monkeypatch, failure):
    native = MagicMock(spec=Win32Adapter)
    native.is_window.return_value = True
    window = WindowInfo(hwnd=500, title='Fixture', class_name='Fixture', pid=99,
        is_visible=True, is_enabled=True, rect=Rect(0, 0, 400, 300), state=WindowState.NORMAL)
    native.get_foreground_window.return_value = window
    native.get_window_info.return_value = window
    def unavailable(_hwnd):
        if failure == 'error':
            raise OSError('Injected DPI failure')
        return 0
    user = SimpleNamespace() if failure == 'missing' else SimpleNamespace(GetDpiForWindow=unavailable)
    monkeypatch.setattr(ctypes, 'windll', SimpleNamespace(user32=user))
    context = ActiveWindowContext(win32_adapter=native)
    assert not context.get_active_window().is_valid
    assert not context.get_window_info(500).is_valid


def test_active_window_context_valid_window(monkeypatch) -> None:
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.get_foreground_window.return_value = WindowInfo(
        hwnd=12345,
        title="Notepad - Untitled",
        class_name="Notepad",
        pid=9999,
        is_visible=True,
        is_enabled=True,
        rect=Rect(left=100, top=100, right=900, bottom=700),
        state=WindowState.NORMAL,
    )
    mock_win32.is_window.return_value = True

    context = ActiveWindowContext(win32_adapter=mock_win32)
    monkeypatch.setattr(context, 'get_dpi_scale', lambda _hwnd: 1.0)
    info = context.get_active_window()

    assert info.is_valid
    assert info.hwnd == 12345
    assert info.window_title == "Notepad - Untitled"
    assert info.class_name == "Notepad"
    assert info.rect.left == 100
    assert info.rect.top == 100
    assert info.rect.width == 800
    assert info.rect.height == 600


def test_active_window_context_no_foreground_window() -> None:
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.get_foreground_window.return_value = None

    context = ActiveWindowContext(win32_adapter=mock_win32)
    info = context.get_active_window()

    assert not info.is_valid
    assert info.hwnd == 0


def test_get_process_name_fallback() -> None:
    context = ActiveWindowContext()
    assert context.get_process_name(0) == "unknown"
    assert context.get_process_name(-1) == "unknown"
