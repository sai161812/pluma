"""tests/unit/test_verify_screen.py — Phase 7: ScreenVerifier unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from pluma.adapters.base import ControlInfo, ElementNotFoundError, Rect, WindowInfo, WindowState
from pluma.adapters.uia import UiaAdapter
from pluma.adapters.win32 import Win32Adapter
from pluma.verify.screen import ScreenVerifier


def test_verify_control_text_match() -> None:
    mock_uia = MagicMock(spec=UiaAdapter)
    mock_uia.find_control.return_value = ControlInfo(
        automation_id="txtResult",
        name="Result is 42",
        control_type="Edit",
        class_name="TextBox",
        is_enabled=True,
        is_visible=True,
        rect=Rect(0, 0, 100, 30),
    )

    verifier = ScreenVerifier(uia_adapter=mock_uia)
    v_res = verifier.verify_control_text(hwnd=123, expected_text="42", auto_id="txtResult")
    assert v_res.ok
    assert "contains expected text" in v_res.detail


def test_verify_control_text_mismatch() -> None:
    mock_uia = MagicMock(spec=UiaAdapter)
    mock_uia.find_control.return_value = ControlInfo(
        automation_id="txtResult",
        name="Error occurred",
        control_type="Edit",
        class_name="TextBox",
        is_enabled=True,
        is_visible=True,
        rect=Rect(0, 0, 100, 30),
    )

    verifier = ScreenVerifier(uia_adapter=mock_uia)
    v_res = verifier.verify_control_text(hwnd=123, expected_text="Success", auto_id="txtResult")
    assert not v_res.ok
    assert "mismatch" in v_res.detail


def test_verify_control_invoked_success() -> None:
    mock_uia = MagicMock(spec=UiaAdapter)
    mock_uia.find_control.return_value = ControlInfo(
        automation_id="btnSubmit",
        name="Submit",
        control_type="Button",
        class_name="Button",
        is_enabled=True,
        is_visible=True,
        rect=Rect(0, 0, 80, 30),
    )

    verifier = ScreenVerifier(uia_adapter=mock_uia)
    v_res = verifier.verify_control_invoked(hwnd=123, name="Submit")
    assert v_res.ok
    assert "accessible" in v_res.detail


def test_verify_control_invoked_not_found() -> None:
    mock_uia = MagicMock(spec=UiaAdapter)
    mock_uia.find_control.side_effect = ElementNotFoundError("Button not found")

    verifier = ScreenVerifier(uia_adapter=mock_uia)
    v_res = verifier.verify_control_invoked(hwnd=123, name="Submit")
    assert not v_res.ok
    assert "failed" in v_res.detail


def test_verify_window_active_success() -> None:
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.get_foreground_window.return_value = WindowInfo(
        hwnd=999,
        title="Document - WordPad",
        class_name="WordPadClass",
        pid=555,
        is_visible=True,
        is_enabled=True,
        rect=Rect(0, 0, 800, 600),
        state=WindowState.NORMAL,
    )

    verifier = ScreenVerifier(win32_adapter=mock_win32)
    v_res = verifier.verify_window_active(hwnd=999, expected_title="WordPad")
    assert v_res.ok
    assert "is active" in v_res.detail


def test_verify_window_active_wrong_hwnd() -> None:
    mock_win32 = MagicMock(spec=Win32Adapter)
    mock_win32.get_foreground_window.return_value = WindowInfo(
        hwnd=888,
        title="Calculator",
        class_name="Calc",
        pid=556,
        is_visible=True,
        is_enabled=True,
        rect=Rect(0, 0, 300, 400),
        state=WindowState.NORMAL,
    )

    verifier = ScreenVerifier(win32_adapter=mock_win32)
    v_res = verifier.verify_window_active(hwnd=999)
    assert not v_res.ok
    assert "mismatch" in v_res.detail
