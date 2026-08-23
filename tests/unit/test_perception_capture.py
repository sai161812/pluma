"""tests/unit/test_perception_capture.py — Phase 8: WindowCapture unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from pluma.adapters.base import Rect, WindowNotFoundError
from pluma.adapters.screen import ScreenAdapter
from pluma.adapters.win32 import Win32Adapter
from pluma.perception.capture import CaptureError, WindowCapture
from pluma.perception.element_refs import BoundingBox


def test_window_capture_success() -> None:
    mock_screen = MagicMock(spec=ScreenAdapter)
    mock_win32 = MagicMock(spec=Win32Adapter)

    mock_win32.is_window.return_value = True
    dummy_bmp = b"BM" + b"\x00" * 100
    mock_screen.capture_window.return_value = dummy_bmp

    capture = WindowCapture(screen_adapter=mock_screen, win32_adapter=mock_win32)
    bmp_bytes = capture.capture_window(hwnd=12345)

    assert bmp_bytes == dummy_bmp
    mock_screen.capture_window.assert_called_once_with(12345)


def test_window_capture_invalid_hwnd_raises_error() -> None:
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.is_window.return_value = False

    capture = WindowCapture(win32_adapter=mock_win32)
    with pytest.raises(WindowNotFoundError, match="invalid window handle"):
        capture.capture_window(hwnd=99999)


def test_region_capture_relative_to_window() -> None:
    mock_screen = MagicMock(spec=ScreenAdapter)
    mock_win32 = MagicMock(spec=Win32Adapter)

    mock_win32.is_window.return_value = True
    mock_win32.get_window_rect.return_value = Rect(left=100, top=100, right=900, bottom=700)
    dummy_bmp = b"BM" + b"\x00" * 50
    mock_screen.capture_rect.return_value = dummy_bmp

    capture = WindowCapture(screen_adapter=mock_screen, win32_adapter=mock_win32)
    # Window-relative region (50, 50, 200, 150) -> Desktop absolute (150, 150, 300, 250)
    region = BoundingBox(left=50, top=50, right=200, bottom=150)
    bmp_bytes = capture.capture_region(region=region, hwnd=12345)

    assert bmp_bytes == dummy_bmp
    mock_screen.capture_rect.assert_called_once_with(
        Rect(left=150, top=150, right=300, bottom=250)
    )


def test_region_capture_invalid_dimensions_raises_error() -> None:
    capture = WindowCapture()
    invalid_region = BoundingBox(left=100, top=100, right=100, bottom=100)  # width=0, height=0
    with pytest.raises(CaptureError, match="Invalid region dimensions"):
        capture.capture_region(invalid_region)
