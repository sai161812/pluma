"""pluma.perception — Screen perception, active window context, and UIA snapshot interfaces."""

from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo
from pluma.perception.element_refs import (
    BoundingBox,
    ElementSource,
    ScreenElement,
    ScreenSnapshot,
    SnapshotFreshness,
    StaleSnapshotError,
)
from pluma.perception.freshness import FreshnessChecker, WindowMismatchError
from pluma.perception.uia_snapshot import UiaSnapshot, UiaSnapshotBuilder

__all__ = [
    "ActiveWindowContext",
    "ActiveWindowInfo",
    "BoundingBox",
    "ElementSource",
    "ScreenElement",
    "ScreenSnapshot",
    "SnapshotFreshness",
    "StaleSnapshotError",
    "FreshnessChecker",
    "WindowMismatchError",
    "UiaSnapshotBuilder",
    "UiaSnapshot",
]
