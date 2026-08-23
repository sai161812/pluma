"""tests/unit/test_perception_context.py — Phase 7: ActiveWindowContext unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from pluma.adapters.base import Rect, WindowInfo, WindowState
from pluma.adapters.win32 import Win32Adapter
from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo


def test_active_window_context_valid_window() -> None:
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
