"""pluma.memory.aliases — User-defined command alias store.

Spec §18: Aliases are persisted in the SQLite Activity Ledger database.
No OS-automation or ML libraries in this module.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pluma.memory.db import DbConnection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AliasStore:
    """SQLite-backed user command/path alias store."""

    def __init__(self, db: DbConnection) -> None:
        self._db = db

    def get(self, alias: str) -> Optional[Dict[str, Any]]:
        """Retrieve target descriptor for an alias, or None."""
        row = self._db.execute_read_one(
            "SELECT target_json FROM aliases WHERE alias = ?",
            (alias,),
        )
        if row is None:
            return None
        try:
            return json.loads(row["target_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def set(self, alias: str, target: Dict[str, Any]) -> None:
        """Store or update an alias target descriptor."""
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO aliases (alias, target_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (alias, json.dumps(target), _now_iso()),
        )

    def delete(self, alias: str) -> None:
        """Delete an alias."""
        self._db.execute_write(
            "DELETE FROM aliases WHERE alias = ?",
            (alias,),
        )

    def all(self) -> Dict[str, Dict[str, Any]]:
        """Return all aliases as a dict of alias -> target."""
        rows = self._db.execute_read("SELECT alias, target_json FROM aliases")
        result: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            try:
                result[r["alias"]] = json.loads(r["target_json"])
            except (json.JSONDecodeError, TypeError):
                result[r["alias"]] = {}
        return result
