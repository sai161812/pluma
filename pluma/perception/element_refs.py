"""pluma.perception.element_refs — ScreenSnapshot, ScreenElement, freshness.

These are the short-lived, task-scoped references that ground any screen-aware
action. References expire quickly (default TTL = 3 s per config). Before any
coordinate-based action, the orchestrator must re-check active window identity
and snapshot freshness.

Spec §8.2 ScreenSnapshot and ScreenElement contracts.
Spec §8: "ScreenElement references expire quickly."

No OS-automation, ML, or adapter code in this module.
The perception adapters (uia_snapshot.py, ocr_adapter.py) populate these types
and return them to the orchestrator. The orchestrator and verifier consume them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, computed_field


class ElementSource(str, Enum):
    """How this screen element was discovered."""
    UIA = "UIA"       # Windows UI Automation — preferred.
    OCR = "OCR"       # Optical character recognition — fallback.


class BoundingBox(BaseModel):
    """Window-relative pixel rectangle for a screen element.

    Coordinates are relative to the top-left corner of the target window,
    not the desktop. This is the safe form that survives window moves (as
    long as the snapshot is fresh and the window has not moved since capture).
    """
    model_config = {"frozen": True}

    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> int:
        return (self.left + self.right) // 2

    @property
    def center_y(self) -> int:
        return (self.top + self.bottom) // 2


class ScreenElement(BaseModel):
    """One addressable element discovered on screen.

    Spec §8.2 ScreenElement fields:
      element_id, snapshot_id, source, label, control_type?,
      bounds, confidence, invocation_capability
    """
    model_config = {"frozen": True}

    element_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    snapshot_id: str
    source: ElementSource
    label: str = Field(
        min_length=0,
        max_length=512,
        description="Human-readable label or OCR text for this element.",
    )
    control_type: Optional[str] = Field(
        default=None,
        description="UIA control type string (e.g. 'Button', 'Edit', 'MenuItem').",
    )
    bounds: BoundingBox
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence score. 1.0 for UIA (semantic); 0.0-1.0 for OCR.",
    )
    invocation_capability: Optional[str] = Field(
        default=None,
        description=(
            "How this element can be acted on: 'invoke', 'set_value', "
            "'expand_collapse', 'click', 'type'. None means read-only."
        ),
    )
    uia_automation_id: Optional[str] = Field(
        default=None,
        description="UIA AutomationId if available — more stable than label.",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ScreenSnapshot(BaseModel):
    """A point-in-time view of the active window's accessible content.

    Spec §8.2 ScreenSnapshot fields:
      snapshot_id, created_at, active_process, active_window_title,
      window_rect, dpi_scale, controls[], ocr_words[], image_ref, expires_at

    image_ref is ephemeral and not persisted by default (spec §8.2).
    The Activity Ledger stores only necessary target metadata.
    """
    model_config = {"frozen": True}

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime  # Set by the capture adapter from config.snapshot_ttl_seconds.

    # Window context at capture time
    active_process: str
    active_window_title: str
    window_rect: BoundingBox  # Desktop-absolute window rectangle at capture time.
    dpi_scale: float = Field(gt=0.0, description="DPI scale factor, e.g. 1.25 for 125%.")

    # Discovered elements
    controls: List[ScreenElement] = Field(default_factory=list)
    ocr_words: List[ScreenElement] = Field(
        default_factory=list,
        description="OCR-derived words with confidence and bounds. Empty if OCR did not run.",
    )

    # Ephemeral image reference (not persisted)
    image_ref: Optional[str] = Field(
        default=None,
        description=(
            "Transient path or handle to the captured image. "
            "Not stored in the Activity Ledger. Set to None after OCR completes."
        ),
    )

    @computed_field  # type: ignore[misc]
    @property
    def is_expired(self) -> bool:
        """True if the snapshot is past its TTL and must not be used for actions."""
        return datetime.now(timezone.utc) >= self.expires_at

    def find_element(self, element_id: str) -> Optional[ScreenElement]:
        """Return the element with *element_id*, or None."""
        for el in self.controls + self.ocr_words:
            if el.element_id == element_id:
                return el
        return None

    def ledger_metadata(self) -> Dict[str, Any]:
        """Return the minimal metadata suitable for storing in the Activity Ledger.

        Spec §8.2: "The Activity Ledger stores only necessary target metadata
        such as app/window, label/control identity, confidence and geometry."
        No image_ref, no full element list.
        """
        return {
            "snapshot_id": self.snapshot_id,
            "active_process": self.active_process,
            "active_window_title": self.active_window_title,
            "dpi_scale": self.dpi_scale,
            "created_at": self.created_at.isoformat(),
        }


class SnapshotFreshness:
    """Utility for checking whether a snapshot is still safe to act on.

    Spec §8.2: "Before a coordinate-based action, re-check active window
    identity and target geometry to prevent clicking stale locations."
    """

    @staticmethod
    def is_fresh(snapshot: ScreenSnapshot) -> bool:
        """Return True if the snapshot has not passed its TTL."""
        return not snapshot.is_expired

    @staticmethod
    def assert_fresh(snapshot: ScreenSnapshot) -> None:
        """Raise StaleSnapshotError if the snapshot is expired."""
        if snapshot.is_expired:
            raise StaleSnapshotError(
                f"Snapshot {snapshot.snapshot_id!r} expired at "
                f"{snapshot.expires_at.isoformat()}. Re-capture required."
            )

    @staticmethod
    def window_matches(snapshot: ScreenSnapshot, current_process: str, current_title: str) -> bool:
        """Return True if the active window is the same as when the snapshot was taken.

        Both process name and window title must match. Used before any
        UIA or coordinate interaction to prevent acting on the wrong window.
        """
        return (
            snapshot.active_process == current_process
            and snapshot.active_window_title == current_title
        )


class StaleSnapshotError(RuntimeError):
    """Raised when an action attempts to use an expired ScreenSnapshot."""
