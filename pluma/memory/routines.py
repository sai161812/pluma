"""pluma.memory.routines — User-defined routine store.

Spec §18: Routines are persisted in the SQLite Activity Ledger database.
No OS-automation or ML libraries in this module.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pluma.memory.db import DbConnection


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoutineStore:
    """SQLite-backed user routine store."""

    def __init__(self, db: DbConnection) -> None:
        self._db = db

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve a routine by unique name, or None."""
        row = self._db.execute_read_one(
            "SELECT id, name, definition_json, updated_at FROM routines WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        try:
            definition = json.loads(row["definition_json"])
        except (json.JSONDecodeError, TypeError):
            definition = {}
        return {
            "id": row["id"],
            "name": row["name"],
            "definition": definition,
            "updated_at": row["updated_at"],
        }

    def save(self, name: str, definition: Dict[str, Any], routine_id: Optional[str] = None) -> str:
        """Save or update a routine. Returns routine UUID."""
        rid = routine_id or str(uuid.uuid4())
        self._db.execute_write(
            """
            INSERT OR REPLACE INTO routines (id, name, definition_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (rid, name, json.dumps(definition), _now_iso()),
        )
        return rid

    def delete(self, name: str) -> None:
        """Delete a routine by name."""
        self._db.execute_write(
            "DELETE FROM routines WHERE name = ?",
            (name,),
        )

    def all(self) -> List[Dict[str, Any]]:
        """Return all routines as a list of dictionaries."""
        rows = self._db.execute_read("SELECT id, name, definition_json, updated_at FROM routines ORDER BY name")
        result: List[Dict[str, Any]] = []
        for r in rows:
            try:
                definition = json.loads(r["definition_json"])
            except (json.JSONDecodeError, TypeError):
                definition = {}
            result.append({
                "id": r["id"],
                "name": r["name"],
                "definition": definition,
                "updated_at": r["updated_at"],
            })
        return result
