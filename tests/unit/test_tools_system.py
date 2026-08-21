"""tests.unit.test_tools_system — Unit and verification tests for System tools."""

import pytest

from pluma.core.task_supervisor import TaskSupervisor
from pluma.tools.system import (
    execute_get_system_status,
    execute_show_activity,
    execute_stop_current,
    execute_undo_last,
)
from pluma.tools.registry import ToolRegistry, register_default_tools


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_get_system_status() -> None:
    res = execute_get_system_status({})
    assert res.ok is True
    assert res.verified is True
    assert "disk_free_gb" in res.data
    assert "os" in res.data


def test_show_activity() -> None:
    res = execute_show_activity({"limit": 5})
    assert res.ok is True
    assert res.verified is True
    assert "records" in res.data


def test_stop_current() -> None:
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task("req-sys-1")
    supervisor.start_task(capsule.task_id)

    res = execute_stop_current({}, task_context=capsule)
    assert res.ok is True
    assert capsule.cancellation_token.is_cancelled is True


def test_undo_last_file_move(tmp_path: object) -> None:
    from pathlib import Path
    import shutil
    
    tmp = Path(str(tmp_path))
    src = tmp / "src.txt"
    src.write_text("undo test")
    dst = tmp / "dst.txt"
    shutil.move(str(src), str(dst))

    supervisor = TaskSupervisor()
    capsule = supervisor.create_task("req-undo-1")
    capsule.undo_stack.append({
        "action": "move_file",
        "source": str(src),
        "destination": str(dst),
    })

    res = execute_undo_last({}, task_context=capsule)
    assert res.ok is True
    assert res.verified is True
    assert src.exists()
    assert not dst.exists()
