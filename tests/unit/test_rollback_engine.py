"""Unit tests for RollbackEngine (Spec §13, §17)."""
import json
import pytest
from pathlib import Path
from pluma.core.cancellation import CancellationToken, StopReason
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, ActivityQuery, TaskRecord, UndoRecord
from pluma.memory.db import DbConnection
from pluma.rollback.engine import RollbackEngine, RollbackResult
from pluma.rollback.recipes import RollbackRecipes


@pytest.fixture
def memory_db():
    conn = DbConnection(":memory:")
    conn.open()
    yield conn
    conn.close()


def test_rollback_task_in_reverse_order(memory_db, tmp_path):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)
    recipes = RollbackRecipes()
    engine = RollbackEngine(ledger=ledger, query=query, recipes=recipes)

    task_id = "task-rollback-1"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-1",
        input_mode="text",
        command_text="Move file and rename file",
    ))

    # File setup
    file1 = tmp_path / "file1_original.txt"
    file1_moved = tmp_path / "file1_moved.txt"
    file1_moved.write_text("data 1")

    file2 = tmp_path / "file2_old.txt"
    file2_new = tmp_path / "file2_renamed.txt"
    file2_new.write_text("data 2")

    # Step 0: move_file
    act1_id = ledger.insert_action(ActionRecord(
        task_id=task_id,
        step_index=0,
        tool="move_file",
        args_raw={"source": str(file1), "destination": str(file1_moved)},
        risk="MEDIUM",
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act1_id,
        undo_data={"action": "move_file", "source": str(file1), "destination": str(file1_moved)},
    ))

    # Step 1: rename_file
    act2_id = ledger.insert_action(ActionRecord(
        task_id=task_id,
        step_index=1,
        tool="rename_file",
        args_raw={"path": str(file2), "new_name": "file2_renamed.txt"},
        risk="MEDIUM",
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act2_id,
        undo_data={"action": "rename_file", "original_path": str(file2), "new_path": str(file2_new)},
    ))

    # Execute rollback on entire task
    result = engine.rollback_task(task_id)

    assert result.all_ok
    assert result.steps_attempted == 2
    assert result.steps_succeeded == 2
    assert result.steps_failed == 0
    assert not result.has_residual

    # Check that rename_file was reversed first, then move_file
    assert result.step_results[0].action == "rename_file"
    assert result.step_results[1].action == "move_file"

    # Both files restored
    assert file1.exists()
    assert not file1_moved.exists()
    assert file2.exists()
    assert not file2_new.exists()

    # Check ledger records updated
    undo1 = query.undo_record_for_action(act1_id)
    assert undo1["rollback_attempted"] == 1
    assert undo1["rollback_ok"] == 1

    undo2 = query.undo_record_for_action(act2_id)
    assert undo2["rollback_attempted"] == 1
    assert undo2["rollback_ok"] == 1


def test_rollback_partial_failure_marks_residual(memory_db, tmp_path):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)
    engine = RollbackEngine(ledger=ledger, query=query)

    task_id = "task-partial-fail"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-pf",
        input_mode="text",
        command_text="Move missing file",
    ))

    # Action whose destination no longer exists
    act_id = ledger.insert_action(ActionRecord(
        task_id=task_id,
        step_index=0,
        tool="move_file",
        args_raw={"source": str(tmp_path / "a.txt"), "destination": str(tmp_path / "missing.txt")},
        risk="MEDIUM",
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act_id,
        undo_data={"action": "move_file", "source": str(tmp_path / "a.txt"), "destination": str(tmp_path / "missing.txt")},
    ))

    result = engine.rollback_task(task_id)

    assert not result.all_ok
    assert result.has_residual
    assert result.steps_failed == 1

    undo_rec = query.undo_record_for_action(act_id)
    assert undo_rec["rollback_attempted"] == 1
    assert undo_rec["rollback_ok"] == 0


def test_rollback_last_reversible(memory_db, tmp_path):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)
    engine = RollbackEngine(ledger=ledger, query=query)

    task_id = "task-undo-last"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-ul",
        input_mode="text",
        command_text="Two steps",
    ))

    f1 = tmp_path / "f1.txt"
    f1_m = tmp_path / "f1_m.txt"
    f1_m.write_text("1")

    f2 = tmp_path / "f2.txt"
    f2_m = tmp_path / "f2_m.txt"
    f2_m.write_text("2")

    # Step 0
    act0 = ledger.insert_action(ActionRecord(
        task_id=task_id, step_index=0, tool="move_file", args_raw={}, risk="MEDIUM"
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act0, undo_data={"action": "move_file", "source": str(f1), "destination": str(f1_m)}
    ))

    # Step 1
    act1 = ledger.insert_action(ActionRecord(
        task_id=task_id, step_index=1, tool="move_file", args_raw={}, risk="MEDIUM"
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act1, undo_data={"action": "move_file", "source": str(f2), "destination": str(f2_m)}
    ))

    # Rollback only last
    step_res = engine.rollback_last_reversible(task_id=task_id)
    assert step_res.ok
    assert f2.exists()
    assert not f2_m.exists()
    # Step 0 is still untouched
    assert not f1.exists()
    assert f1_m.exists()


def test_task_supervisor_stop_invokes_rollback_engine(memory_db, tmp_path):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)
    engine = RollbackEngine(ledger=ledger, query=query)
    supervisor = TaskSupervisor(ledger=ledger, rollback_engine=engine)

    capsule = supervisor.create_task("req-stop-test")
    ledger.insert_task(TaskRecord(
        task_id=capsule.task_id,
        request_id="req-stop-test",
        input_mode="text",
        command_text="Move file test",
    ))
    supervisor.start_task(capsule.task_id)

    # Put an action in the DB
    dst = tmp_path / "target.txt"
    src = tmp_path / "src.txt"
    dst.write_text("payload")

    act_id = ledger.insert_action(ActionRecord(
        task_id=capsule.task_id, step_index=0, tool="move_file", args_raw={}, risk="MEDIUM"
    ))
    ledger.insert_undo_record(UndoRecord(
        action_row_id=act_id, undo_data={"action": "move_file", "source": str(src), "destination": str(dst)}
    ))

    # Stop task
    supervisor.stop_task(capsule.task_id, reason=StopReason.USER_STOP)

    assert capsule.state == TaskState.STOPPED
    assert src.exists()
    assert not dst.exists()

    # Check ledger updated
    task_row = query.task_by_id(capsule.task_id)
    assert task_row["final_state"] == "STOPPED"
    assert task_row["stop_reason"] == "user_stop"
