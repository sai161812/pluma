"""tests/unit/test_perception_ocr_adapter.py — Phase 8: OcrAdapter unit tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
import pytest

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import BoundingBox
from pluma.perception.ocr_adapter import OcrAdapter, OcrResult, OcrWord


def test_paddleocr_not_imported_at_module_level() -> None:
    """Verify that importing OCR modules does NOT import paddleocr or onnxruntime."""
    import pluma.perception.ocr_adapter
    import pluma.perception.ocr_lifecycle
    assert "paddleocr" not in sys.modules, "paddleocr must not be imported at module level"
    assert "onnxruntime" not in sys.modules, "onnxruntime must not be imported at module level"


def test_ocr_word_contains_text() -> None:
    word = OcrWord(
        text="Submit Order",
        confidence=0.95,
        bounds=BoundingBox(left=10, top=20, right=100, bottom=50),
    )
    assert word.contains_text("submit")
    assert word.contains_text("ORDER")
    assert not word.contains_text("cancel")
    assert word.contains_text("Submit", case_sensitive=True)
    assert not word.contains_text("submit", case_sensitive=True)


def test_ocr_result_find_words() -> None:
    w1 = OcrWord(text="Cancel", confidence=0.85, bounds=BoundingBox(left=10, top=10, right=50, bottom=30))
    w2 = OcrWord(text="Save Changes", confidence=0.45, bounds=BoundingBox(left=60, top=10, right=150, bottom=30))
    w3 = OcrWord(text="Save Draft", confidence=0.92, bounds=BoundingBox(left=160, top=10, right=240, bottom=30))

    res = OcrResult(words=[w1, w2, w3], full_text="Cancel Save Changes Save Draft", duration_ms=15.0)

    assert len(res.find_words("Save")) == 2
    # Filter by confidence
    assert len(res.find_words("Save", min_confidence=0.8)) == 1
    assert res.find_words("Save", min_confidence=0.8)[0].text == "Save Draft"
    assert len(res.find_words("NonExistent")) == 0


def test_ocr_adapter_custom_backend() -> None:
    mock_backend = MagicMock()
    mock_backend.recognize.return_value = [
        OcrWord(text="OK", confidence=0.99, bounds=BoundingBox(left=100, top=200, right=150, bottom=230))
    ]

    adapter = OcrAdapter(custom_backend=mock_backend)
    assert adapter.is_loaded

    dummy_bytes = b"BM_DUMMY"
    result = adapter.run(dummy_bytes)

    assert isinstance(result, OcrResult)
    assert len(result.words) == 1
    assert result.words[0].text == "OK"
    assert result.full_text == "OK"
    mock_backend.recognize.assert_called_once_with(dummy_bytes)


def test_ocr_adapter_cancellation_token() -> None:
    mock_backend = MagicMock()
    adapter = OcrAdapter(custom_backend=mock_backend)

    token = CancellationToken()
    token.cancel()

    with pytest.raises(TaskCancelledError):
        adapter.run(b"BM_DUMMY", cancellation_token=token)

    mock_backend.recognize.assert_not_called()


def test_ocr_adapter_not_loaded_raises_error() -> None:
    adapter = OcrAdapter()
    assert not adapter.is_loaded
    with pytest.raises(RuntimeError, match="not loaded"):
        adapter.run(b"BM_DUMMY")
