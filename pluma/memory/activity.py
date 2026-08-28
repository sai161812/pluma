"""pluma.memory.activity — Activity Ledger write and query interface.

Spec §16: "A local Activity Ledger is mandatory. It records necessary task
detail and can be viewed inside PLUMA through an Activity view."

This module provides:
  - TaskRecord / ActionRecord / UndoRecord dataclasses for structured writes.
  - ActivityLedger: the single write path for all task/action data.
  - ActivityQuery: the read path used by the Activity view and the verifier.

All text written here comes from deterministic executor templates.
Spec §16.4: "User-visible Activity messages must be generated from deterministic
templates owned by the executor, not by the LLM."

No OS-automation or ML code in this module.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pluma.memory.db import DbConnection
from pluma.memory.redaction import redact_sensitive_data, redact_string, sanitise_args_for_ledger

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Write-path record types
# ---------------------------------------------------------------------------

@dataclass
class TaskRecord:
    """Data needed to insert a row into the tasks table."""
    task_id: str
    request_id: str
    input_mode: str               # 'text' or 'voice'
    command_text: str
    created_at: str = field(default_factory=_now_iso)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    final_state: Optional[str] = None
    route: Optional[str] = None
    active_process: Optional[str] = None
    active_window: Optional[str] = None
    stop_reason: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class ActionRecord:
    """Data needed to insert a row into the actions table."""
    task_id: str
    step_index: int
    tool: str
    args_raw: Dict[str, Any]      # Redacted by ActivityLedger before storage.
    risk: str
    started_at: str = field(default_factory=_now_iso)
    adapter: Optional[str] = None
    approval_state: Optional[str] = None
    ended_at: Optional[str] = None
    duration_ms: Optional[float] = None
    result_data: Optional[Dict[str, Any]] = None
    verified: bool = False
    verification_detail: Optional[Dict[str, Any]] = None
    error_detail: Optional[Dict[str, Any]] = None
    # Returned after insert so the caller can attach an UndoRecord.
    _row_id: Optional[int] = field(default=None, init=False, repr=False)


@dataclass
class UndoRecord:
    """Data needed to insert a row into the undo_records table."""
    action_row_id: int            # FK → actions.id
    undo_data: Dict[str, Any]     # Tool-specific pre-state.
    available: bool = True


@dataclass
class ResourceRecord:
    """Data needed to insert a row into the resources table."""
    id: str
    task_id: str
    resource_type: str            # 'temp_dir', 'subprocess', 'browser_tab', etc.
    ownership: str                # 'PREEXISTING' or 'PLUMA_CREATED'
    external_id: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)
    released_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScreenEventRecord:
    """Data needed to insert a row into the screen_events table."""
    task_id: str
    snapshot_id: str
    source: str                   # 'UIA' or 'OCR'
    target_label: Optional[str] = None
    control_type: Optional[str] = None
    bounds: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    active_window_signature: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)


# ---------------------------------------------------------------------------
# ActivityLedger — write path
# ---------------------------------------------------------------------------

class ActivityLedger:
    """Single write path to the PLUMA Activity Ledger.

    All arguments are redacted before they touch the database.
    Factual message templates are set by the executor, not by this class.
    """

    def __init__(self, db: DbConnection) -> None:
        self._db = db

    # -- Task lifecycle --

    def insert_task(self, record: TaskRecord) -> None:
        """Insert a new task row. Called when the TaskCapsule is created."""
        redacted_cmd = redact_string(record.command_text) if record.command_text else record.command_text
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO tasks
              (task_id, request_id, input_mode, command_text,
               created_at, started_at, completed_at, final_state,
               route, active_process, active_window, stop_reason, error_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id, record.request_id, record.input_mode.lower(),
                redacted_cmd, record.created_at, record.started_at,
                record.completed_at, record.final_state, record.route,
                record.active_process, record.active_window,
                record.stop_reason, record.error_code,
            ),
        )

    def update_task(self, task_id: str, **fields: Any) -> None:
        """Update one or more fields on an existing task row.

        Only the following fields may be updated:
          started_at, completed_at, final_state, route,
          active_process, active_window, stop_reason, error_code
        """
        allowed = {
            "started_at", "completed_at", "final_state", "route",
            "active_process", "active_window", "stop_reason", "error_code",
        }
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"update_task: disallowed fields {bad!r}")
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [task_id]
        self._db.execute_write(
            f"UPDATE tasks SET {set_clause} WHERE task_id = ?",
            values,
        )

    # -- Action recording --

    def insert_action(self, record: ActionRecord) -> int:
        """Insert an action row and return its integer row id."""
        sanitised_args = sanitise_args_for_ledger(record.tool, record.args_raw)
        sanitised_result = redact_sensitive_data(record.result_data) if record.result_data else None
        sanitised_verify = redact_sensitive_data(record.verification_detail) if record.verification_detail else None
        sanitised_error = redact_sensitive_data(record.error_detail) if record.error_detail else None

        result_json = json.dumps(sanitised_result) if sanitised_result is not None else None
        verify_json = json.dumps(sanitised_verify) if sanitised_verify is not None else None
        error_json = json.dumps(sanitised_error) if sanitised_error is not None else None

        row_id = self._db.execute_write(
            """
            INSERT INTO actions
              (task_id, step_index, tool, adapter, args_json_sanitized,
               risk, approval_state, started_at, ended_at, duration_ms,
               result_json, verified, verification_json, error_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id, record.step_index, record.tool, record.adapter,
                sanitised_args, record.risk, record.approval_state,
                record.started_at, record.ended_at, record.duration_ms,
                result_json, int(record.verified), verify_json, error_json,
            ),
            wait=True,
        )
        record._row_id = row_id
        return row_id  # type: ignore[return-value]

    # -- Undo records --

    def insert_undo_record(self, record: UndoRecord) -> None:
        """Insert an undo record linked to an action row."""
        sanitised_undo = redact_sensitive_data(record.undo_data) if record.undo_data else None
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO undo_records
              (action_id, undo_json, available)
            VALUES (?, ?, ?)
            """,
            (
                record.action_row_id,
                json.dumps(sanitised_undo) if sanitised_undo is not None else None,
                int(record.available),
            ),
        )

    # Alias for convenient cross-caller use
    insert_undo = insert_undo_record

    def mark_rollback_result(
        self,
        action_row_id: int,
        ok: bool,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update the undo_records row after a rollback attempt."""
        self._db.execute_write(
            """
            UPDATE undo_records
            SET rollback_attempted = 1, rollback_ok = ?, rollback_result_json = ?
            WHERE action_id = ?
            """,
            (int(ok), json.dumps(result) if result else None, action_row_id),
        )

    def mark_undo_consumed(self, action_row_id: int) -> None:
        """Mark an undo record as consumed (available = 0)."""
        self._db.execute_write(
            "UPDATE undo_records SET available = 0 WHERE action_id = ?",
            (action_row_id,),
        )

    def consume_undo_and_mark_result_atomic(
        self,
        action_row_id: int,
        ok: bool,
        result: Dict[str, Any],
    ) -> None:
        """Atomically mark rollback result and consume undo record in one SQLite transaction."""
        stmts = [
            (
                """
                UPDATE undo_records
                SET rollback_attempted = 1, rollback_ok = ?, rollback_result_json = ?
                WHERE action_id = ?
                """,
                (int(ok), json.dumps(result) if result else None, action_row_id),
            ),
        ]
        if ok:
            stmts.append((
                "UPDATE undo_records SET available = 0 WHERE action_id = ?",
                (action_row_id,),
            ))
        self._db.execute_transaction(stmts, wait=True)


    # -- Resources --

    def insert_resource(self, record: ResourceRecord) -> None:
        """Insert a claimed or created resource row."""
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO resources
              (id, task_id, resource_type, ownership, external_id, created_at, released_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id, record.task_id, record.resource_type, record.ownership,
                record.external_id, record.created_at, record.released_at,
                json.dumps(record.metadata) if record.metadata else None,
            ),
        )

    def release_resource(self, resource_id: str, released_at: Optional[str] = None) -> None:
        """Mark a resource as released."""
        rel_time = released_at or _now_iso()
        self._db.execute_write(
            "UPDATE resources SET released_at = ? WHERE id = ?",
            (rel_time, resource_id),
        )

    # -- Screen events --

    def insert_screen_event(self, record: ScreenEventRecord) -> int:
        """Insert a screen event metadata record (no raw screenshots)."""
        row_id = self._db.execute_write(
            """
            INSERT INTO screen_events
              (task_id, snapshot_id, source, target_label, control_type,
               bounds_json, confidence, active_window_signature, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id, record.snapshot_id, record.source,
                record.target_label, record.control_type,
                json.dumps(record.bounds) if record.bounds else None,
                record.confidence, record.active_window_signature,
                record.created_at,
            ),
            wait=True,
        )
        return row_id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# ActivityQuery — read path
# ---------------------------------------------------------------------------

class ActivityQuery:
    """Read path for the Activity Ledger. Used by the Activity view and tests."""

    def __init__(self, db: DbConnection) -> None:
        self._db = db

    def recent_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent *limit* task rows, newest first."""
        rows = self._db.execute_read(
            "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    # Alias for compatibility with external caller expectations
    get_recent_tasks = recent_tasks

    def task_by_id(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return one task row or None."""
        row = self._db.execute_read_one(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        )
        return dict(row) if row else None

    # Alias for compatibility
    get_task = task_by_id

    def actions_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Return all action rows for *task_id*, ordered by step_index."""
        rows = self._db.execute_read(
            "SELECT * FROM actions WHERE task_id = ? ORDER BY step_index",
            (task_id,),
        )
        return [dict(r) for r in rows]

    # Alias for compatibility with external caller expectations
    get_task_actions = actions_for_task

    def undo_record_for_action(self, action_row_id: int) -> Optional[Dict[str, Any]]:
        """Return the undo record for an action row, or None."""
        row = self._db.execute_read_one(
            "SELECT * FROM undo_records WHERE action_id = ?", (action_row_id,)
        )
        return dict(row) if row else None

    def available_undo_records_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Return all available undo records for a task, in reverse step order.

        Used by the rollback engine to determine what can be reversed.
        """
        rows = self._db.execute_read(
            """
            SELECT ur.*, a.step_index, a.tool
            FROM undo_records ur
            JOIN actions a ON a.id = ur.action_id
            WHERE a.task_id = ? AND ur.available = 1
            ORDER BY a.step_index DESC
            """,
            (task_id,),
        )
        return [dict(r) for r in rows]

    def get_latest_available_undo_record(self) -> Optional[Dict[str, Any]]:
        """Return the most recent available undo record across all tasks, newest first."""
        row = self._db.execute_read_one(
            """
            SELECT ur.*, a.task_id, a.step_index, a.tool
            FROM undo_records ur
            JOIN actions a ON a.id = ur.action_id
            WHERE ur.available = 1
            ORDER BY ur.action_id DESC
            LIMIT 1
            """
        )
        return dict(row) if row else None

    def resources_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Return all tracked resources for a task."""
        rows = self._db.execute_read(
            "SELECT * FROM resources WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [dict(r) for r in rows]

    def screen_events_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Return all screen events for a task."""
        rows = self._db.execute_read(
            "SELECT * FROM screen_events WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [dict(r) for r in rows]
