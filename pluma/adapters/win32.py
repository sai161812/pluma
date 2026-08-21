"""pluma.adapters.win32 — Win32 API native automation adapter.

Spec §13, §14: Win32 adapter wraps native Windows user32/kernel32 APIs for
window listing, focus management, window state manipulation, and process
inspection.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import re
from typing import Any, Dict, List, Optional

from pluma.adapters.base import (
    AccessDeniedError,
    AdapterError,
    Rect,
    WindowInfo,
    WindowNotFoundError,
    WindowState,
)

logger = logging.getLogger(__name__)

# Win32 Constants
SW_HIDE = 0
SW_SHOWNORMAL = 1
SW_SHOWMINIMIZED = 2
SW_MAXIMIZE = 3
SW_SHOWNOACTIVATE = 4
SW_SHOW = 5
SW_MINIMIZE = 6
SW_SHOWMINNOACTIVE = 7
SW_SHOWNA = 8
SW_RESTORE = 9

WM_CLOSE = 0x0010
GWL_STYLE = -16
WS_VISIBLE = 0x10000000
WS_MINIMIZE = 0x20000000
WS_MAXIMIZE = 0x01000000


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class Win32Adapter:
    """Native Win32 automation adapter for window management and inspection."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

    def is_window(self, hwnd: int) -> bool:
        """Check if hwnd is a valid window handle."""
        if not hwnd or not isinstance(hwnd, int):
            return False
        return bool(self._user32.IsWindow(wintypes.HWND(hwnd)))

    def get_window_pid(self, hwnd: int) -> int:
        """Get the PID of the process that owns the window."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return pid.value

    def get_window_title(self, hwnd: int) -> str:
        """Get the window title text."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        length = self._user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
        if length == 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
        return buf.value

    def get_class_name(self, hwnd: int) -> str:
        """Get the window class name."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        buf = ctypes.create_unicode_buffer(256)
        self._user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
        return buf.value

    def get_window_rect(self, hwnd: int) -> Rect:
        """Get the bounding rectangle of a window."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        rect = _RECT()
        ok = self._user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect))
        if not ok:
            raise AdapterError(f"Failed to get window rect for HWND {hwnd}")
        return Rect(
            left=int(rect.left),
            top=int(rect.top),
            right=int(rect.right),
            bottom=int(rect.bottom),
        )

    def get_window_state(self, hwnd: int) -> WindowState:
        """Determine the current display state of the window."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        
        if not self._user32.IsWindowVisible(wintypes.HWND(hwnd)):
            return WindowState.HIDDEN
        if self._user32.IsIconic(wintypes.HWND(hwnd)):
            return WindowState.MINIMIZED
        if self._user32.IsZoomed(wintypes.HWND(hwnd)):
            return WindowState.MAXIMIZED
        return WindowState.NORMAL

    def get_window_info(self, hwnd: int) -> WindowInfo:
        """Retrieve full metadata for a window handle."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        
        title = self.get_window_title(hwnd)
        class_name = self.get_class_name(hwnd)
        pid = self.get_window_pid(hwnd)
        is_visible = bool(self._user32.IsWindowVisible(wintypes.HWND(hwnd)))
        is_enabled = bool(self._user32.IsWindowEnabled(wintypes.HWND(hwnd)))
        rect = self.get_window_rect(hwnd)
        state = self.get_window_state(hwnd)

        return WindowInfo(
            hwnd=hwnd,
            title=title,
            class_name=class_name,
            pid=pid,
            is_visible=is_visible,
            is_enabled=is_enabled,
            rect=rect,
            state=state,
        )

    def find_windows(
        self,
        title_pattern: Optional[str] = None,
        process_name: Optional[str] = None,
        visible_only: bool = True,
    ) -> List[WindowInfo]:
        """Enumerate top-level windows matching optional filters."""
        results: List[WindowInfo] = []
        pattern = re.compile(title_pattern, re.IGNORECASE) if title_pattern else None

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_windows_callback(hwnd_val: int, _: Any) -> bool:
            hwnd = int(hwnd_val)
            if not self.is_window(hwnd):
                return True
            
            is_visible = bool(self._user32.IsWindowVisible(wintypes.HWND(hwnd)))
            if visible_only and not is_visible:
                return True

            title = self.get_window_title(hwnd)
            if pattern and not pattern.search(title):
                return True

            try:
                info = self.get_window_info(hwnd)
                results.append(info)
            except Exception as exc:
                logger.debug("Failed to get info for window %d: %s", hwnd, exc)
            return True

        cb = WNDENUMPROC(enum_windows_callback)
        self._user32.EnumWindows(cb, 0)
        return results

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Get the currently focused foreground window."""
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd or not self.is_window(hwnd):
            return None
        try:
            return self.get_window_info(int(hwnd))
        except Exception:
            return None

    def set_foreground_window(self, hwnd: int) -> bool:
        """Bring a window to the foreground and set input focus."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        
        # If minimized, restore first
        if self._user32.IsIconic(wintypes.HWND(hwnd)):
            self._user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
        
        ok = bool(self._user32.SetForegroundWindow(wintypes.HWND(hwnd)))
        return ok

    def set_window_state(self, hwnd: int, state: WindowState | str) -> bool:
        """Set window display state (minimized, maximized, normal, hidden, restore)."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        
        state_str = state.value if isinstance(state, WindowState) else str(state).lower()
        cmd_map = {
            "minimized": SW_MINIMIZE,
            "minimize": SW_MINIMIZE,
            "maximized": SW_MAXIMIZE,
            "maximize": SW_MAXIMIZE,
            "normal": SW_SHOWNORMAL,
            "restore": SW_RESTORE,
            "hidden": SW_HIDE,
            "hide": SW_HIDE,
            "show": SW_SHOW,
        }
        cmd = cmd_map.get(state_str)
        if cmd is None:
            raise ValueError(f"Unknown window state: {state}")
        
        return bool(self._user32.ShowWindow(wintypes.HWND(hwnd), cmd))

    def close_window(self, hwnd: int) -> bool:
        """Send WM_CLOSE message to a window to request graceful close."""
        if not self.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        return bool(self._user32.PostMessageW(wintypes.HWND(hwnd), WM_CLOSE, 0, 0))
