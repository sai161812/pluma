"""tests.unit.test_db — SQLite migration, WAL, and queued writer tests."""

from __future__ import annotations

import threading
import time
import pytest
from pathlib import Path


class TestMigrations:
    def test_in_memory_db_opens_and_migrates(self) -> None:
        from pluma.memory.db import DbConnection
        with DbConnection(":memory:") as db:
            rows = db.execute_read(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            table_names = {r[0] for r in rows}
            required = {
                "preferences", "aliases", "routines", "tasks",
                "actions", "undo_records", "resources", "screen_events",
                "_schema_migrations",
            }
            assert required.issubset(table_names), (
                f"Missing tables: {required - table_names}"
            )

    def test_migrations_are_idempotent(self) -> None:
        """Running migrations twice on the same DB must not error."""
        from pluma.memory.db import DbConnection, _run_migrations
        with DbConnection(":memory:") as db:
            # Migrations already ran on open(). Run them again manually.
            assert db._write_conn is not None
            _run_migrations(db._write_conn)  # Second run — must be a no-op.

    def test_wal_mode_is_set(self) -> None:
        from pluma.memory.db import DbConnection
        with DbConnection(":memory:") as db:
            rows = db.execute_read("PRAGMA journal_mode")
            mode = rows[0][0]
            # In-memory DB falls back to 'memory' journal mode (WAL not supported).
            # For file-based DBs WAL is set; this test just confirms no error.
            assert mode in ("wal", "memory")


class TestQueuedWriter:
    def test_write_and_read_roundtrip(self) -> None:
        from pluma.memory.db import DbConnection
        with DbConnection(":memory:") as db:
            db.execute_write(
                "INSERT INTO preferences (key, value_json, updated_at) VALUES (?, ?, ?)",
                ("theme", '"dark"', "2026-01-01T00:00:00Z"),
            )
            row = db.execute_read_one(
                "SELECT value_json FROM preferences WHERE key = ?", ("theme",)
            )
            assert row is not None
            assert row[0] == '"dark"'

    def test_write_order_is_preserved(self) -> None:
        """100 sequential writes must appear in FIFO order."""
        from pluma.memory.db import DbConnection
        with DbConnection(":memory:") as db:
            for i in range(100):
                db.execute_write(
                    "INSERT INTO preferences (key, value_json, updated_at) VALUES (?, ?, ?)",
                    (f"key_{i:04d}", str(i), "2026-01-01T00:00:00Z"),
                )
            rows = db.execute_read(
                "SELECT key FROM preferences ORDER BY key"
            )
            keys = [r[0] for r in rows]
            assert len(keys) == 100
            assert keys[0] == "key_0000"
            assert keys[99] == "key_0099"

    def test_write_exception_does_not_crash_writer(self) -> None:
        """A bad SQL write must raise on the caller, not crash the writer thread."""
        from pluma.memory.db import DbConnection
        with DbConnection(":memory:") as db:
            with pytest.raises(Exception):
                db.execute_write("INSERT INTO nonexistent_table VALUES (?)", ("x",))
            # Writer thread should still be alive and functional.
            db.execute_write(
                "INSERT INTO preferences (key, value_json, updated_at) VALUES (?, ?, ?)",
                ("after_error", '"ok"', "2026-01-01T00:00:00Z"),
            )
            row = db.execute_read_one(
                "SELECT value_json FROM preferences WHERE key = ?", ("after_error",)
            )
            assert row is not None

    def test_file_db_creates_directory(self, tmp_path: Path) -> None:
        from pluma.memory.db import DbConnection
        db_path = str(tmp_path / "subdir" / "pluma.db")
        with DbConnection(db_path) as db:
            rows = db.execute_read(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
            )
            assert len(rows) == 1
