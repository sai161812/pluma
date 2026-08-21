"""tests.unit.test_adapters_base — Unit tests for base adapter contracts and errors."""

import pytest

from pluma.adapters.base import (
    AccessDeniedError,
    AdapterError,
    AdapterTimeoutError,
    ControlInfo,
    ElementNotFoundError,
    ElementUnavailableError,
    InputOutOfBoundsError,
    Rect,
    WindowInfo,
    WindowNotFoundError,
    WindowState,
)


def test_adapter_error_hierarchy() -> None:
    """Verify all adapter errors derive from AdapterError with factual codes."""
    err = AdapterError("generic failure", error_code="TEST_ERROR")
    assert isinstance(err, Exception)
    assert err.message == "generic failure"
    assert err.error_code == "TEST_ERROR"

    access_err = AccessDeniedError("UAC restricted")
    assert isinstance(access_err, AdapterError)
    assert access_err.error_code == "ACCESS_DENIED"

    elem_err = ElementNotFoundError("Button missing")
    assert isinstance(elem_err, AdapterError)
    assert elem_err.error_code == "ELEMENT_NOT_FOUND"

    unavail_err = ElementUnavailableError("Button disabled")
    assert isinstance(unavail_err, AdapterError)
    assert unavail_err.error_code == "ELEMENT_UNAVAILABLE"

    timeout_err = AdapterTimeoutError("PowerShell hung")
    assert isinstance(timeout_err, AdapterError)
    assert timeout_err.error_code == "TIMEOUT"

    win_err = WindowNotFoundError("HWND 99999 not found")
    assert isinstance(win_err, AdapterError)
    assert win_err.error_code == "WINDOW_NOT_FOUND"

    bounds_err = InputOutOfBoundsError("Outside screen")
    assert isinstance(bounds_err, AdapterError)
    assert bounds_err.error_code == "OUT_OF_BOUNDS"


def test_rect_geometry() -> None:
    """Verify bounding box calculation and point containment."""
    r = Rect(left=100, top=100, right=500, bottom=400)
    assert r.width == 400
    assert r.height == 300
    assert r.contains(100, 100)
    assert r.contains(300, 250)
    assert r.contains(500, 400)
    assert not r.contains(99, 100)
    assert not r.contains(501, 400)
    assert not r.contains(300, 401)


def test_window_info_model() -> None:
    """Verify WindowInfo dataclass construction and fields."""
    rect = Rect(left=0, top=0, right=1920, bottom=1080)
    info = WindowInfo(
        hwnd=12345,
        title="Test Window",
        class_name="Notepad",
        pid=5678,
        is_visible=True,
        is_enabled=True,
        rect=rect,
        state=WindowState.NORMAL,
    )
    assert info.hwnd == 12345
    assert info.title == "Test Window"
    assert info.state == WindowState.NORMAL
    assert info.rect.width == 1920


def test_control_info_model() -> None:
    """Verify ControlInfo dataclass construction."""
    ctrl = ControlInfo(
        automation_id="btn_submit",
        name="Submit",
        control_type="Button",
        class_name="ButtonClass",
        is_enabled=True,
        is_visible=True,
    )
    assert ctrl.automation_id == "btn_submit"
    assert ctrl.name == "Submit"
    assert ctrl.is_enabled is True
