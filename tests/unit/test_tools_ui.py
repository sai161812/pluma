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
    CLICK_OCR_TEXT_SPEC,
    INSPECT_ACTIVE_WINDOW_SPEC,
    TYPE_INTO_ELEMENT_SPEC,
    execute_click_element,
    execute_inspect_active_window,
    execute_type_into_element,
)


def test_ui_tool_specs_metadata() -> None:
    assert len(ALL_UI_TOOLS) == 4

    assert INSPECT_ACTIVE_WINDOW_SPEC.name == "inspect_active_window"
    assert INSPECT_ACTIVE_WINDOW_SPEC.risk_class == RiskClass.READ

    assert CLICK_ELEMENT_SPEC.name == "click_element"
    assert CLICK_ELEMENT_SPEC.risk_class == RiskClass.LOW

    assert TYPE_INTO_ELEMENT_SPEC.name == "type_into_element"
    assert TYPE_INTO_ELEMENT_SPEC.risk_class == RiskClass.LOW

    assert CLICK_OCR_TEXT_SPEC.name == "click_ocr_text"
    assert CLICK_OCR_TEXT_SPEC.risk_class == RiskClass.LOW


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
    mock_snapshot.snapshot_id = "mock-snap-id"
    mock_snapshot.model_dump.return_value = {}
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


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaAdapter")
@patch("pluma.tools.ui.ScreenVerifier")
def test_execute_click_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter.find_control.return_value.is_enabled = True
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_control_enabled.return_value = MagicMock(ok=True)
    mock_verifier_cls.return_value = mock_verifier

    mock_ctx = MagicMock()
    active_win = MagicMock()
    active_win.is_valid = True
    active_win.hwnd = 456
    active_win.pid = 1000
    active_win.rect = BoundingBox(left=0, top=0, right=800, bottom=600)
    active_win.dpi_scale = 1.0
    mock_ctx.get_active_window.return_value = active_win
    mock_ctx.get_process_creation_time_ns.return_value = 123456789
    mock_active_ctx_cls.return_value = mock_ctx

    task_ctx = MagicMock()
    task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 1000,
        "snapshot_creation_time_ns": 123456789,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn_save",
        "name": "Save",
        "control_type": "Button",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_click_element({
        "snapshot_id": "snap-1", "target_ref": "snap-1::btn_save",
        "expected_enabled": False,
    }, task_context=task_ctx)
    assert result.ok
    assert result.verified
    assert mock_adapter.invoke_control.called
    mock_verifier.verify_control_enabled.assert_called_once_with(
        hwnd=456, expected_enabled=False, auto_id="btn_save", name="Save"
    )
    assert "Save" in result.factual_message


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaAdapter")
@patch("pluma.tools.ui.ScreenVerifier")
def test_execute_click_element_without_postcondition_is_refused_before_dispatch(
    mock_verifier_cls: MagicMock,
    mock_adapter_cls: MagicMock,
    mock_active_ctx_cls: MagicMock,
) -> None:
    mock_ctx = MagicMock()
    active = MagicMock()
    active.is_valid = True
    active.hwnd = 456
    active.pid = 1000
    active.rect = BoundingBox(left=0, top=0, right=800, bottom=600)
    active.dpi_scale = 1.0
    mock_ctx.get_active_window.return_value = active
    mock_active_ctx_cls.return_value = mock_ctx

    task_ctx = MagicMock()
    task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 1000,
        "snapshot_creation_time_ns": None,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn_submit",
        "name": "Submit",
        "control_type": "Button",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_click_element(
        {"snapshot_id": "snap-1", "target_ref": "snap-1::btn_submit"},
        task_context=task_ctx,
    )

    assert not result.ok
    assert not result.verified
    assert result.error_code == "UI_POSTCONDITION_REQUIRED"
    mock_adapter_cls.return_value.invoke_control.assert_not_called()
    mock_verifier_cls.return_value.verify_control_enabled.assert_not_called()


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaAdapter")
def test_execute_click_element_refuses_when_expected_state_is_already_present(
    mock_adapter_cls: MagicMock,
    mock_active_ctx_cls: MagicMock,
) -> None:
    mock_ctx = MagicMock()
    active = MagicMock()
    active.is_valid = True
    active.hwnd = 456
    active.pid = 1000
    active.rect = BoundingBox(left=0, top=0, right=800, bottom=600)
    active.dpi_scale = 1.0
    mock_ctx.get_active_window.return_value = active
    mock_ctx.get_process_creation_time_ns.return_value = 123456789
    mock_active_ctx_cls.return_value = mock_ctx

    adapter = mock_adapter_cls.return_value
    adapter.find_control.return_value.is_enabled = False
    task_ctx = MagicMock()
    task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 1000,
        "snapshot_creation_time_ns": 123456789,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn_submit",
        "name": "Submit",
        "control_type": "Button",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_click_element(
        {
            "snapshot_id": "snap-1",
            "target_ref": "snap-1::btn_submit",
            "expected_enabled": False,
        },
        task_context=task_ctx,
    )

    assert not result.ok
    assert result.error_code == "UI_NO_EXPECTED_TRANSITION"
    adapter.invoke_control.assert_not_called()

@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaAdapter")
def test_execute_click_element_not_found(mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter.find_control.return_value.is_enabled = True
    mock_adapter.invoke_control.side_effect = Exception("Not found")
    mock_adapter_cls.return_value = mock_adapter

    mock_ctx = MagicMock()
    active_win = MagicMock()
    active_win.is_valid = True
    active_win.hwnd = 456
    active_win.pid = 1000
    active_win.rect = BoundingBox(left=0, top=0, right=800, bottom=600)
    active_win.dpi_scale = 1.0
    mock_ctx.get_active_window.return_value = active_win
    mock_ctx.get_process_creation_time_ns.return_value = 123456789
    mock_active_ctx_cls.return_value = mock_ctx

    task_ctx = MagicMock()
    task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 1000,
        "snapshot_creation_time_ns": 123456789,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn_missing",
        "name": "Missing",
        "control_type": "Button",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_click_element({
        "snapshot_id": "snap-1", "target_ref": "snap-1::btn_missing",
        "expected_enabled": False,
    }, task_context=task_ctx)
    assert not result.ok
    pass

@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.tools.ui.UiaAdapter")
@patch("pluma.tools.ui.ScreenVerifier")
def test_execute_type_into_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    mock_adapter = MagicMock()
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_control_text.return_value = MagicMock(ok=True)
    mock_verifier_cls.return_value = mock_verifier

    mock_ctx = MagicMock()
    active_win = MagicMock()
    active_win.is_valid = True
    active_win.hwnd = 789
    active_win.pid = 1000
    active_win.rect = BoundingBox(left=0, top=0, right=800, bottom=600)
    active_win.dpi_scale = 1.0
    mock_ctx.get_active_window.return_value = active_win
    mock_ctx.get_process_creation_time_ns.return_value = 123456789
    mock_active_ctx_cls.return_value = mock_ctx

    task_ctx = MagicMock()
    task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 789,
        "snapshot_pid": 1000,
        "snapshot_creation_time_ns": 123456789,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "txt_input",
        "name": "Input",
        "control_type": "Edit",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_type_into_element({"text": "Hello World", "snapshot_id": "snap-2", "target_ref": "snap-2::txt_input"}, task_context=task_ctx)
    assert result.ok
    assert result.verified
    assert mock_adapter.set_control_text.called
