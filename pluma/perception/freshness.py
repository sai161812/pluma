"""pluma.perception.freshness — Snapshot TTL and freshness checks (stub body).

The primary freshness logic lives in pluma.perception.element_refs.SnapshotFreshness.
This module provides the runtime freshness checker that also validates active-window
identity at the moment of action execution.

Spec §8.2: "Re-check active window identity and target geometry before
coordinate-based interaction."
"""

from pluma.perception.element_refs import SnapshotFreshness, StaleSnapshotError

__all__ = ["SnapshotFreshness", "StaleSnapshotError"]
