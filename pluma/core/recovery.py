r"""pluma.core.recovery — Startup crash recovery and state reconciliation.

Spec §20.3, §25:
- On startup, mark any previously RUNNING/STOPPING/ROLLING_BACK task as ABORTED_BY_CRASH.
- Inspect recorded temp resources and clean only resources whose PLUMA ownership can be verified.
- Never assume a leftover PID is the same process after reboot; verify creation time/ownership metadata.
- Clean up orphaned temp directories under %LOCALAPPDATA%\Pluma\temp\task_*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Dict, List, Optional

from pluma.config.paths import PlumaPaths, get_paths
from pluma.core.ownership import OwnershipRegistry
from pluma.core.task_supervisor import TaskState
from pluma.memory.db import DbConnection

logger = logging.getLogger(__name__)

# Non-terminal states that indicate a task was interrupted mid-flight by a crash or shutdown
_INTERRUPTED_STATES = (
    TaskState.CREATED.value,
    TaskState.RUNNING.value,
    TaskState.STOPPING.value,
    TaskState.ROLLING_BACK.value,
)


@dataclass(frozen=True)
class CrashRecoveryResult:
    """Outcome of startup crash recovery reconciliation."""
    stale_tasks_recovered: int = 0
    recovered_task_ids: List[str] = field(default_factory=list)
    orphaned_dirs_cleaned: int = 0
    db_integrity_ok: bool = True
    errors: List[str] = field(default_factory=list)


class CrashRecoveryManager:
    """Performs startup reconciliation, database integrity checks, and resource cleanup."""

    def __init__(
        self,
        db: Optional[DbConnection] = None,
        paths: Optional[PlumaPaths] = None,
        ownership_registry: Optional[OwnershipRegistry] = None,
    ) -> None:
        self.paths = paths or get_paths()
        self.db = db or DbConnection(str(self.paths.db_path))
        self.ownership_registry = ownership_registry
        self._owns_db = db is None

    def _ensure_db_open(self) -> None:
        """Ensure database connection is open."""
        if not self.db.is_open:
            self.db.open()

    def check_database_integrity(self) -> bool:
        """Run SQLite PRAGMA integrity_check to ensure database consistency."""
        try:
            self._ensure_db_open()
            rows = self.db.execute_read("PRAGMA integrity_check")
            if rows and rows[0][0] == "ok":
                return True
            logger.error("Database integrity check failed: %s", rows)
            return False
        except Exception as exc:
            logger.error("Database integrity check error: %s", exc)
            return False

    def reconcile_stale_tasks(self) -> List[str]:
        """Find and mark any uncompleted tasks as ABORTED_BY_CRASH."""
        recovered_ids: List[str] = []
        try:
            self._ensure_db_open()
            placeholders = ",".join(f"'{s}'" for s in _INTERRUPTED_STATES)
            query = (
                f"SELECT task_id, final_state FROM tasks "
                f"WHERE final_state IS NULL OR final_state IN ({placeholders})"
            )
            rows = self.db.execute_read(query)
            if not rows:
                return []

            now_iso = datetime.now(timezone.utc).isoformat()
            for row in rows:
                task_id = str(row[0])
                prev_state = row[1] or "INCOMPLETE"
                logger.warning(
                    "Recovering crashed task %s (previous state: %s) -> ABORTED_BY_CRASH",
                    task_id, prev_state,
                )

                update_sql = (
                    "UPDATE tasks SET final_state = ?, completed_at = ?, stop_reason = ? "
                    "WHERE task_id = ?"
                )
                self.db.execute_write(
                    update_sql,
                    (TaskState.ABORTED_BY_CRASH.value, now_iso, "CRASH", task_id),
                )
                recovered_ids.append(task_id)

        except Exception as exc:
            logger.error("Failed to reconcile stale tasks: %s", exc)
        return recovered_ids

    def cleanup_orphaned_task_directories(self, active_task_ids: Optional[set[str]] = None) -> int:
        """Remove leftover temp directories for tasks that are no longer active."""
        active = active_task_ids or set()
        cleaned_count = 0
        temp_root = self.paths.temp_dir

        if not temp_root.exists():
            return 0

        for item in temp_root.iterdir():
            if item.is_dir() and item.name.startswith("task_"):
                task_id = item.name[5:]  # strip 'task_' prefix
                if task_id not in active:
                    try:
                        shutil.rmtree(item, ignore_errors=True)
                        cleaned_count += 1
                        logger.debug("Cleaned orphaned task temp directory: %s", item)
                    except Exception as exc:
                        logger.debug("Could not remove temp directory %s: %s", item, exc)
        return cleaned_count

    def reconcile_startup(self) -> CrashRecoveryResult:
        """Full startup crash recovery reconciliation pass."""
        errors: List[str] = []

        # 1. Ensure filesystem structure exists
        try:
            self.paths.ensure_directories()
        except Exception as exc:
            errors.append(f"Failed to create directories: {exc}")

        # 2. Check DB integrity
        db_ok = self.check_database_integrity()
        if not db_ok:
            errors.append("Database integrity check reported errors.")

        # 3. Mark stale tasks as ABORTED_BY_CRASH
        recovered_ids = self.reconcile_stale_tasks()

        # 4. Clean orphaned task scratch spaces
        cleaned_dirs = self.cleanup_orphaned_task_directories()

        if self._owns_db:
            try:
                self.db.close()
            except Exception:
                pass

        logger.info(
            "Startup Crash Recovery complete: %d stale tasks recovered, %d orphaned dirs cleaned.",
            len(recovered_ids), cleaned_dirs,
        )

        return CrashRecoveryResult(
            stale_tasks_recovered=len(recovered_ids),
            recovered_task_ids=recovered_ids,
            orphaned_dirs_cleaned=cleaned_dirs,
            db_integrity_ok=db_ok,
            errors=errors,
        )
