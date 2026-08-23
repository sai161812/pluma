"""tests/unit/test_perception_freshness.py — Phase 7: FreshnessChecker unit tests."""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ScreenSnapshot, StaleSnapshotError
from pluma.perception.freshness import FreshnessChecker, WindowMismatchError


def _make_snapshot(ttl_seconds: float = 3.0, process: str = "notepad.exe", title: str = "Untitled - Notepad") -> ScreenSnapshot:
    now = datetime.now(timezone.utc)
    return ScreenSnapshot(
        snapshot_id="snap-123",
        created_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
        active_process=process,
        active_window_title=title,
        window_rect=BoundingBox(left=100, top=100, right=800, bottom=600),
        dpi_scale=1.0,
        controls=[],
        ocr_words=[],
    )


def test_freshness_checker_valid_and_fresh() -> None:
    mock_context = MagicMock(spec=ActiveWindowContext)
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=111,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        is_valid=True,
    )

    checker = FreshnessChecker(context=mock_context)
    snap = _make_snapshot(ttl_seconds=5.0)

    assert checker.is_valid(snap)
    checker.validate(snap)


def test_freshness_checker_expired_snapshot_raises_stale_error() -> None:
    mock_context = MagicMock(spec=ActiveWindowContext)
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=111,
        process_name="notepad.exe",
        window_title="Untitled - Notepad",
        is_valid=True,
    )

    checker = FreshnessChecker(context=mock_context)
    # Expired snapshot
    snap = _make_snapshot(ttl_seconds=-1.0)

    assert snap.is_expired
    assert not checker.is_valid(snap)
    with pytest.raises(StaleSnapshotError, match="expired at"):
        checker.validate(snap)


def test_freshness_checker_window_mismatch_raises_error() -> None:
    mock_context = MagicMock(spec=ActiveWindowContext)
    # Active window changed to Chrome
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=222,
        process_name="chrome.exe",
        window_title="New Tab - Google Chrome",
        is_valid=True,
    )

    checker = FreshnessChecker(context=mock_context)
    snap = _make_snapshot(ttl_seconds=5.0, process="notepad.exe", title="Untitled - Notepad")

    assert not checker.is_valid(snap)
    with pytest.raises(WindowMismatchError, match="Active window focus changed"):
        checker.validate(snap)
