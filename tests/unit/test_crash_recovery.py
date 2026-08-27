"""tests/unit/test_crash_recovery.py — Unit tests for startup crash recovery manager."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import pytest

from pluma.config.paths import PlumaPaths
from pluma.core.recovery import CrashRecoveryManager
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActionRecord, ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection


@pytest.fixture
def test_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        local_root = Path(temp_dir) / "LocalPluma"
        roaming_root = Path(temp_dir) / "RoamingPluma"
        paths = PlumaPaths(local_app_data=local_root, roaming_app_data=roaming_root)
        paths.ensure_directories()

        db = DbConnection(str(paths.db_path))
        db.open()
        ledger = ActivityLedger(db=db)

        yield {
            "paths": paths,
            "db": db,
            "ledger": ledger,
        }

        db.close()


def test_database_integrity_check(test_env: dict) -> None:
    """Verify that healthy database passes integrity check."""
    mgr = CrashRecoveryManager(db=test_env["db"], paths=test_env["paths"])
    assert mgr.check_database_integrity() is True


def test_stale_tasks_reconciled_to_aborted_by_crash(test_env: dict) -> None:
    """Verify that tasks in non-terminal states are reconciled as ABORTED_BY_CRASH on startup."""
    ledger: ActivityLedger = test_env["ledger"]
    db: DbConnection = test_env["db"]
    paths: PlumaPaths = test_env["paths"]

    # 1. Insert tasks in various states
    # Succeeded task (should remain SUCCEEDED)
    ledger.insert_task(TaskRecord(task_id="task-ok", request_id="req-1", input_mode="TEXT", command_text="volume 50", route="FAST", final_state="SUCCEEDED"))

    # Stale/crashed tasks in non-terminal states
    ledger.insert_task(TaskRecord(task_id="task-running", request_id="req-2", input_mode="TEXT", command_text="slow task", route="SMART", final_state="RUNNING"))
    ledger.insert_task(TaskRecord(task_id="task-stopping", request_id="req-3", input_mode="TEXT", command_text="stopped task", route="SMART", final_state="STOPPING"))
    ledger.insert_task(TaskRecord(task_id="task-rollback", request_id="req-4", input_mode="TEXT", command_text="rolling back task", route="SMART", final_state="ROLLING_BACK"))
    ledger.insert_task(TaskRecord(task_id="task-created", request_id="req-5", input_mode="TEXT", command_text="created task", route="SMART", final_state="CREATED"))

    # 2. Run CrashRecoveryManager startup pass
    mgr = CrashRecoveryManager(db=db, paths=paths)
    res = mgr.reconcile_startup()

    assert res.stale_tasks_recovered == 4
    assert set(res.recovered_task_ids) == {
        "task-running",
        "task-stopping",
        "task-rollback",
        "task-created",
    }
    assert res.db_integrity_ok is True

    # 3. Query database to verify final states
    query = ActivityQuery(db=db)
    ok_task = query.task_by_id("task-ok")
    assert ok_task["final_state"] == "SUCCEEDED"

    for tid in ["task-running", "task-stopping", "task-rollback", "task-created"]:
        t = query.task_by_id(tid)
        assert t["final_state"] == TaskState.ABORTED_BY_CRASH.value
        assert t["stop_reason"] == "CRASH"
        assert t["completed_at"] is not None


def test_orphaned_task_temp_directories_cleaned(test_env: dict) -> None:
    """Verify that leftover task scratch spaces are cleaned up on startup."""
    paths: PlumaPaths = test_env["paths"]
    db: DbConnection = test_env["db"]

    # Create dummy temp folders under paths.temp_dir
    dir_1 = paths.task_temp_dir("crashed-task-1")
    dir_2 = paths.task_temp_dir("crashed-task-2")
    dir_1.mkdir(parents=True, exist_ok=True)
    dir_2.mkdir(parents=True, exist_ok=True)
    (dir_1 / "scratch.txt").write_text("temporary data")
    (dir_2 / "scratch.txt").write_text("temporary data")

    assert dir_1.exists()
    assert dir_2.exists()

    mgr = CrashRecoveryManager(db=db, paths=paths)
    cleaned = mgr.cleanup_orphaned_task_directories()

    assert cleaned == 2
    assert not dir_1.exists()
    assert not dir_2.exists()
