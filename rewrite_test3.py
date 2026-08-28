import os
import re

with open('tests/unit/test_tools_ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''def test_execute_click_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    from datetime import datetime, timedelta, timezone
    
    mock_adapter = MagicMock()
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_control_invoked.return_value = MagicMock(ok=True)
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

    result = execute_click_element({"snapshot_id": "snap-1", "target_ref": "snap-1::btn_save"}, task_context=task_ctx)
    assert result.ok
    assert result.verified
    assert mock_adapter.invoke_control.called
    assert "Save" in result.factual_message

def test_execute_click_element_not_found(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    from datetime import datetime, timedelta, timezone

    mock_adapter = MagicMock()
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

    result = execute_click_element({"snapshot_id": "snap-1", "target_ref": "snap-1::btn_missing"}, task_context=task_ctx)
    assert not result.ok
    assert "Failed to click" in result.factual_message

def test_execute_type_into_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_active_ctx_cls: MagicMock) -> None:
    from datetime import datetime, timedelta, timezone

    mock_adapter = MagicMock()
    mock_adapter_cls.return_value = mock_adapter

    mock_verifier = MagicMock()
    mock_verifier.verify_text_entered.return_value = MagicMock(ok=True)
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
        "auto_id": "txt_input",
        "name": "Input",
        "control_type": "Edit",
    }
    task_ctx.cancellation_token = MagicMock(is_cancelled=False)

    result = execute_type_into_element({"text": "Hello World", "snapshot_id": "snap-2", "target_ref": "snap-2::txt_input"}, task_context=task_ctx)
    assert result.ok
    assert result.verified
    assert mock_adapter.type_text.called
'''

code = re.sub(
    r'def test_execute_click_element_success.*?@patch\("pluma.tools.ui.ActiveWindowContext"\)\n@patch\("pluma.tools.ui.UiaAdapter"\)\n@patch\("pluma.tools.ui.ScreenVerifier"\)\ndef test_execute_type_into_element_not_found',
    replacement + '\n@patch("pluma.tools.ui.ActiveWindowContext")\n@patch("pluma.tools.ui.UiaAdapter")\n@patch("pluma.tools.ui.ScreenVerifier")\ndef test_execute_type_into_element_not_found',
    code,
    flags=re.DOTALL
)

with open('tests/unit/test_tools_ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('UI test rewrite done')
