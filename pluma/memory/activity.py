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
from pluma.memory.redaction import (
    redact_command_text,
    redact_sensitive_data,
    redact_string,
    sanitise_args_for_ledger,
)

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
    original_transcript: Optional[str] = None
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
        redacted_cmd = redact_command_text(record.command_text) if record.command_text else record.command_text
        redacted_transcript = (redact_command_text(record.original_transcript)
                               if record.original_transcript else None)
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO tasks
              (task_id, request_id, input_mode, command_text, original_transcript,
               created_at, started_at, completed_at, final_state,
               route, active_process, active_window, stop_reason, error_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.task_id, record.request_id, record.input_mode.lower(),
                redacted_cmd, redacted_transcript, record.created_at, record.started_at,
                record.completed_at, record.final_state, record.route,
                redact_string(record.active_process) if record.active_process else record.active_process,
                redact_string(record.active_window) if record.active_window else record.active_window,
                record.stop_reason, record.error_code,
            ),
        )

    def update_task(self, task_id: str, *, _timeout_s: Optional[float] = None, **fields: Any) -> None:
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
        safe_fields = dict(fields)
        for name in ("active_process", "active_window"):
            if safe_fields.get(name):
                safe_fields[name] = redact_string(safe_fields[name])
        set_clause = ", ".join(f"{k} = ?" for k in safe_fields)
        values = list(safe_fields.values()) + [task_id]
        self._db.execute_write(
            f"UPDATE tasks SET {set_clause} WHERE task_id = ?",
            values,
            timeout_s=_timeout_s,
        )

    # -- Action recording --

    def insert_action(self, record: ActionRecord, *, _timeout_s: Optional[float] = None) -> int:
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
            timeout_s=_timeout_s,
        )
        record._row_id = row_id
        return row_id  # type: ignore[return-value]

    # -- Undo records --

    def insert_undo_record(self, record: UndoRecord, *, _timeout_s: Optional[float] = None) -> None:
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
            timeout_s=_timeout_s,
        )

    def prepare_mutation(self, record: ActionRecord, pending: Dict[str, Any]) -> int:
        """Acknowledge and read back durable pre-state before executor admission.

        If either write fails, the caller must not dispatch. A crash between
        these writes cannot leave a mutation because dispatch follows both.
        """
        row_id = self.insert_action(record, _timeout_s=2.0)
        if type(row_id) is not int or row_id <= 0:
            raise RuntimeError("Mutation action identity was not verified.")
        # Publish the same complete identity that the parent will retain.
        # Adding this only at finalization changed undo_json during STOP's
        # read/claim and falsely refused an otherwise recoverable inverse.
        pending['action_row_id'] = row_id
        available = not pending.get("non_undoable", False)
        self.insert_undo_record(UndoRecord(row_id, pending, available=available), _timeout_s=2.0)
        row = ActivityQuery(self._db).undo_record_for_action(row_id)
        expected = redact_sensitive_data(pending)
        if not row or row['available'] != int(available) or json.loads(row['undo_json']) != expected:
            raise RuntimeError("Mutation pre-state was not durably verified.")
        return row_id

    def finish_mutation(self, row_id: int, record: ActionRecord,
                        undo_data: Dict[str, Any], *, not_executed: bool = False) -> bool:
        """Atomically finalize the original action and its inverse evidence.

        Return whether undo remains available (a concurrent verified rollback
        may have consumed it). Never create a second action for one attempt.
        """
        encode = lambda value: json.dumps(redact_sensitive_data(value)) if value is not None else None
        statements = [(
            """UPDATE actions SET adapter=?, ended_at=?, duration_ms=?, result_json=?,
                   verified=?, verification_json=?, error_json=? WHERE id=? AND task_id=?""",
            (record.adapter, record.ended_at or _now_iso(), record.duration_ms,
             encode(record.result_data), int(record.verified), encode(record.verification_detail),
             encode(record.error_detail), row_id, record.task_id)),
            ("UPDATE undo_records SET undo_json=? WHERE action_id=?", (encode(undo_data), row_id))]
        if not_executed:
            statements.append(("UPDATE undo_records SET available=0 WHERE action_id=?", (row_id,)))
        self._db.execute_transaction(statements, timeout_s=2.0)
        row = ActivityQuery(self._db).undo_record_for_action(row_id)
        action = self._db.execute_read_one("SELECT verified FROM actions WHERE id=? AND task_id=?",
                                           (row_id, record.task_id))
        if (not row or not action or action['verified'] != int(record.verified)
                or json.loads(row['undo_json']) != redact_sensitive_data(undo_data)
                or (not_executed and row['available'] != 0)):
            raise RuntimeError("Mutation completion was not durably verified.")
        return bool(row['available'])

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
        claim_id: Optional[str] = None,
    ) -> None:
        """Atomically mark rollback result and consume undo record in one SQLite transaction."""
        if claim_id is not None:
            claim = self._db.execute_read_one("SELECT operation_id FROM undo_claims WHERE action_id=?", (action_row_id,))
            if claim is None or claim["operation_id"] != claim_id:
                raise ValueError("Undo claim is not owned by this operation.")
        stmts = [
            (
                """
                UPDATE undo_records
                SET rollback_attempted = 1, rollback_ok = ?, rollback_result_json = ?
                WHERE action_id = ?
                """,
                (int(ok), json.dumps(redact_sensitive_data(result)) if result else None, action_row_id),
            ),
        ]
        if ok:
            stmts.append((
                "UPDATE undo_records SET available = 0 WHERE action_id = ?",
                (action_row_id,),
            ))
        if claim_id is not None:
            stmts.append(("UPDATE undo_claims SET state=? WHERE action_id=? AND operation_id=?",
                ("verified" if ok else "unverified", action_row_id, claim_id)))
        self._db.execute_transaction(stmts, wait=True, timeout_s=2.0)
        observed = self._db.execute_read_one("SELECT available, rollback_attempted, rollback_ok FROM undo_records WHERE action_id=?", (action_row_id,))
        if observed is None or observed['rollback_attempted'] != 1 or observed['rollback_ok'] != int(ok) or (ok and observed['available'] != 0):
            raise ValueError("Undo consumption could not be read back.")
        if claim_id is not None:
            claim = self._db.execute_read_one("SELECT state FROM undo_claims WHERE action_id=? AND operation_id=?", (action_row_id, claim_id))
            if claim is None or claim['state'] != ('verified' if ok else 'unverified'):
                raise ValueError("Undo claim outcome could not be read back.")

    def claim_undo(self, action_row_id: int, task_id: str, undo_json: str) -> Optional[str]:
        import uuid
        operation = str(uuid.uuid4())
        self._db.execute_transaction([("""INSERT OR IGNORE INTO undo_claims
            (action_id, operation_id, task_id, state, created_at)
            SELECT action_id, ?, ?, 'claimed', ? FROM undo_records
            WHERE action_id=? AND available=1 AND undo_json=?""",
            (operation, task_id, _now_iso(), action_row_id, undo_json))], wait=True, timeout_s=2.0)
        row = self._db.execute_read_one("SELECT operation_id FROM undo_claims WHERE action_id=?", (action_row_id,))
        if row is None:
            # A pending journal may change between read and claim. Record the
            # refused rollback attempt without modifying its newer pre-state
            # or a claim held by another executor.
            self._db.execute_transaction([("""UPDATE undo_records SET rollback_attempted=1,
                rollback_ok=0, rollback_result_json=? WHERE action_id=?
                AND NOT EXISTS (SELECT 1 FROM undo_claims WHERE action_id=?)""",
                (json.dumps({"error": "UNDO_CLAIM_UNVERIFIED"}), action_row_id, action_row_id))],
                wait=True, timeout_s=2.0)
        return operation if row is not None and row["operation_id"] == operation else None


    # -- Resources --

    def record_cleanup(self, task_id: str, entries: List[Dict[str, Any]]) -> None:
        """Persist a redacted cleanup snapshot and verify its SQLite readback.

        The independent journal also accepts unpublished preparations. Mirror
        into resources only when task history exists, in the same transaction.
        """
        self._write_cleanup(task_id, entries)

    def finalize_task(self, task_id: str, *, final_state: str, completed_at: str,
                      stop_reason: Optional[str], error_code: Optional[str],
                      entries: List[Dict[str, Any]]) -> None:
        """Atomically store the supervisor's terminal outcome and evidence.

        The readback includes history, independent journal and resource mirror.
        A missing task row is an error, never a fabricated successful history.
        """
        from pluma.core.task_supervisor import TaskState, _TERMINAL_STATES
        if TaskState(final_state) not in _TERMINAL_STATES:
            raise ValueError("Terminal ledger state required.")
        fields = (final_state, completed_at, stop_reason, error_code)
        self._write_cleanup(task_id, entries, terminal=fields)

    def finalize_pre_execution(self, task_id: str, *, final_state: str, completed_at: str,
                               stop_reason: Optional[str], error_code: Optional[str],
                               entries: List[Dict[str, Any]]) -> None:
        """Journal a capture cancelled before a request/transcript exists."""
        from pluma.core.task_supervisor import TaskState, _TERMINAL_STATES
        if TaskState(final_state) not in _TERMINAL_STATES:
            raise ValueError("Terminal pre-execution state required.")
        self._write_cleanup(task_id, entries, pre_execution={"final_state": final_state,
            "completed_at": completed_at, "stop_reason": stop_reason, "error_code": error_code})

    def _write_cleanup(self, task_id: str, entries: List[Dict[str, Any]], *,
                       terminal: Optional[tuple] = None,
                       pre_execution: Optional[Dict[str, Any]] = None) -> None:
        from pluma.core.cleanup import CleanupEvidence, latest_unresolved
        checks = [CleanupEvidence.model_validate(item) for item in entries]
        complete = not latest_unresolved(checks)
        metadata = redact_sensitive_data({"version": 1, "complete": complete,
                                           "entries": [item.model_dump() for item in checks]})
        if pre_execution is not None:
            metadata["pre_execution_outcome"] = redact_sensitive_data(pre_execution)
        encoded = json.dumps(metadata)
        record_id = "cleanup:" + task_id
        now = _now_iso()
        released = now if complete else None
        statements = [
            ("""INSERT OR REPLACE INTO cleanup_reports
               (task_id, recorded_at, released_at, metadata_json) VALUES (?, ?, ?, ?)""",
             (task_id, now, released, encoded)),
            ("""INSERT OR REPLACE INTO resources
               (id, task_id, resource_type, ownership, created_at, released_at, metadata_json)
               SELECT ?, task_id, 'cleanup_report', 'PLUMA_CREATED', ?, ?, ? FROM tasks WHERE task_id = ?""",
             (record_id, now, released, encoded, task_id)),
        ]
        if terminal is not None:
            statements.append(("""UPDATE tasks SET final_state = ?, completed_at = ?,
                                stop_reason = ?, error_code = ? WHERE task_id = ?""",
                               (*terminal, task_id)))
        self._db.execute_transaction(statements, timeout_s=2.0)
        row = self._db.execute_read_one("SELECT metadata_json FROM cleanup_reports WHERE task_id = ?", (task_id,))
        if row is None or json.loads(row[0]) != metadata:
            raise RuntimeError("Cleanup ledger readback failed.")
        if terminal is not None:
            row = self._db.execute_read_one("""SELECT t.final_state, t.completed_at, t.stop_reason,
                t.error_code, r.metadata_json FROM tasks t JOIN resources r ON r.task_id = t.task_id
                WHERE t.task_id = ? AND r.id = ?""", (task_id, record_id))
            if row is None or tuple(row[:4]) != terminal or json.loads(row[4]) != metadata:
                raise RuntimeError("Terminal ledger readback failed.")

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

    def task_by_request_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Return the newest task row for a request ID, for IPC replay refusal."""
        row = self._db.execute_read_one(
            "SELECT * FROM tasks WHERE request_id = ? ORDER BY created_at DESC LIMIT 1",
            (request_id,),
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

    def cleanup_report_for_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Read cleanup evidence even if task preparation never published."""
        row = self._db.execute_read_one("SELECT * FROM cleanup_reports WHERE task_id = ?", (task_id,))
        return dict(row) if row else None

    def screen_events_for_task(self, task_id: str) -> List[Dict[str, Any]]:
        """Return all screen events for a task."""
        rows = self._db.execute_read(
            "SELECT * FROM screen_events WHERE task_id = ? ORDER BY created_at",
            (task_id,),
        )
        return [dict(r) for r in rows]
