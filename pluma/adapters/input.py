"""pluma.adapters.input — SendInput keyboard and mouse automation adapter.

Spec §13, §14: Provides low-level keyboard and mouse simulation via Win32
SendInput API with coordinate boundary validation and modifier key safety.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Union

from pluma.adapters.base import (
    AdapterError,
    InputOutOfBoundsError,
    Rect,
)

logger = logging.getLogger(__name__)

# Win32 SendInput constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_ABSOLUTE = 0x8000

# Virtual Key Codes
VK_MAP: Dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "delete": 0x2E,
    "del": 0x2E,
    "win": 0x5B,
    "windows": 0x5B,
    "lwin": 0x5B,
    "rwin": 0x5C,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


# Ctypes struct definitions for SendInput 64-bit safety
class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", _KEYBDINPUT),
        ("mi", _MOUSEINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


class InputAdapter:
    """Adapter for keyboard and mouse automation using Win32 SendInput."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32

    def _resolve_vk(self, key: Union[str, int]) -> int:
        """Resolve string key name or integer to virtual key code."""
        if isinstance(key, int):
            return key
        key_lower = str(key).lower().strip()
        if key_lower in VK_MAP:
            return VK_MAP[key_lower]
        if len(key_lower) == 1:
            char_code = ord(key_lower.upper())
            return char_code
        raise ValueError(f"Unknown key name: '{key}'")

    def _send_inputs(self, inputs: Sequence[_INPUT]) -> int:
        """Call SendInput ctypes function safely."""
        n = len(inputs)
        if n == 0:
            return 0
        arr = (_INPUT * n)(*inputs)
        cb_size = ctypes.sizeof(_INPUT)
        sent = self._user32.SendInput(n, arr, cb_size)
        if sent != n:
            err = ctypes.GetLastError()
            logger.warning("SendInput partial failure: sent %d of %d, error=%d", sent, n, err)
        return int(sent)

    def press_key(self, key: Union[str, int], duration_s: float = 0.05) -> None:
        """Simulate pressing and releasing a single key."""
        vk = self._resolve_vk(key)

        inp_down = _INPUT(type=INPUT_KEYBOARD)
        inp_down.u.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)

        inp_up = _INPUT(type=INPUT_KEYBOARD)
        inp_up.u.ki = _KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)

        self._send_inputs([inp_down])
        if duration_s > 0:
            time.sleep(duration_s)
        self._send_inputs([inp_up])

    def send_hotkey(
        self,
        modifiers: Sequence[Union[str, int]],
        key: Union[str, int],
        duration_s: float = 0.05,
    ) -> None:
        """Simulate a keyboard shortcut chord (e.g. Ctrl+Shift+S, Alt+F4).

        Guarantees that modifier keys are released even if an exception occurs.
        """
        mod_vks = [self._resolve_vk(m) for m in modifiers]
        main_vk = self._resolve_vk(key)

        try:
            # Press modifiers in order
            for mvk in mod_vks:
                inp = _INPUT(type=INPUT_KEYBOARD)
                inp.u.ki = _KEYBDINPUT(wVk=mvk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
                self._send_inputs([inp])

            # Press and release main key
            inp_down = _INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = _KEYBDINPUT(wVk=main_vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0)
            self._send_inputs([inp_down])

            if duration_s > 0:
                time.sleep(duration_s)

            inp_up = _INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = _KEYBDINPUT(wVk=main_vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
            self._send_inputs([inp_up])

        finally:
            # Release modifiers in reverse order
            for mvk in reversed(mod_vks):
                inp = _INPUT(type=INPUT_KEYBOARD)
                inp.u.ki = _KEYBDINPUT(wVk=mvk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)
                self._send_inputs([inp])

    def send_text(self, text: str) -> None:
        """Send unicode text characters directly."""
        inputs: List[_INPUT] = []
        for char in text:
            code = ord(char)
            inp_down = _INPUT(type=INPUT_KEYBOARD)
            inp_down.u.ki = _KEYBDINPUT(
                wVk=0,
                wScan=code,
                dwFlags=KEYEVENTF_UNICODE,
                time=0,
                dwExtraInfo=0,
            )
            inp_up = _INPUT(type=INPUT_KEYBOARD)
            inp_up.u.ki = _KEYBDINPUT(
                wVk=0,
                wScan=code,
                dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
                time=0,
                dwExtraInfo=0,
            )
            inputs.extend([inp_down, inp_up])

        self._send_inputs(inputs)

    def mouse_move(self, x: int, y: int, bounding_rect: Optional[Rect] = None) -> None:
        """Move mouse cursor to coordinate (x, y) with optional boundary checking."""
        if bounding_rect and not bounding_rect.contains(x, y):
            raise InputOutOfBoundsError(
                f"Coordinates ({x}, {y}) outside target rect: {bounding_rect}"
            )

        # Use SetCursorPos for direct, accurate movement
        ok = self._user32.SetCursorPos(int(x), int(y))
        if not ok:
            raise AdapterError(f"Failed to move cursor to ({x}, {y})")

    def mouse_click(
        self,
        x: int,
        y: int,
        button: str = "left",
        double: bool = False,
        bounding_rect: Optional[Rect] = None,
    ) -> None:
        """Click mouse at specified coordinate with boundary validation."""
        self.mouse_move(x, y, bounding_rect=bounding_rect)

        btn = button.lower().strip()
        if btn == "left":
            down_flag = MOUSEEVENTF_LEFTDOWN
            up_flag = MOUSEEVENTF_LEFTUP
        elif btn == "right":
            down_flag = MOUSEEVENTF_RIGHTDOWN
            up_flag = MOUSEEVENTF_RIGHTUP
        elif btn == "middle":
            down_flag = MOUSEEVENTF_MIDDLEDOWN
            up_flag = MOUSEEVENTF_MIDDLEUP
        else:
            raise ValueError(f"Unknown mouse button: '{button}'")

        def _click_once() -> None:
            d = _INPUT(type=INPUT_MOUSE)
            d.u.mi = _MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=down_flag, time=0, dwExtraInfo=0)
            u = _INPUT(type=INPUT_MOUSE)
            u.u.mi = _MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=up_flag, time=0, dwExtraInfo=0)
            self._send_inputs([d, u])

        _click_once()
        if double:
            time.sleep(0.05)
            _click_once()
