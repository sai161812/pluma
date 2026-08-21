"""tests.unit.test_tool_runner_ledger — Tests for ToolRegistry execution runner & Activity Ledger integration."""

import time
from pathlib import Path
import pytest

from pluma.core.cancellation import TaskCancelledError
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.registry import (
    ToolArgumentError,
    ToolRegistry,
    UnknownToolError,
    register_default_tools,
)


@pytest.fixture
def db_conn(tmp_path: Path) -> DbConnection:
    conn = DbConnection(str(tmp_path / "test_ledger.db"))
    conn.open()
    return conn


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_registry_contains_at_least_10_tools(registry: ToolRegistry) -> None:
    """Phase 2 Gate: At least 10 tools execute through one registry."""
    names = registry.all_names()
    assert len(names) >= 10
    assert "open_app" in names
    assert "list_files" in names
    assert "move_file" in names
    assert "set_volume" in names
    assert "get_system_status" in names


def test_execute_records_to_activity_ledger(
    registry: ToolRegistry, db_conn: DbConnection, tmp_path: Path
) -> None:
    """Phase 2 Gate: Every state change writes action, verification and risk data."""
    ledger = ActivityLedger(db_conn)
    query = ActivityQuery(db_conn)

    # 1. Create a task
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task("req-gate-1")
    supervisor.start_task(capsule.task_id)

    ledger.insert_task(TaskRecord(
        task_id=capsule.task_id,
        request_id=capsule.request_id,
        input_mode="text",
        command_text="create folder test_dir",
        started_at="2026-08-21T00:00:00Z",
    ))

    # 2. Execute create_folder through the registry runner
    target_folder = str(tmp_path / "test_dir")
    res = registry.execute(
        tool_name="create_folder",
        arguments={"path": target_folder},
        task_context=capsule,
        ledger=ledger,
        step_index=0,
    )

    assert res.ok is True
    assert res.verified is True

    # Allow async DB writer to commit
    time.sleep(0.3)

    # 3. Verify SQLite Activity Ledger contains action and undo records
    actions = query.actions_for_task(capsule.task_id)
    assert len(actions) == 1
    act = actions[0]
    assert act["tool"] == "create_folder"
    assert act["risk"] == "LOW"
    assert act["verified"] == 1
    assert act["duration_ms"] is not None

    undo_recs = query.available_undo_records_for_task(capsule.task_id)
    assert len(undo_recs) == 1
    assert undo_recs[0]["action_id"] == act["id"]


def test_reversible_tool_produces_usable_undo(
    registry: ToolRegistry, tmp_path: Path
) -> None:
    """Phase 2 Gate: Reversible tools produce usable undo records."""
    src = tmp_path / "before.txt"
    src.write_text("reversibility test")
    dst = tmp_path / "after.txt"

    supervisor = TaskSupervisor()
    capsule = supervisor.create_task("req-gate-2")
    supervisor.start_task(capsule.task_id)

    # Move file
    res = registry.execute(
        tool_name="move_file",
        arguments={"source": str(src), "destination": str(dst)},
        task_context=capsule,
    )
    assert res.ok is True
    assert res.verified is True
    assert dst.exists()
    assert not src.exists()
    assert len(capsule.undo_stack) == 1

    # Execute undo_last
    undo_res = registry.execute(
        tool_name="undo_last",
        arguments={},
        task_context=capsule,
    )
    assert undo_res.ok is True
    assert undo_res.verified is True
    assert src.exists()
    assert not dst.exists()


def test_cancellation_latch_blocks_execution(registry: ToolRegistry) -> None:
    """STOP latch prevents tool execution."""
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task("req-gate-3")
    supervisor.start_task(capsule.task_id)
    supervisor.stop_task(capsule.task_id)

    with pytest.raises(TaskCancelledError):
        registry.execute(
            tool_name="list_files",
            arguments={"path": "."},
            task_context=capsule,
        )


def test_argument_validation_rejects_bad_input(registry: ToolRegistry) -> None:
    """Invalid arguments fail before execution."""
    with pytest.raises(ToolArgumentError):
        registry.execute(
            tool_name="set_volume",
            arguments={"level": 150},  # ge=0, le=100
        )
