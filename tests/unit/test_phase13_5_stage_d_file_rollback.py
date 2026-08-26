"""tests/unit/test_phase13_5_stage_d_file_rollback.py — Stage D File Operations and Rollback regression tests."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest
from pydantic import ValidationError

from pluma.memory.activity import ActionRecord, ActivityLedger, ActivityQuery, TaskRecord, UndoRecord
from pluma.memory.db import DbConnection
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.files import RenameFileArgs, execute_move_file, execute_rename_file
from pluma.tools.system import execute_undo_last


def test_stage_d_rename_file_directory_traversal_defense() -> None:
    """Gate D: Verify rename_file rejects path traversal characters, subpaths, and reserved device names."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        test_file = root / "source.txt"
        test_file.write_text("sample content")

        # 1. Pydantic validation rejects path traversal
        with pytest.raises(ValidationError):
            RenameFileArgs(path=str(test_file), new_name="../escaped.txt")

        with pytest.raises(ValidationError):
            RenameFileArgs(path=str(test_file), new_name="sub/nested.txt")

        with pytest.raises(ValidationError):
            RenameFileArgs(path=str(test_file), new_name="CON")

        with pytest.raises(ValidationError):
            RenameFileArgs(path=str(test_file), new_name="NUL.txt")

        # 2. Runtime executor rejects traversal attempts
        res = execute_rename_file({"path": str(test_file), "new_name": "..\\escaped.txt"})
        assert res.ok is False
        assert "traversal" in res.error.lower()


def test_stage_d_move_file_overwrite_slot_preservation_and_rollback() -> None:
    """Gate D: Verify overwriting move preserves previous destination content and restores both on rollback."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        src = root / "new_doc.txt"
        dst = root / "important_original.txt"

        src.write_text("NEW CONTENT")
        dst.write_text("ORIGINAL CONTENT")

        # Execute move with overwrite=True
        res = execute_move_file({"source": str(src), "destination": str(dst), "overwrite": True})
        assert res.ok is True
        assert dst.read_text() == "NEW CONTENT"
        assert not src.exists()
        assert res.data.get("preserved_destination_backup") is not None

        # Execute rollback using captured undo data
        undo_data = {
            "action": "move_file",
            "source": str(src),
            "destination": str(dst),
            "preserved_destination_backup": res.data["preserved_destination_backup"],
        }
        recipes = RollbackRecipes()
        rb_res = recipes.apply("move_file", undo_data)
        assert rb_res.ok is True

        # Verify BOTH source and original destination are restored intact
        assert src.exists()
        assert src.read_text() == "NEW CONTENT"
        assert dst.exists()
        assert dst.read_text() == "ORIGINAL CONTENT"


def test_stage_d_sqlite_persistent_undo_last() -> None:
    """Gate D: Verify execute_undo_last finds and consumes persistent SQLite Activity Ledger undo records."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "activity.db"
        db = DbConnection(str(db_path))
        db.open()
        try:
            ledger = ActivityLedger(db)
            query = ActivityQuery(db)

            src = Path(td) / "file1.txt"
            dst = Path(td) / "file1_moved.txt"
            src.write_text("Hello Persistent Undo")

            # 1. Execute move
            res = execute_move_file({"source": str(src), "destination": str(dst)})
            assert res.ok is True
            assert dst.exists()
            assert not src.exists()

            # 2. Record task, action and undo to SQLite Activity Ledger
            ledger.insert_task(
                TaskRecord(
                    task_id="task-move-1",
                    request_id="req-1",
                    input_mode="text",
                    command_text="move file",
                    final_state="SUCCEEDED",
                )
            )
            action_id = ledger.insert_action(
                ActionRecord(
                    task_id="task-move-1",
                    step_index=1,
                    tool="move_file",
                    args_raw={"source": str(src), "destination": str(dst)},
                    risk="MEDIUM",
                    verified=True,
                )
            )
            ledger.insert_undo_record(
                UndoRecord(
                    action_row_id=action_id,
                    undo_data={"action": "move_file", "source": str(src), "destination": str(dst)},
                )
            )

            # 3. Verify undo record is available
            latest = query.get_latest_available_undo_record()
            assert latest is not None
            assert latest["action_id"] == action_id

            # 4. Execute undo_last in a brand-new task context
            class NewTaskContext:
                task_id = "task-undo-invocation"
                undo_stack = []

            ctx = NewTaskContext()
            ctx.db = db
            undo_res = execute_undo_last({}, task_context=ctx)
            assert undo_res.ok is True
            assert src.exists()
            assert not dst.exists()

            # 5. Verify undo record is now consumed in SQLite
            assert query.get_latest_available_undo_record() is None

            # 6. Subsequent undo_last returns no available records
            second_undo = execute_undo_last({}, task_context=ctx)
            assert second_undo.ok is False
            assert "no undo records available" in second_undo.error.lower()
        finally:
            db.close()
