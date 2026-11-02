"""Bounded saved-task browsing. No raw action, undo, transcript or resource data."""
import re
from datetime import datetime

from pluma.memory.redaction import redact_command_text, redact_sensitive_data

MAX_COMMAND_BYTES = 8192


class HistoryCursorUnavailable(ValueError):
    pass


def _command(value):
    if not isinstance(value, str):
        return None
    # SQL withholds oversized input before invoking Python. Redact the whole
    # available value before presentation or searching; never truncate first.
    text = redact_command_text(value)
    return text if len(text.encode("utf-8")) <= MAX_COMMAND_BYTES else None


def _identifier(value):
    if value is None:
        return None
    if (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value)
            or redact_sensitive_data(value) != value):
        return None
    return value


def read_page(db, request):
    from pluma.core.ipc_contracts import SavedHistoryTaskV1, HistoryPageV1
    search = request.search.casefold()
    with db.read_snapshot() as connection:
        connection.create_function("pluma_history_command", 1, _command, deterministic=True)
        connection.create_function("pluma_history_match", 5,
            lambda command, task, state, route, mode: int(search in "\n".join(
                x for x in (command, task, state, route, mode) if isinstance(x, str)).casefold()),
            deterministic=True)
        cursor_time = None
        if request.before_task_id is not None:
            cursor = connection.execute("SELECT CASE WHEN length(CAST(created_at AS BLOB)) <= 64 THEN created_at END AS created_at FROM tasks WHERE task_id=?", (request.before_task_id,)).fetchone()
            if cursor is None or cursor["created_at"] is None:
                raise HistoryCursorUnavailable("Saved history cursor is unavailable.")
            cursor_time = cursor["created_at"]
        rows = connection.execute("""
            WITH displayed AS (
                SELECT created_at AS sort_created_at, task_id AS sort_task_id,
                       CASE WHEN length(CAST(task_id AS BLOB)) = 36 THEN task_id END AS task_id,
                       CASE WHEN length(CAST(request_id AS BLOB)) = 36 THEN request_id END AS request_id,
                       CASE WHEN input_mode IN ('text','voice') THEN input_mode END AS input_mode,
                       CASE WHEN length(CAST(created_at AS BLOB)) <= 64 THEN created_at END AS created_at,
                       CASE WHEN length(CAST(started_at AS BLOB)) <= 64 THEN started_at END AS started_at,
                       CASE WHEN length(CAST(completed_at AS BLOB)) <= 64 THEN completed_at END AS completed_at,
                       CASE WHEN final_state IN ('CREATED','RUNNING','STOPPING','ROLLING_BACK','SUCCEEDED',
                           'FAILED','STOPPED','STOPPED_WITH_RESIDUAL','DEFERRED','ABORTED_BY_CRASH') THEN final_state END AS final_state,
                       CASE WHEN route IN ('FAST','SMART','SCREEN','DEEP') THEN route END AS route,
                       CASE WHEN length(CAST(stop_reason AS BLOB)) <= 64 THEN stop_reason END AS stop_reason,
                       CASE WHEN length(CAST(error_code AS BLOB)) <= 64 THEN error_code END AS error_code,
                       pluma_history_command(CASE WHEN EXISTS(SELECT 1 FROM actions private_action WHERE private_action.task_id=tasks.task_id AND (private_action.tool LIKE '%clipboard%' OR private_action.tool IN ('paste','paste_text'))) THEN '[REDACTED CLIPBOARD COMMAND]' WHEN length(CAST(command_text AS BLOB)) <= ? THEN command_text END) AS command_text
                FROM tasks
                WHERE (? IS NULL OR created_at < ? OR (created_at = ? AND task_id < ?))
            )
            SELECT task_id, request_id, input_mode, command_text, created_at, started_at, completed_at,
                   final_state, route, stop_reason, error_code FROM displayed
            WHERE (? = '' OR pluma_history_match(command_text, task_id, final_state, route, input_mode))
            ORDER BY sort_created_at DESC, sort_task_id DESC LIMIT ?
        """, (MAX_COMMAND_BYTES, cursor_time, cursor_time, cursor_time, request.before_task_id, search, request.limit + 1)).fetchall()
    more = len(rows) > request.limit
    tasks = []
    for row in rows[:request.limit]:
        data = dict(row)
        for field in ("created_at", "started_at", "completed_at"):
            value = data[field]
            if value is not None:
                if not isinstance(value, str) or len(value) > 64 or datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
                    raise ValueError("Invalid saved timestamp.")
        data["stop_reason"], data["error_code"] = _identifier(data["stop_reason"]), _identifier(data["error_code"])
        tasks.append(SavedHistoryTaskV1(**data))
    return HistoryPageV1(request_id=request.request_id, before_task_id=request.before_task_id,
        tasks=tasks, has_more=more, next_before_task_id=tasks[-1].task_id if more else None)
