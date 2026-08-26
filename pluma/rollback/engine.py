"""pluma.rollback.engine — Rollback and undo engine.

Spec §13, §17:
Every reversible action captures minimum safe pre-state for evidence-based undo.
Rollback is executed automatically on STOP or failure, walking completed
reversible steps in reverse order (newest first).

No heavy ML or OS-automation libraries in this module.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pluma.memory.activity import ActivityLedger, ActivityQuery
from pluma.rollback.recipes import RollbackRecipes, RollbackStepResult

logger = logging.getLogger(__name__)


@dataclass
class RollbackResult:
    """Full outcome of a task rollback operation."""
    task_id: str
    all_ok: bool
    steps_attempted: int
    steps_succeeded: int
    steps_failed: int
    step_results: List[RollbackStepResult] = field(default_factory=list)
    has_residual: bool = False
    factual_summary: str = ""


class RollbackEngine:
    """Rollback and undo engine for reversible task actions."""

    def __init__(
        self,
        ledger: Optional[ActivityLedger] = None,
        query: Optional[ActivityQuery] = None,
        recipes: Optional[RollbackRecipes] = None,
    ) -> None:
        self._ledger = ledger
        self._query = query
        if not self._query and self._ledger and getattr(self._ledger, "_db", None):
            self._query = ActivityQuery(self._ledger._db)
        self._recipes = recipes or RollbackRecipes()

    @property
    def recipes(self) -> RollbackRecipes:
        return self._recipes

    def rollback_task(
        self,
        task_id: str,
        cancellation_token: Any = None,
        memory_undo_stack: Optional[List[Dict[str, Any]]] = None,
    ) -> RollbackResult:
        """Walk completed reversible actions backward and apply tool rollback recipes.

        Applies undo records in reverse order (newest first).
        Records rollback outcome back to the Activity Ledger for each action.
        """
        step_results: List[RollbackStepResult] = []
        attempted = 0
        succeeded = 0
        failed = 0

        # 1. Fetch available undo records from database if available
        db_records: List[Dict[str, Any]] = []
        if self._query:
            try:
                db_records = self._query.available_undo_records_for_task(task_id)
            except Exception as e:
                logger.error("Failed to query available undo records for task %s: %s", task_id, e)

        if db_records:
            # Reverse order is already guaranteed by ORDER BY step_index DESC
            for rec in db_records:
                attempted += 1
                action_id = rec.get("action_id")
                raw_json = rec.get("undo_json", "{}")
                try:
                    undo_data = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                except Exception:
                    undo_data = {}

                tool_name = rec.get("tool", "")
                action_name = undo_data.get("action", tool_name)

                step_res = self._recipes.apply(action_name, undo_data)
                step_results.append(step_res)

                if step_res.ok:
                    succeeded += 1
                else:
                    failed += 1

                # Update database record with rollback result
                if self._ledger and action_id is not None:
                    try:
                        self._ledger.mark_rollback_result(
                            action_row_id=action_id,
                            ok=step_res.ok,
                            result=step_res.data or {"message": step_res.message, "error": step_res.error},
                        )
                    except Exception as e:
                        logger.error("Failed to mark rollback result for action %s: %s", action_id, e)

        elif memory_undo_stack:
            # Fallback to in-memory undo stack if DB was not queried or returned no rows
            # Pop/iterate in reverse order
            reversed_stack = list(reversed(memory_undo_stack))
            for item in reversed_stack:
                attempted += 1
                action_name = item.get("action", "")
                step_res = self._recipes.apply(action_name, item)
                step_results.append(step_res)
                if step_res.ok:
                    succeeded += 1
                else:
                    failed += 1

        all_ok = (failed == 0)
        has_residual = (failed > 0)

        if attempted == 0:
            summary = "No reversible actions to rollback."
        elif all_ok:
            summary = f"Rollback: successfully restored {succeeded} action{'s' if succeeded != 1 else ''}."
        else:
            summary = f"Rollback: {succeeded} succeeded, {failed} failed (residual effects remain)."

        return RollbackResult(
            task_id=task_id,
            all_ok=all_ok,
            steps_attempted=attempted,
            steps_succeeded=succeeded,
            steps_failed=failed,
            step_results=step_results,
            has_residual=has_residual,
            factual_summary=summary,
        )

    def rollback_last_reversible(
        self,
        task_id: Optional[str] = None,
        undo_data: Optional[Dict[str, Any]] = None,
    ) -> RollbackStepResult:
        """Reverse only the single most recent reversible action."""
        if undo_data is not None:
            action_name = undo_data.get("action", "")
            return self._recipes.apply(action_name, undo_data)

        if task_id and self._query:
            try:
                records = self._query.available_undo_records_for_task(task_id)
                if records:
                    rec = records[0]  # Newest
                    action_id = rec.get("action_id")
                    raw_json = rec.get("undo_json", "{}")
                    parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
                    action_name = parsed.get("action", rec.get("tool", ""))
                    res = self._recipes.apply(action_name, parsed)
                    if self._ledger and action_id is not None:
                        self._ledger.mark_rollback_result(
                            action_row_id=action_id,
                            ok=res.ok,
                            result=res.data or {"message": res.message, "error": res.error},
                        )
                    return res
            except Exception as e:
                logger.error("Failed to rollback last reversible action for %s: %s", task_id, e)

        return RollbackStepResult(
            ok=False,
            action="",
            message="No undo records available to reverse.",
            error="No undo records found.",
        )
