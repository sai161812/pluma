"""pluma.perception — Screen perception, active window context, and UIA/OCR snapshot interfaces."""

from pluma.perception.capture import CaptureError, WindowCapture
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
from pluma.perception.ocr_adapter import OcrAdapter, OcrResult, OcrWord
from pluma.perception.ocr_lifecycle import (
    OcrLifecycleManager,
    OcrLifecycleState,
    get_default_ocr_lifecycle_manager,
    set_default_ocr_lifecycle_manager,
)
from pluma.perception.uia_snapshot import UiaSnapshot, UiaSnapshotBuilder

__all__ = [
    # Capture
    "WindowCapture",
    "CaptureError",
    # Context
    "ActiveWindowContext",
    "ActiveWindowInfo",
    # Element refs
    "BoundingBox",
    "ElementSource",
    "ScreenElement",
    "ScreenSnapshot",
    "SnapshotFreshness",
    "StaleSnapshotError",
    # Freshness
    "FreshnessChecker",
    "WindowMismatchError",
    # OCR
    "OcrAdapter",
    "OcrWord",
    "OcrResult",
    "OcrLifecycleManager",
    "OcrLifecycleState",
    "get_default_ocr_lifecycle_manager",
    "set_default_ocr_lifecycle_manager",
    # UIA
    "UiaSnapshotBuilder",
    "UiaSnapshot",
]
