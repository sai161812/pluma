"""tests/unit/test_perception_ocr_lifecycle.py — Phase 8: OcrLifecycleManager unit tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock
import pytest

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import BoundingBox
from pluma.perception.ocr_adapter import OcrWord
from pluma.perception.ocr_lifecycle import OcrLifecycleManager, OcrLifecycleState


def test_ocr_lifecycle_cold_at_init() -> None:
    manager = OcrLifecycleManager(idle_unload_seconds=0.2)
    assert manager.state == OcrLifecycleState.COLD


def test_ocr_lifecycle_warm_after_run() -> None:
    mock_backend = MagicMock()
    mock_backend.recognize.return_value = [
        OcrWord(text="Login", confidence=0.98, bounds=BoundingBox(left=10, top=10, right=80, bottom=40))
    ]

    manager = OcrLifecycleManager(idle_unload_seconds=0.5, custom_backend=mock_backend)
    res = manager.run_ocr(b"BM_TEST")

    assert len(res.words) == 1
    assert res.words[0].text == "Login"
    assert manager.state == OcrLifecycleState.WARM


def test_ocr_lifecycle_idle_unload() -> None:
    mock_backend = MagicMock()
    mock_backend.recognize.return_value = []

    # Very short idle timeout: 0.1 seconds
    manager = OcrLifecycleManager(idle_unload_seconds=0.1, custom_backend=mock_backend)
    manager.run_ocr(b"BM_TEST")
    assert manager.state == OcrLifecycleState.WARM

    # Wait for idle timeout to trigger unload
    time.sleep(0.25)
    assert manager.state == OcrLifecycleState.COLD


def test_ocr_lifecycle_shutdown() -> None:
    mock_backend = MagicMock()
    manager = OcrLifecycleManager(idle_unload_seconds=5.0, custom_backend=mock_backend)
    manager.run_ocr(b"BM_TEST")
    assert manager.state == OcrLifecycleState.WARM

    manager.shutdown()
    assert manager.state == OcrLifecycleState.COLD


def test_ocr_lifecycle_cancellation() -> None:
    mock_backend = MagicMock()
    manager = OcrLifecycleManager(custom_backend=mock_backend)

    token = CancellationToken()
    token.cancel()

    with pytest.raises(TaskCancelledError):
        manager.run_ocr(b"BM_TEST", cancellation_token=token)
