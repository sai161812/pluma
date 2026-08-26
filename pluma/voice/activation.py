"""pluma.voice.activation — Push-to-talk activation and hotkey hooks.

Spec §7: "Use push-to-talk as the always-available voice activation for V1."
Zero background microphone capture when idle.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from typing import Callable, Optional, Tuple

logger = logging.getLogger(__name__)

# Win32 modifier constants
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


def parse_hotkey_string(hotkey_str: str) -> Tuple[int, int]:
    """Parse hotkey string like 'ctrl+alt+v' into Win32 (modifiers, vk_code)."""
    parts = [p.strip().lower() for p in hotkey_str.split("+") if p.strip()]
    modifiers = 0
    vk_code = 0

    key_map = {
        "esc": 0x1B,
        "escape": 0x1B,
        "space": 0x20,
        "tab": 0x09,
        "return": 0x0D,
        "enter": 0x0D,
    }

    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part in ("alt", "menu"):
            modifiers |= MOD_ALT
        elif part in ("shift",):
            modifiers |= MOD_SHIFT
        elif part in ("win", "windows", "super"):
            modifiers |= MOD_WIN
        elif part in key_map:
            vk_code = key_map[part]
        elif len(part) == 1 and part.isalnum():
            # A-Z are 0x41 - 0x5A, 0-9 are 0x30 - 0x39
            vk_code = ord(part.upper())
        elif part.startswith("f") and part[1:].isdigit():
            # F1-F12 are 0x70 - 0x7B
            f_num = int(part[1:])
            if 1 <= f_num <= 12:
                vk_code = 0x70 + (f_num - 1)

    if vk_code == 0:
        vk_code = ord("V")  # Fallback to 'V'
    return modifiers, vk_code


class VoiceActivation:
    """Manages push-to-talk activation hooks and state triggers."""

    def __init__(
        self,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
        hotkey: str = "ctrl+alt+v",
    ) -> None:
        self.on_press = on_press
        self.on_release = on_release
        self.hotkey = hotkey
        self.modifiers, self.vk_code = parse_hotkey_string(hotkey)

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._is_active = False
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        """Return True if push-to-talk is currently pressed/active."""
        with self._lock:
            return self._is_active

    def trigger_press(self) -> None:
        """Trigger push-to-talk press event manually or from hook."""
        with self._lock:
            if self._is_active:
                return
            self._is_active = True
        logger.debug("Push-to-talk activated (recording started).")
        if self.on_press:
            try:
                self.on_press()
            except Exception as exc:
                logger.error("Error in on_press callback: %s", exc)

    def trigger_release(self) -> None:
        """Trigger push-to-talk release event manually or from hook."""
        with self._lock:
            if not self._is_active:
                return
            self._is_active = False
        logger.debug("Push-to-talk released (recording stopped).")
        if self.on_release:
            try:
                self.on_release()
            except Exception as exc:
                logger.error("Error in on_release callback: %s", exc)

    def _monitor_loop(self) -> None:
        """Windows message / polling loop for push-to-talk key release."""
        if sys.platform != "win32":
            return

        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        VK_SHIFT = 0x10
        VK_CONTROL = 0x11
        VK_MENU = 0x12
        VK_LWIN = 0x5B
        VK_RWIN = 0x5C

        while self._running:
            # Check primary vk_code
            state = user32.GetAsyncKeyState(self.vk_code)
            key_down = bool(state & 0x8000)

            # Check configured modifiers
            if key_down and self.modifiers:
                if (self.modifiers & MOD_CONTROL) and not (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000):
                    key_down = False
                if (self.modifiers & MOD_ALT) and not (user32.GetAsyncKeyState(VK_MENU) & 0x8000):
                    key_down = False
                if (self.modifiers & MOD_SHIFT) and not (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000):
                    key_down = False
                if (self.modifiers & MOD_WIN) and not ((user32.GetAsyncKeyState(VK_LWIN) | user32.GetAsyncKeyState(VK_RWIN)) & 0x8000):
                    key_down = False

            if key_down and not self.is_active:
                self.trigger_press()
            elif not key_down and self.is_active:
                self.trigger_release()

            time.sleep(0.02)  # 20ms polling interval for responsive release

    def start(self) -> None:
        """Start listening for push-to-talk triggers."""
        if self._running:
            return
        self._running = True
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._monitor_loop, daemon=True, name="VoiceActivationThread")
            self._thread.start()
            logger.info("VoiceActivation started for hotkey '%s'.", self.hotkey)

    def stop(self) -> None:
        """Stop voice activation listener."""
        self._running = False
        if self.is_active:
            self.trigger_release()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)
            self._thread = None
        logger.info("VoiceActivation stopped.")
