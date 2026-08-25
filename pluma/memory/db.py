"""pluma.memory.db — SQLite connection, WAL mode, and queued writer.

Spec §20.1: "Use a single queued writer or short transactions. SQLite WAL
mode is reasonable if multiple readers coexist with one controlled writer."

Design:
  - One DbConnection per database file.
  - WAL journal mode is set on first open.
  - A background writer thread serialises all mutations via a queue.
    Reads can happen directly on a separate read connection in WAL mode.
  - Migrations are run from the migrations/ directory in version order.
  - In tests, pass ":memory:" as db_path; migrations still run.

No ML, OS-automation, or adapter code in this module.
"""

from __future__ import annotations

import logging
import os
import queue
import sqlite3
import threading
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Path to the migrations directory relative to this file.
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _run_migrations(conn: sqlite3.Connection) -> None:
    """Apply all pending SQL migration files in version order.

    Migration files are named NNN_description.sql (e.g. 0001_baseline.sql).
    Only files whose version number has not yet been applied are run.
    This function is idempotent.
    """
    # Create a migrations-tracking table if it doesn't exist.
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS _schema_migrations (
            version TEXT PRIMARY KEY NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()

    applied: set[str] = {
        row[0]
        for row in conn.execute("SELECT version FROM _schema_migrations").fetchall()
    }

    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    for mf in migration_files:
        version = mf.stem  # e.g. "0001_baseline"
        if version in applied:
            continue
        sql = mf.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO _schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
                (version,),
            )
            conn.commit()
            logger.info("Applied migration: %s", version)
        except sqlite3.Error as exc:
            logger.error("Migration %s failed: %s", version, exc)
            raise


class _WriteTask:
    """One unit of work submitted to the background writer thread."""

    __slots__ = ("sql", "params", "result_queue")

    def __init__(
        self,
        sql: str,
        params: Sequence[Any],
        result_queue: Optional[queue.SimpleQueue],
    ) -> None:
        self.sql = sql
        self.params = params
        self.result_queue = result_queue


_SENTINEL = object()  # Signals the writer thread to exit.


class DbConnection:
    """Manages one SQLite database file with WAL mode and a queued writer.

    Usage:
        db = DbConnection("path/to/pluma.db")
        db.open()
        db.execute_write("INSERT INTO preferences ...", ("key", "val"))
        rows = db.execute_read("SELECT * FROM preferences")
        db.close()

    Or as a context manager:
        with DbConnection("path/to/pluma.db") as db:
            ...
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._write_conn: Optional[sqlite3.Connection] = None
        self._read_conn: Optional[sqlite3.Connection] = None
        self._write_queue: queue.Queue = queue.Queue()
        self._writer_thread: Optional[threading.Thread] = None
        self._open = False

    @property
    def is_open(self) -> bool:
        """True if the database connection is currently open."""
        return self._open

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the database, set WAL mode, run migrations, start writer."""
        if self._open:
            return

        if self._db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self._db_path)), exist_ok=True)

        # Read connection for file-based DBs — WAL allows concurrent reads from a
        # separate connection. For :memory: the writer thread will set self._read_conn
        # to the write connection (a second connect(":memory:") is a different empty DB).
        if self._db_path != ":memory:":
            self._read_conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level=None,
            )
            self._read_conn.row_factory = sqlite3.Row
            self._read_conn.execute("PRAGMA journal_mode=WAL")
            self._read_conn.execute("PRAGMA foreign_keys=ON")
        else:
            self._read_conn = None  # Will be set by writer thread.

        # The write connection is created on the writer thread (SQLite thread affinity).
        # We use a ready-event to synchronise before returning from open().
        self._writer_ready = threading.Event()
        self._writer_init_error: Optional[Exception] = None

        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name="pluma-db-writer",
            daemon=True,
        )
        self._writer_thread.start()

        # Wait for the writer thread to finish initialising before returning.
        self._writer_ready.wait(timeout=10)
        if self._writer_init_error is not None:
            raise self._writer_init_error

        self._open = True
        logger.debug("DbConnection opened: %s", self._db_path)


    def close(self) -> None:
        """Flush all pending writes and close both connections."""
        if not self._open:
            return
        # Signal the writer to stop after draining the queue.
        # The writer thread closes the write connection itself when it exits.
        self._write_queue.put(_SENTINEL)
        if self._writer_thread:
            self._writer_thread.join(timeout=10)
        # Read connection: only close separately if it's not the write connection
        # (for :memory: DBs, read_conn IS write_conn after writer thread sets it).
        if self._read_conn is not None and self._read_conn is not self._write_conn:
            self._read_conn.close()
        self._open = False
        logger.debug("DbConnection closed: %s", self._db_path)

    def __enter__(self) -> "DbConnection":
        self.open()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Write path (queued, serialised)
    # ------------------------------------------------------------------

    def execute_write(
        self,
        sql: str,
        params: Sequence[Any] = (),
        *,
        wait: bool = True,
    ) -> Optional[int]:
        """Enqueue a write statement.

        If *wait* is True, blocks until the write is committed and returns
        the lastrowid. If *wait* is False, returns None immediately.
        """
        if not self._open:
            raise RuntimeError("DbConnection is not open.")
        result_q: Optional[queue.SimpleQueue] = queue.SimpleQueue() if wait else None
        self._write_queue.put(_WriteTask(sql, params, result_q))
        if wait and result_q is not None:
            outcome = result_q.get()
            if isinstance(outcome, Exception):
                raise outcome
            return outcome  # lastrowid
        return None

    def execute_write_many(
        self,
        sql: str,
        params_list: List[Sequence[Any]],
        *,
        wait: bool = True,
    ) -> None:
        """Execute one statement for each entry in *params_list* in one transaction."""
        if not self._open:
            raise RuntimeError("DbConnection is not open.")
        # Batch into a single write task by wrapping in a callable.
        result_q: Optional[queue.SimpleQueue] = queue.SimpleQueue() if wait else None
        # Use a special sentinel with a callable payload.
        task = _WriteManyTask(sql, params_list, result_q)
        self._write_queue.put(task)
        if wait and result_q is not None:
            outcome = result_q.get()
            if isinstance(outcome, Exception):
                raise outcome

    def _writer_loop(self) -> None:
        """Background thread: create write connection, run migrations, drain queue."""
        try:
            # Create the write connection HERE — on the writer thread.
            # check_same_thread=False is safe because all writes are serialised
            # through the queue (single writer). We set it False so the read
            # path can share the connection for :memory: databases where a
            # second sqlite3.connect(":memory:") would open a different DB.
            conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,
                isolation_level=None,      # autocommit; we manage transactions.
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _run_migrations(conn)
            self._write_conn = conn

            # For :memory: databases, the read connection must be the SAME
            # object (a second connect(":memory:") is a different, empty DB).
            if self._db_path == ":memory:":
                # Reuse write conn for reads; safe under WAL-style isolation.
                self._read_conn = conn
                self._read_conn.row_factory = sqlite3.Row

        except Exception as exc:
            self._writer_init_error = exc
            self._writer_ready.set()
            return

        # Signal the calling thread that initialisation succeeded.
        self._writer_ready.set()

        while True:
            item = self._write_queue.get()
            if item is _SENTINEL:
                if self._db_path != ":memory:":
                    conn.close()
                break
            try:
                conn.execute("BEGIN")
                if isinstance(item, _WriteManyTask):
                    conn.executemany(item.sql, item.params_list)
                    conn.execute("COMMIT")
                    if item.result_queue is not None:
                        item.result_queue.put(None)
                else:
                    cursor = conn.execute(item.sql, item.params)
                    conn.execute("COMMIT")
                    if item.result_queue is not None:
                        item.result_queue.put(cursor.lastrowid)
            except Exception as exc:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                sql_str = getattr(item, "sql", "<unknown>")
                logger.error("DB write failed: %s - %s", exc, sql_str)
                if isinstance(item, (_WriteTask, _WriteManyTask)):
                    if item.result_queue is not None:
                        item.result_queue.put(exc)


    # ------------------------------------------------------------------
    # Read path (direct, thread-safe via WAL)
    # ------------------------------------------------------------------

    def execute_read(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> List[sqlite3.Row]:
        """Execute a SELECT and return all rows."""
        if not self._open:
            raise RuntimeError("DbConnection is not open.")
        assert self._read_conn is not None
        return self._read_conn.execute(sql, params).fetchall()

    def execute_read_one(
        self,
        sql: str,
        params: Sequence[Any] = (),
    ) -> Optional[sqlite3.Row]:
        """Execute a SELECT and return the first row, or None."""
        if not self._open:
            raise RuntimeError("DbConnection is not open.")
        assert self._read_conn is not None
        return self._read_conn.execute(sql, params).fetchone()


class _WriteManyTask:
    """Batch write task submitted to the background writer thread."""

    __slots__ = ("sql", "params_list", "result_queue")

    def __init__(
        self,
        sql: str,
        params_list: List[Sequence[Any]],
        result_queue: Optional[queue.SimpleQueue],
    ) -> None:
        self.sql = sql
        self.params_list = params_list
        self.result_queue = result_queue
