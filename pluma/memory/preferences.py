"""pluma.memory.preferences — User preference store.

Spec §18: Preferences are persisted in the SQLite Activity Ledger database.
No OS-automation or ML libraries in this module.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pluma.memory.db import DbConnection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PreferencesStore:
    """SQLite-backed user preference store."""

    def __init__(self, db: DbConnection) -> None:
        self._db = db

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a preference value by key. Returns default if not found."""
        row = self._db.execute_read_one(
            "SELECT value_json FROM preferences WHERE key = ?",
            (key,),
        )
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except (json.JSONDecodeError, TypeError):
            return default

    def set(self, key: str, value: Any) -> None:
        """Store or update a preference value."""
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO preferences (key, value_json, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, json.dumps(value), _now_iso()),
        )

    def delete(self, key: str) -> None:
        """Delete a preference by key."""
        self._db.execute_write(
            "DELETE FROM preferences WHERE key = ?",
            (key,),
        )

    def all(self) -> Dict[str, Any]:
        """Return all preferences as a key-value dict."""
        rows = self._db.execute_read("SELECT key, value_json FROM preferences")
        result: Dict[str, Any] = {}
        for r in rows:
            try:
                result[r["key"]] = json.loads(r["value_json"])
            except (json.JSONDecodeError, TypeError):
                result[r["key"]] = None
        return result
