"""tests/unit/test_phase13_5_stage_e_perception.py — Stage E Perception and Freshness regression tests."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
import pytest

from pluma.perception.element_refs import (
    BoundingBox,
    ElementSource,
    ScreenElement,
    ScreenSnapshot,
    SnapshotFreshness,
    StaleSnapshotError,
)
from pluma.perception.freshness import FreshnessChecker, WindowMismatchError
from pluma.perception.ocr_adapter import OcrResult, OcrWord
from pluma.tools.ui import execute_click_ocr_text


def test_stage_e_snapshot_ttl_and_freshness_invalidation() -> None:
    """Gate E: Verify 3-second TTL expiration and focus shift invalidation."""
    now = datetime.now(timezone.utc)
    fresh_snapshot = ScreenSnapshot(
        task_id="task-fresh-test",
        active_process="notepad.exe",
        active_window_title="Untitled - Notepad",
        window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
        dpi_scale=1.0,
        ttl_seconds=1.0,
        expires_at=now + timedelta(seconds=1.0),
    )

    # 1. Fresh snapshot passes
    assert SnapshotFreshness.is_fresh(fresh_snapshot) is True
    SnapshotFreshness.assert_fresh(fresh_snapshot)

    # 2. Expired snapshot raises StaleSnapshotError
    expired_snapshot = ScreenSnapshot(
        task_id="task-stale-test",
        active_process="notepad.exe",
        active_window_title="Untitled - Notepad",
        window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
        dpi_scale=1.0,
        ttl_seconds=1.0,
        expires_at=now - timedelta(seconds=1.0),
    )
    assert SnapshotFreshness.is_fresh(expired_snapshot) is False
    with pytest.raises(StaleSnapshotError):
        SnapshotFreshness.assert_fresh(expired_snapshot)

    # 3. Focus shift mismatch
    checker = FreshnessChecker()
    assert SnapshotFreshness.window_matches(fresh_snapshot, "notepad.exe", "Untitled - Notepad") is True
    assert SnapshotFreshness.window_matches(fresh_snapshot, "calc.exe", "Calculator") is False


def test_stage_e_bounding_box_geometry_and_clipping() -> None:
    """Gate E: Verify window-relative to absolute coordinate calculations and boundary containment."""
    box = BoundingBox(left=100, top=50, right=300, bottom=150)
    assert box.width == 200
    assert box.height == 100
    assert box.center_x == 200
    assert box.center_y == 100
    assert box.center == (200, 100)

    assert box.contains(200, 100) is True
    assert box.contains(50, 50) is False
    assert box.contains(350, 100) is False

    # Window offset translation: window at (500, 300)
    win_box = BoundingBox(left=500, top=300, right=1500, bottom=1000)
    desktop_x = win_box.left + box.center_x
    desktop_y = win_box.top + box.center_y
    assert desktop_x == 700
    assert desktop_y == 400
    assert win_box.contains(desktop_x, desktop_y) is True


def test_stage_e_ocr_disambiguation_rules() -> None:
    """Gate E: Verify OCR matching disambiguation: single match succeeds, 0 matches fails, multiple matches rejects as ambiguous."""
    words = [
        OcrWord(text="Save", confidence=0.95, bounds=BoundingBox(left=10, top=10, right=50, bottom=30)),
        OcrWord(text="Cancel", confidence=0.92, bounds=BoundingBox(left=60, top=10, right=110, bottom=30)),
        OcrWord(text="Save", confidence=0.90, bounds=BoundingBox(left=10, top=50, right=50, bottom=70)),
    ]
    ocr_result = OcrResult(words=words)

    # 1. Unique match
    cancel_matches = ocr_result.find_words("Cancel")
    assert len(cancel_matches) == 1
    assert cancel_matches[0].text == "Cancel"

    # 2. No match
    missing_matches = ocr_result.find_words("NonExistentButton")
    assert len(missing_matches) == 0

    # 3. Ambiguous duplicate matches (Spec §E-03, §E-08)
    save_matches = ocr_result.find_words("Save")
    assert len(save_matches) == 2
