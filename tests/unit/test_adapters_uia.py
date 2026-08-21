"""tests.unit.test_adapters_uia — Unit tests for UiaAdapter."""

from unittest.mock import MagicMock, patch
import pytest

from pluma.adapters.base import (
    AdapterError,
    AdapterTimeoutError,
    ControlInfo,
    ElementNotFoundError,
    ElementUnavailableError,
    Rect,
    WindowNotFoundError,
)
from pluma.adapters.uia import UiaAdapter


def test_uia_adapter_instantiation() -> None:
    """Verify UiaAdapter instantiates without importing heavy ML modules."""
    adapter = UiaAdapter()
    assert adapter is not None


def test_uia_invalid_hwnd_raises_window_not_found() -> None:
    """Verify invalid HWND raises WindowNotFoundError."""
    adapter = UiaAdapter()
    with pytest.raises(WindowNotFoundError):
        adapter.find_control(0x7FFFFFFF, name="TestControl")


def test_uia_find_control_mocked() -> None:
    """Verify find_control parses wrapper and returns ControlInfo."""
    adapter = UiaAdapter()

    mock_rect = MagicMock(left=10, top=20, right=100, bottom=50)
    mock_wrapper = MagicMock()
    mock_wrapper.rectangle.return_value = mock_rect
    mock_wrapper.is_enabled.return_value = True
    mock_wrapper.is_visible.return_value = True
    mock_wrapper.element_info.automation_id = "btn_ok"
    mock_wrapper.element_info.name = "OK"
    mock_wrapper.element_info.control_type = "Button"
    mock_wrapper.element_info.class_name = "Button"
    mock_wrapper.element_info.handle = 12345

    mock_elem = MagicMock()
    mock_elem.exists.return_value = True
    mock_elem.wrapper_object.return_value = mock_wrapper

    mock_win = MagicMock()
    mock_win.child_window.return_value = mock_elem

    with patch.object(adapter._win32, "is_window", return_value=True):
        with patch.object(adapter, "_get_app_window", return_value=mock_win):
            ctrl = adapter.find_control(12345, name="OK")
            assert isinstance(ctrl, ControlInfo)
            assert ctrl.automation_id == "btn_ok"
            assert ctrl.name == "OK"
            assert ctrl.rect == Rect(left=10, top=20, right=100, bottom=50)
            assert ctrl.is_enabled is True


def test_uia_find_control_not_found() -> None:
    """Verify ElementNotFoundError when element does not exist."""
    adapter = UiaAdapter()
    mock_elem = MagicMock()
    mock_elem.exists.return_value = False

    mock_win = MagicMock()
    mock_win.child_window.return_value = mock_elem

    with patch.object(adapter._win32, "is_window", return_value=True):
        with patch.object(adapter, "_get_app_window", return_value=mock_win):
            with pytest.raises(ElementNotFoundError):
                adapter.find_control(12345, name="Nonexistent")


def test_uia_invoke_disabled_control() -> None:
    """Verify ElementUnavailableError when invoking a disabled control."""
    adapter = UiaAdapter()
    mock_wrapper = MagicMock()
    mock_wrapper.is_enabled.return_value = False

    mock_elem = MagicMock()
    mock_elem.exists.return_value = True
    mock_elem.wrapper_object.return_value = mock_wrapper

    mock_win = MagicMock()
    mock_win.child_window.return_value = mock_elem

    with patch.object(adapter._win32, "is_window", return_value=True):
        with patch.object(adapter, "_get_app_window", return_value=mock_win):
            with pytest.raises(ElementUnavailableError):
                adapter.invoke_control(12345, name="DisabledBtn")
