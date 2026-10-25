"""Bounded, read-only snapshots of the executor-selected Activity database."""
from pathlib import Path
from contextlib import closing
import sqlite3

from pluma.memory.redaction import redact_string


def recent_activity(path: str, limit: int) -> list[dict]:
    if not path or path == ":memory:":
        raise ValueError("An executor-owned persistent ledger is required.")
    # mode=ro never creates storage, migrates schema or starts a writer thread.
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=1)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(ACTIVITY_SQL, (limit,)).fetchall()
    return _records(rows)


def recent_activity_from_query(query, limit):
    return _records(query._db.execute_read(ACTIVITY_SQL, (limit,)))


def _records(rows):
    return [dict(row, command=redact_string(row["command"] or ""),
                 command_truncated=bool(row["command_truncated"])) for row in rows]


ACTIVITY_SQL = """SELECT t.task_id,
            substr(t.command_text, 1, 4096) AS command,
            length(t.command_text) > 4096 AS command_truncated,
            t.final_state AS state, t.created_at, t.input_mode, t.route,
            (SELECT count(*) FROM actions a WHERE a.task_id=t.task_id) AS action_count
            FROM tasks t ORDER BY t.created_at DESC, t.task_id DESC LIMIT ?"""
