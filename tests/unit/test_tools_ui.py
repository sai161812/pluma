"""tests/unit/test_tools_ui.py — Phase 7: UI interaction tools unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from pluma.adapters.base import ControlInfo, ElementNotFoundError, Rect
from pluma.perception.context import ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement, ScreenSnapshot
from pluma.tools.base import RiskClass, ToolResult
from pluma.tools.ui import (
    ALL_UI_TOOLS,
    CLICK_ELEMENT_SPEC,
    INSPECT_ACTIVE_WINDOW_SPEC,
    TYPE_INTO_ELEMENT_SPEC,
    execute_click_element,
    execute_inspect_active_window,
    execute_type_into_element,
)


def test_ui_tool_specs_metadata() -> None:
    assert len(ALL_UI_TOOLS) == 3
    
    assert INSPECT_ACTIVE_WINDOW_SPEC.name == "inspect_active_window"
    assert INSPECT_ACTIVE_WINDOW_SPEC.risk_class == RiskClass.READ

    assert CLICK_ELEMENT_SPEC.name == "click_element"
    assert CLICK_ELEMENT_SPEC.risk_class == RiskClass.LOW

    assert TYPE_INTO_ELEMENT_SPEC.name == "type_into_element"
    assert TYPE_INTO_ELEMENT_SPEC.risk_class == RiskClass.LOW


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaSnapshotBuilder")
def test_execute_inspect_active_window(mock_builder_cls: MagicMock, mock_context_cls: MagicMock) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=123,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        is_valid=True,
    )
    mock_context_cls.return_value = mock_context

    mock_builder = MagicMock()
    mock_snapshot = MagicMock(spec=ScreenSnapshot)
    mock_snapshot.controls = [
        ScreenElement(
            snapshot_id="snap-1",
            source=ElementSource.UIA,
            label="File",
            control_type="MenuItem",
            bounds=BoundingBox(left=0, top=0, right=50, bottom=25),
            confidence=1.0,
            invocation_capability="invoke",
        )
    ]
    mock_builder.capture.return_value = mock_snapshot
    mock_builder_cls.return_value = mock_builder

    result = execute_inspect_active_window({"include_controls": True, "max_controls": 10})
    assert result.ok
    assert result.verified
    assert result.data["hwnd"] == 123
    assert result.data["control_count"] == 1
    assert result.data["controls"][0]["label"] == "File"


@patch("pluma.tools.ui.UiaAdapter")
@patch("pluma.tools.ui.ScreenVerifier")
def test_execute_click_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_control_invoked.return_value = MagicMock(ok=True)
    mock_verifier_cls.return_value = mock_verifier

    result = execute_click_element({"name": "Save", "hwnd": 456})
    assert result.ok
    assert result.verified
    assert mock_adapter.invoke_control.called
    assert "Save" in result.factual_message


@patch("pluma.tools.ui.UiaAdapter")
def test_execute_click_element_not_found(mock_adapter_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter.invoke_control.side_effect = ElementNotFoundError("Control not found")
    mock_adapter_cls.return_value = mock_adapter

    result = execute_click_element({"name": "NonExistentButton", "hwnd": 456})
    assert not result.ok
    assert not result.verified
    assert "Failed to click" in result.factual_message


@patch("pluma.tools.ui.UiaAdapter")
@patch("pluma.tools.ui.ScreenVerifier")
def test_execute_type_into_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_control_text.return_value = MagicMock(ok=True)
    mock_verifier_cls.return_value = mock_verifier

    result = execute_type_into_element({"text": "Hello World", "auto_id": "txtInput", "hwnd": 789})
    assert result.ok
    assert result.verified
    assert mock_adapter.set_control_text.called
    assert "txtInput" in result.factual_message
