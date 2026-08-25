"""pluma.perception.freshness — Snapshot TTL and window focus freshness validator.

Spec §8.2: "Before a coordinate-based or UIA action, re-check active window
identity and target geometry to prevent clicking stale locations."
"""

from __future__ import annotations

import logging
from typing import Optional

from pluma.perception.context import ActiveWindowContext
from pluma.perception.element_refs import (
    ScreenSnapshot,
    SnapshotFreshness,
    StaleSnapshotError,
)

logger = logging.getLogger(__name__)


class WindowMismatchError(RuntimeError):
    """Raised when active window changes focus after snapshot capture."""


class FreshnessChecker:
    """Validates that a ScreenSnapshot has not expired and still matches active window focus."""

    def __init__(self, context: Optional[ActiveWindowContext] = None) -> None:
        self._context = context or ActiveWindowContext()

    def validate(
        self,
        snapshot: ScreenSnapshot,
        require_window_match: bool = True,
    ) -> None:
        """Assert that snapshot is not expired and foreground window has not changed.

        Raises:
            StaleSnapshotError: If snapshot has passed its TTL.
            WindowMismatchError: If active window focus has moved to another window.
        """
        # 1. Check TTL expiration
        SnapshotFreshness.assert_fresh(snapshot)

        # 2. Check window match if required
        if require_window_match:
            active = self._context.get_active_window()
            if not active.is_valid:
                raise WindowMismatchError("Foreground window is no longer valid or accessible.")

            if not SnapshotFreshness.window_matches(snapshot, active.process_name, active.window_title):
                raise WindowMismatchError(
                    f"Active window focus changed: expected '{snapshot.active_process}' "
                    f"('{snapshot.active_window_title}'), but found '{active.process_name}' "
                    f"('{active.window_title}'). Action aborted for safety."
                )

    def is_valid(
        self,
        snapshot: ScreenSnapshot,
        require_window_match: bool = True,
    ) -> bool:
        """Return True if snapshot is fresh and focus has not shifted."""
        try:
            self.validate(snapshot, require_window_match=require_window_match)
            return True
        except Exception:
            return False


__all__ = [
    "FreshnessChecker",
    "SnapshotFreshness",
    "StaleSnapshotError",
    "WindowMismatchError",
]
