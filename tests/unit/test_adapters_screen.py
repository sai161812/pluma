"""tests.unit.test_adapters_screen — Unit tests for ScreenAdapter."""

import os
import pytest

from pluma.adapters.base import (
    Rect,
    WindowNotFoundError,
)
from pluma.adapters.screen import ScreenAdapter


def test_screen_adapter_invalid_rect() -> None:
    """Verify non-positive dimensions raise ValueError."""
    adapter = ScreenAdapter()
    with pytest.raises(ValueError):
        adapter.capture_rect(Rect(left=100, top=100, right=100, bottom=100))

    with pytest.raises(ValueError):
        adapter.capture_rect(Rect(left=100, top=100, right=50, bottom=50))


def test_screen_adapter_invalid_hwnd() -> None:
    """Verify invalid HWND raises WindowNotFoundError."""
    adapter = ScreenAdapter()
    with pytest.raises(WindowNotFoundError):
        adapter.capture_window(0x7FFFFFFF)


def test_screen_adapter_capture_rect() -> None:
    """Verify capture_rect captures desktop bytes with valid BMP signature."""
    adapter = ScreenAdapter()
    rect = Rect(left=0, top=0, right=50, bottom=50)
    data = adapter.capture_rect(rect)
    assert isinstance(data, bytes)
    assert len(data) > 54  # Headers alone are 54 bytes
    assert data.startswith(b"BM")  # BMP magic signature


def test_screen_adapter_capture_to_temp_file() -> None:
    """Verify capture_to_temp_file creates a temporary BMP file."""
    adapter = ScreenAdapter()
    rect = Rect(left=10, top=10, right=60, bottom=60)
    temp_path = adapter.capture_to_temp_file(rect)
    try:
        assert os.path.exists(temp_path)
        assert os.path.getsize(temp_path) > 54
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
