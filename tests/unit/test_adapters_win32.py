"""tests.unit.test_adapters_win32 — Unit tests for Win32Adapter."""

import pytest

from pluma.adapters.base import (
    Rect,
    WindowInfo,
    WindowNotFoundError,
    WindowState,
)
from pluma.adapters.win32 import Win32Adapter


def test_win32_adapter_instantiation() -> None:
    """Verify Win32Adapter initializes without starting ML or external workers."""
    adapter = Win32Adapter()
    assert adapter is not None


def test_win32_invalid_hwnd_raises() -> None:
    """Verify operations on invalid HWNDs raise WindowNotFoundError."""
    adapter = Win32Adapter()
    invalid_hwnd = 0x7FFFFFFF

    assert not adapter.is_window(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.get_window_title(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.get_window_rect(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.get_window_pid(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.get_window_state(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.get_window_info(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.set_foreground_window(invalid_hwnd)

    with pytest.raises(WindowNotFoundError):
        adapter.set_window_state(invalid_hwnd, WindowState.MINIMIZED)

    with pytest.raises(WindowNotFoundError):
        adapter.close_window(invalid_hwnd)


def test_win32_find_windows() -> None:
    """Verify find_windows returns valid WindowInfo list."""
    adapter = Win32Adapter()
    windows = adapter.find_windows(visible_only=False)
    assert isinstance(windows, list)
    if windows:
        w = windows[0]
        assert isinstance(w, WindowInfo)
        assert isinstance(w.hwnd, int)
        assert isinstance(w.rect, Rect)


def test_win32_foreground_window() -> None:
    """Verify get_foreground_window returns WindowInfo or None."""
    adapter = Win32Adapter()
    fg = adapter.get_foreground_window()
    if fg is not None:
        assert isinstance(fg, WindowInfo)
        assert fg.hwnd > 0
        assert isinstance(fg.pid, int)
