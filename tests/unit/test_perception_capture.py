"""tests/unit/test_perception_capture.py — Phase 8: WindowCapture unit tests."""

from __future__ import annotations

import io
from unittest.mock import MagicMock
import pytest
from PIL import Image

from pluma.adapters.base import Rect, WindowNotFoundError
from pluma.adapters.screen import ScreenAdapter
from pluma.adapters.win32 import Win32Adapter
from pluma.perception.capture import CaptureError, WindowCapture
from pluma.perception.element_refs import BoundingBox


def _bmp_bytes(width: int, height: int) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), color=(1, 2, 3)).save(output, format="BMP")
    return output.getvalue()


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
    mock_screen.capture_window.return_value = _bmp_bytes(800, 600)

    capture = WindowCapture(screen_adapter=mock_screen, win32_adapter=mock_win32)
    # Window-relative crop (50, 50, 200, 150) is taken from this target HWND only.
    region = BoundingBox(left=50, top=50, right=200, bottom=150)
    bmp_bytes = capture.capture_region(region=region, hwnd=12345)

    assert bmp_bytes[:2] == b"BM"
    assert int.from_bytes(bmp_bytes[18:22], "little", signed=True) == 150
    assert abs(int.from_bytes(bmp_bytes[22:26], "little", signed=True)) == 100
    mock_screen.capture_window.assert_called_once_with(12345)
    mock_screen.capture_rect.assert_not_called()


def test_region_capture_refuses_invalid_supplied_hwnd_without_desktop_fallback() -> None:
    mock_screen = MagicMock(spec=ScreenAdapter)
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.is_window.return_value = False
    capture = WindowCapture(screen_adapter=mock_screen, win32_adapter=mock_win32)

    with pytest.raises(CaptureError, match="invalid window handle"):
        capture.capture_region(BoundingBox(left=10, top=10, right=40, bottom=40), hwnd=99)

    mock_screen.capture_window.assert_not_called()
    mock_screen.capture_rect.assert_not_called()


@pytest.mark.parametrize(
    "region",
    [
        BoundingBox(left=-1, top=0, right=20, bottom=20),
        BoundingBox(left=0, top=-1, right=20, bottom=20),
        BoundingBox(left=0, top=0, right=801, bottom=20),
        BoundingBox(left=0, top=0, right=20, bottom=601),
    ],
)
def test_region_capture_refuses_crop_outside_target_window(region: BoundingBox) -> None:
    mock_screen = MagicMock(spec=ScreenAdapter)
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.is_window.return_value = True
    mock_win32.get_window_rect.return_value = Rect(left=100, top=100, right=900, bottom=700)
    capture = WindowCapture(screen_adapter=mock_screen, win32_adapter=mock_win32)

    with pytest.raises(CaptureError, match="exceeds target window bounds"):
        capture.capture_region(region, hwnd=99)

    mock_screen.capture_window.assert_not_called()
    mock_screen.capture_rect.assert_not_called()


def test_region_capture_invalid_dimensions_raises_error() -> None:
    capture = WindowCapture()
    invalid_region = BoundingBox(left=100, top=100, right=100, bottom=100)  # width=0, height=0
    with pytest.raises(CaptureError, match="Invalid region dimensions"):
        capture.capture_region(invalid_region)
