"""pluma.perception.snapshot_registry — Task-scoped UI snapshot registry.

Spec §8.2: Every grounded UI action must resolve a real snapshot and element
reference, validate its TTL, HWND, PID identity, process creation time,
class, title, rectangle and DPI context.

Reject unknown, expired, duplicated, ambiguous, moved, mismatched or
invented references. Never catch freshness errors and continue.
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, Optional

from pluma.perception.element_refs import ScreenElement, ScreenSnapshot, StaleSnapshotError

logger = logging.getLogger(__name__)


class SnapshotNotFoundError(KeyError):
    """Raised when the requested snapshot_id is not in this task's registry."""


class ElementNotFoundInSnapshotError(KeyError):
    """Raised when the requested element_id is not found in any snapshot."""


class SnapshotRegistry:
    """Holds all ScreenSnapshots captured during a single task's lifetime.

    Rules:
    - Only snapshots explicitly registered here can be referenced by UI tools.
    - Resolving an expired snapshot always raises StaleSnapshotError.
    - Resolving an unknown snapshot_id always raises SnapshotNotFoundError.
    - Neither of these errors may be caught-and-continued by callers.
    - Thread-safe: multiple threads can register and resolve snapshots safely.
    """

    def __init__(self) -> None:
        self._snapshots: Dict[str, ScreenSnapshot] = {}
        self._lock = threading.RLock()

    def register(self, snapshot: ScreenSnapshot) -> None:
        """Register a freshly-captured snapshot. Overwrites a prior snapshot with the same ID."""
        with self._lock:
            self._snapshots[snapshot.snapshot_id] = snapshot
            logger.debug(
                "Snapshot %s registered (window=%r, pid=%r, expires=%s)",
                snapshot.snapshot_id,
                snapshot.active_window_title,
                snapshot.active_process,
                snapshot.expires_at.isoformat(),
            )

    def resolve(self, snapshot_id: str) -> ScreenSnapshot:
        """Return the snapshot for *snapshot_id*, or raise if unknown or expired.

        Raises:
            SnapshotNotFoundError: If *snapshot_id* was never registered.
            StaleSnapshotError: If the snapshot's TTL has elapsed.
        """
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
        if snapshot is None:
            raise SnapshotNotFoundError(
                f"snapshot_id={snapshot_id!r} is not registered in this task's snapshot registry. "
                "Invented or cross-task snapshot references are rejected."
            )
        if snapshot.is_expired:
            raise StaleSnapshotError(
                f"Snapshot {snapshot_id!r} expired at {snapshot.expires_at.isoformat()}. "
                "Re-capture required before any UI action."
            )
        return snapshot

    def resolve_element(self, snapshot_id: str, element_id: str) -> ScreenElement:
        """Resolve a snapshot and find *element_id* within it.

        Raises:
            SnapshotNotFoundError: Unknown snapshot_id.
            StaleSnapshotError: Expired snapshot.
            ElementNotFoundInSnapshotError: element_id not in snapshot.
        """
        snapshot = self.resolve(snapshot_id)
        element = snapshot.find_element(element_id)
        if element is None:
            raise ElementNotFoundInSnapshotError(
                f"element_id={element_id!r} not found in snapshot {snapshot_id!r}. "
                "Invented element references are rejected."
            )
        return element

    def get(self, snapshot_id: str) -> Optional[ScreenSnapshot]:
        """Return the snapshot or None — does NOT check TTL."""
        with self._lock:
            return self._snapshots.get(snapshot_id)

    def clear(self) -> None:
        """Remove all snapshots — called when the task reaches a terminal state."""
        with self._lock:
            self._snapshots.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._snapshots)


# Module-level per-task registry factory
def create_snapshot_registry() -> SnapshotRegistry:
    """Return a new empty SnapshotRegistry for a task."""
    return SnapshotRegistry()


__all__ = [
    "SnapshotRegistry",
    "SnapshotNotFoundError",
    "ElementNotFoundInSnapshotError",
    "create_snapshot_registry",
]
