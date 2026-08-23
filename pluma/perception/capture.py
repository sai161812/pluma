"""pluma.perception.capture — Ephemeral target-window and region screen capture.

Spec §8.2, §4: "Capture only when screen context is needed; no loop."
Screenshots are strictly ephemeral — in-memory bytes only.
No image files are written to disk or persisted in the Activity Ledger.
Boundary: No continuous capture loop. Capture is on-demand only.
"""

from __future__ import annotations

import logging
from typing import Optional

from pluma.adapters.base import AdapterError, Rect, WindowNotFoundError
from pluma.adapters.screen import ScreenAdapter
from pluma.adapters.win32 import Win32Adapter
from pluma.perception.element_refs import BoundingBox

logger = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    """Raised when window or region capture fails."""


class WindowCapture:
    """Ephemeral target-window and region screen capture.

    All captures return raw BMP bytes held in memory only. The caller
    is responsible for discarding the bytes after use. No files are
    created unless explicitly requested via capture_to_temp_file.

    Spec §8.2: "Do not persist screenshots by default."
    """

    def __init__(
        self,
        screen_adapter: Optional[ScreenAdapter] = None,
        win32_adapter: Optional[Win32Adapter] = None,
    ) -> None:
        self._screen = screen_adapter or ScreenAdapter()
        self._win32 = win32_adapter or Win32Adapter()

    def capture_window(self, hwnd: int) -> bytes:
        """Capture the full visual content of a specific window as BMP bytes.

        Returns:
            Ephemeral BMP image bytes. Discard after processing.

        Raises:
            WindowNotFoundError: If the hwnd is invalid.
            CaptureError: If capture fails.
        """
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Cannot capture invalid window handle: {hwnd}")
        try:
            bmp_bytes = self._screen.capture_window(hwnd)
            logger.debug("Captured window HWND %d — %d bytes", hwnd, len(bmp_bytes))
            return bmp_bytes
        except WindowNotFoundError:
            raise
        except Exception as exc:
            raise CaptureError(f"Window capture failed for HWND {hwnd}: {exc}") from exc

    def capture_region(
        self,
        region: BoundingBox,
        hwnd: Optional[int] = None,
    ) -> bytes:
        """Capture a window-relative cropped region as BMP bytes.

        Args:
            region: Window-relative bounding box of the region to capture.
            hwnd: Optional window handle; if provided, converts region coordinates
                  to desktop-absolute using the window's position.

        Returns:
            Ephemeral BMP image bytes. Discard after processing.

        Raises:
            CaptureError: If capture fails.
        """
        if region.width <= 0 or region.height <= 0:
            raise CaptureError(
                f"Invalid region dimensions: {region.width}x{region.height}"
            )

        try:
            # Convert window-relative to desktop-absolute if hwnd given
            if hwnd is not None and self._win32.is_window(hwnd):
                win_rect = self._win32.get_window_rect(hwnd)
                abs_left = win_rect.left + region.left
                abs_top = win_rect.top + region.top
                abs_right = win_rect.left + region.right
                abs_bottom = win_rect.top + region.bottom
            else:
                abs_left = region.left
                abs_top = region.top
                abs_right = region.right
                abs_bottom = region.bottom

            desktop_rect = Rect(
                left=abs_left,
                top=abs_top,
                right=abs_right,
                bottom=abs_bottom,
            )
            bmp_bytes = self._screen.capture_rect(desktop_rect)
            logger.debug(
                "Captured region %dx%d — %d bytes",
                region.width,
                region.height,
                len(bmp_bytes),
            )
            return bmp_bytes
        except Exception as exc:
            raise CaptureError(f"Region capture failed: {exc}") from exc
