"""pluma.perception.context — Active window context inspection.

Spec §5.1 Perception Layer: "Active-window identity, UIA tree, targeted
capture, OCR, screen-element references."
Zero ML or pywinauto imported at module level.
"""

from __future__ import annotations

import ctypes
import logging
from dataclasses import dataclass
from typing import Optional

from pluma.adapters.win32 import Win32Adapter
from pluma.perception.element_refs import BoundingBox

logger = logging.getLogger(__name__)


@dataclass
class ActiveWindowInfo:
    """Identity and geometry of the active foreground window."""
    hwnd: int = 0
    process_name: str = "unknown"
    window_title: str = ""
    rect: BoundingBox = BoundingBox(left=0, top=0, right=0, bottom=0)
    dpi_scale: float = 1.0
    is_valid: bool = False
    pid: int = 0
    class_name: str = ""


class ActiveWindowContext:
    """Inspects the foreground window to extract identity, geometry, and process context."""

    def __init__(self, win32_adapter: Optional[Win32Adapter] = None) -> None:
        self._win32 = win32_adapter or Win32Adapter()

    def get_dpi_scale(self, hwnd: int) -> float:
        """Get the DPI scaling factor for a window (default 1.0 for 96 DPI)."""
        if not hwnd or not self._win32.is_window(hwnd):
            return 1.0
        try:
            user32 = ctypes.windll.user32
            if hasattr(user32, "GetDpiForWindow"):
                dpi = user32.GetDpiForWindow(ctypes.wintypes.HWND(hwnd))
                if dpi > 0:
                    return round(float(dpi) / 96.0, 2)
        except Exception as exc:
            logger.debug("Failed to get DPI for window %d: %s", hwnd, exc)
        return 1.0

    def get_process_name(self, pid: int) -> str:
        """Resolve process executable name from PID."""
        if not pid:
            return "unknown"
        try:
            import psutil
            return psutil.Process(pid).name()
        except Exception:
            return "unknown"

    def get_active_window(self) -> ActiveWindowInfo:
        """Retrieve full context for the current foreground window."""
        try:
            fg = self._win32.get_foreground_window()
            if fg is None or not fg.hwnd:
                return ActiveWindowInfo(is_valid=False)

            pname = self.get_process_name(fg.pid)
            dpi = self.get_dpi_scale(fg.hwnd)
            bbox = BoundingBox(
                left=fg.rect.left,
                top=fg.rect.top,
                right=fg.rect.right,
                bottom=fg.rect.bottom,
            )

            return ActiveWindowInfo(
                hwnd=fg.hwnd,
                process_name=pname,
                window_title=fg.title,
                rect=bbox,
                dpi_scale=dpi,
                is_valid=True,
                pid=fg.pid,
                class_name=fg.class_name,
            )
        except Exception as exc:
            logger.debug("Failed to get active window context: %s", exc)
            return ActiveWindowInfo(is_valid=False)
