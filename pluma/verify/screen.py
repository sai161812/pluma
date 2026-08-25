"""pluma.verify.screen — Screen and UIA-based postcondition verifiers.

Spec §15, §16: Confirms UI control state, text values, and window focus
using Windows UI Automation or native Win32 APIs after actions.
"""

from __future__ import annotations

import logging
from typing import Optional

from pluma.adapters.base import ControlInfo, ElementNotFoundError, WindowNotFoundError
from pluma.adapters.uia import UiaAdapter
from pluma.adapters.win32 import Win32Adapter
from pluma.tools.base import VerifyResult

logger = logging.getLogger(__name__)


class ScreenVerifier:
    """Postcondition verifier for UI Automation controls and window focus."""

    def __init__(
        self,
        uia_adapter: Optional[UiaAdapter] = None,
        win32_adapter: Optional[Win32Adapter] = None,
    ) -> None:
        self._uia = uia_adapter or UiaAdapter()
        self._win32 = win32_adapter or Win32Adapter()

    def verify_control_text(
        self,
        hwnd: int,
        expected_text: str,
        auto_id: Optional[str] = None,
        name: Optional[str] = None,
        timeout_s: float = 2.0,
    ) -> VerifyResult:
        """Verify that a control contains the expected text value."""
        try:
            ctrl = self._uia.find_control(
                hwnd=hwnd,
                auto_id=auto_id,
                name=name,
                timeout_s=timeout_s,
            )
            actual_text = ctrl.name
            if expected_text in actual_text:
                return VerifyResult(
                    ok=True,
                    method="uia",
                    detail=f"Control '{name or auto_id}' contains expected text '{expected_text}'.",
                )
            return VerifyResult(
                ok=False,
                method="uia",
                detail=f"Control text mismatch: expected '{expected_text}', got '{actual_text}'.",
            )
        except Exception as exc:
            return VerifyResult(
                ok=False,
                method="uia",
                detail=f"Failed to verify control text: {exc}",
            )

    def verify_control_invoked(
        self,
        hwnd: int,
        auto_id: Optional[str] = None,
        name: Optional[str] = None,
        timeout_s: float = 2.0,
    ) -> VerifyResult:
        """Verify that a target control exists and was accessible for invocation."""
        try:
            ctrl = self._uia.find_control(
                hwnd=hwnd,
                auto_id=auto_id,
                name=name,
                timeout_s=timeout_s,
            )
            return VerifyResult(
                ok=True,
                method="uia",
                detail=f"Control '{name or auto_id}' verified accessible (enabled={ctrl.is_enabled}).",
            )
        except Exception as exc:
            return VerifyResult(
                ok=False,
                method="uia",
                detail=f"Control verification failed: {exc}",
            )

    def verify_window_active(
        self,
        hwnd: int,
        expected_title: Optional[str] = None,
    ) -> VerifyResult:
        """Verify that the target window is currently the foreground active window."""
        try:
            fg = self._win32.get_foreground_window()
            if fg is None:
                return VerifyResult(
                    ok=False,
                    method="win32",
                    detail="No active foreground window found.",
                )

            if fg.hwnd != hwnd:
                return VerifyResult(
                    ok=False,
                    method="win32",
                    detail=f"Window HWND mismatch: expected {hwnd}, got {fg.hwnd} ('{fg.title}').",
                )

            if expected_title and expected_title.lower() not in fg.title.lower():
                return VerifyResult(
                    ok=False,
                    method="win32",
                    detail=f"Window title mismatch: expected '{expected_title}' in '{fg.title}'.",
                )

            return VerifyResult(
                ok=True,
                method="win32",
                detail=f"Window HWND {hwnd} ('{fg.title}') is active in foreground.",
            )
        except Exception as exc:
            return VerifyResult(
                ok=False,
                method="win32",
                detail=f"Window active verification failed: {exc}",
            )
