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
        self.task_resolver = None

    def _apply(self, task_id, action, state):
        owned_inverse = action in ('safe_delete', 'set_volume', 'mute', 'unmute', 'set_default_audio_device') or (action == 'pending_mutation' and state.get('tool') == 'safe_delete')
        capsule = self.task_resolver(task_id) if self.task_resolver is not None else None
        if owned_inverse and capsule is not None:
            from pluma.rollback.owned import apply_owned
            return apply_owned(action, state, capsule)
        return self._recipes.apply(action, state)

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
                logger.error("Failed to query undo records for task %s", task_id)
                failed += 1
                step_results.append(RollbackStepResult(ok=False, action="undo_query",
                    message="Undo records could not be read.", error="UNDO_QUERY_FAILED"))

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

                claim_id = None
                if self._ledger and action_id is not None:
                    try:
                        claim_id = self._ledger.claim_undo(action_id, task_id, raw_json)
                    except Exception:
                        claim_id = None
                    if claim_id is None:
                        failed += 1
                        step_results.append(RollbackStepResult(ok=False, action=action_name,
                            message="Undo is already claimed or its state could not be verified.", error="UNDO_CLAIM_UNVERIFIED"))
                        continue
                step_res = self._apply(task_id, action_name, undo_data)

                # Atomically record rollback result and consume undo record in one transaction
                if self._ledger and action_id is not None:
                    try:
                        self._ledger.consume_undo_and_mark_result_atomic(
                            action_row_id=action_id,
                            ok=step_res.ok,
                            result=step_res.data or {"message": step_res.message, "error": step_res.error},
                            claim_id=claim_id,
                        )
                    except Exception as e:
                        logger.error("Failed to atomically record rollback for action %s: %s", action_id, e)
                        # Failure in atomic ledger update must never report false success
                        step_res = RollbackStepResult(
                            ok=False,
                            action=action_name,
                            message=f"Rollback succeeded locally but atomic ledger consumption failed: {e}",
                            error="UNDO_CONSUMPTION_FAILED",
                        )

                step_results.append(step_res)
                if step_res.ok:
                    succeeded += 1
                    # Remove only the exact pre-state whose verified rollback
                    # and ledger consumption succeeded. Never discard a conflict.
                    if memory_undo_stack is not None:
                        for item in list(memory_undo_stack):
                            if (item == undo_data or (item.get("action") == "pending_mutation"
                                    and item.get("action_row_id") == action_id)):
                                memory_undo_stack.remove(item)
                else:
                    failed += 1



        elif memory_undo_stack:
            # Fallback to in-memory undo stack if DB was not queried or returned no rows
            # Pop/iterate in reverse order; consumed records are removed from memory_undo_stack
            to_remove = []
            for item in list(reversed(memory_undo_stack)):
                attempted += 1
                action_name = item.get("action", "")
                step_res = self._apply(task_id, action_name, item)
                step_results.append(step_res)
                if step_res.ok:
                    succeeded += 1
                    to_remove.append(item)
                else:
                    failed += 1

            for itm in to_remove:
                if itm in memory_undo_stack:
                    memory_undo_stack.remove(itm)


        all_ok = (failed == 0)
        has_residual = (failed > 0)

        if attempted == 0 and has_residual:
            summary = "Rollback records could not be verified. Residual effects are unknown."
        elif attempted == 0:
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
                        try:
                            self._ledger.consume_undo_and_mark_result_atomic(
                                action_row_id=action_id,
                                ok=res.ok,
                                result=res.data or {"message": res.message, "error": res.error},
                            )
                        except Exception as consume_err:
                            logger.error("Failed to atomically record rollback for action %s: %s", action_id, consume_err)
                            res = RollbackStepResult(
                                ok=False,
                                action=action_name,
                                message=f"Rollback succeeded locally but atomic ledger consumption failed: {consume_err}",
                                error="UNDO_CONSUMPTION_FAILED",
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
