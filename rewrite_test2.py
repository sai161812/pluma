import os
import re

with open('tests/unit/test_tools_ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = re.sub(
    r'''    mock_builder = MagicMock\(\)
    mock_snapshot = MagicMock\(spec=ScreenSnapshot\)''',
    '''    mock_builder = MagicMock()
    mock_snapshot = MagicMock(spec=ScreenSnapshot)
    mock_snapshot.snapshot_id = "mock-snap-id"
    mock_snapshot.model_dump.return_value = {}''',
    code
)

code = re.sub(
    r'''def test_execute_click_element_success\(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock\) -> None:
    mock_context = MagicMock\(\)
    mock_context\.get_active_window\.return_value = ActiveWindowInfo\(
        hwnd=456, process_name="app\.exe", window_title="App", is_valid=True
    \)
    mock_context\.get_process_creation_time_ns\.return_value = 1000
    mock_context_cls\.return_value = mock_context

    mock_task_ctx = MagicMock\(\)
    mock_reg = MagicMock\(\)
    mock_task_ctx\.snapshot_registry = mock_reg
    mock_snap = MagicMock\(\)
    mock_snap\.hwnd = 456
    mock_snap\.pid = None
    mock_snap\.process_creation_time_ns = None
    mock_snap\.dpi_scale = None
    mock_reg\.resolve\.return_value = mock_snap

    mock_elem = MagicMock\(\)
    mock_elem\.uia_automation_id = "btn1"
    mock_elem\.label = "OK"
    mock_elem\.control_type = "Button"
    mock_reg\.resolve_element\.return_value = mock_elem''',
    '''def test_execute_click_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=456, process_name="app.exe", window_title="App", is_valid=True, pid=123, dpi_scale=1.0
    )
    mock_context.get_process_creation_time_ns.return_value = 1000
    mock_context_cls.return_value = mock_context

    mock_task_ctx = MagicMock()
    mock_task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 123,
        "snapshot_creation_time_ns": 1000,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn1",
        "name": "OK",
        "control_type": "Button",
    }''',
    code
)

code = re.sub(
    r'''def test_execute_click_element_not_found\(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock\) -> None:
    mock_context = MagicMock\(\)
    mock_context\.get_active_window\.return_value = ActiveWindowInfo\(
        hwnd=456, process_name="app\.exe", window_title="App", is_valid=True
    \)
    mock_context_cls\.return_value = mock_context

    mock_task_ctx = MagicMock\(\)
    mock_reg = MagicMock\(\)
    mock_task_ctx\.snapshot_registry = mock_reg
    mock_snap = MagicMock\(\)
    mock_snap\.hwnd = 456
    mock_snap\.pid = None
    mock_snap\.process_creation_time_ns = None
    mock_snap\.dpi_scale = None
    mock_reg\.resolve\.return_value = mock_snap

    mock_elem = MagicMock\(\)
    mock_elem\.uia_automation_id = "btn1"
    mock_elem\.label = "OK"
    mock_elem\.control_type = "Button"
    mock_reg\.resolve_element\.return_value = mock_elem''',
    '''def test_execute_click_element_not_found(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=456, process_name="app.exe", window_title="App", is_valid=True, pid=123, dpi_scale=1.0
    )
    mock_context_cls.return_value = mock_context

    mock_task_ctx = MagicMock()
    mock_task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 456,
        "snapshot_pid": 123,
        "snapshot_creation_time_ns": None,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "btn1",
        "name": "OK",
        "control_type": "Button",
    }''',
    code
)

code = re.sub(
    r'''def test_execute_type_into_element_success\(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock\) -> None:
    mock_context = MagicMock\(\)
    mock_context\.get_active_window\.return_value = ActiveWindowInfo\(
        hwnd=789, process_name="app\.exe", window_title="App", is_valid=True
    \)
    mock_context_cls\.return_value = mock_context

    mock_task_ctx = MagicMock\(\)
    mock_reg = MagicMock\(\)
    mock_task_ctx\.snapshot_registry = mock_reg
    mock_snap = MagicMock\(\)
    mock_snap\.hwnd = 789
    mock_snap\.pid = None
    mock_snap\.process_creation_time_ns = None
    mock_snap\.dpi_scale = None
    mock_reg\.resolve\.return_value = mock_snap

    mock_elem = MagicMock\(\)
    mock_elem\.uia_automation_id = "txt1"
    mock_elem\.label = "Name"
    mock_elem\.control_type = "Edit"
    mock_reg\.resolve_element\.return_value = mock_elem''',
    '''def test_execute_type_into_element_success(mock_verifier_cls: MagicMock, mock_adapter_cls: MagicMock, mock_context_cls: MagicMock) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=789, process_name="app.exe", window_title="App", is_valid=True, pid=123, dpi_scale=1.0
    )
    mock_context_cls.return_value = mock_context

    mock_task_ctx = MagicMock()
    mock_task_ctx.grounded_ui_target = {
        "snapshot_hwnd": 789,
        "snapshot_pid": 123,
        "snapshot_creation_time_ns": None,
        "snapshot_dpi_scale": 1.0,
        "auto_id": "txt1",
        "name": "Name",
        "control_type": "Edit",
    }''',
    code
)


with open('tests/unit/test_tools_ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('UI test update done')
