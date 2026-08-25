"""tests/unit/test_verify_ocr.py — Phase 8: OCR postcondition verification tests."""

from __future__ import annotations

from unittest.mock import MagicMock
import pytest

from pluma.adapters.base import Rect
from pluma.perception.capture import WindowCapture
from pluma.perception.element_refs import BoundingBox
from pluma.perception.ocr_adapter import OcrResult, OcrWord
from pluma.perception.ocr_lifecycle import OcrLifecycleManager
from pluma.verify.screen import ScreenVerifier


def test_verify_ocr_text_present_success() -> None:
    mock_capture = MagicMock(spec=WindowCapture)
    mock_capture.capture_window.return_value = b"BM_IMG"

    mock_ocr = MagicMock(spec=OcrLifecycleManager)
    mock_ocr.run_ocr.return_value = OcrResult(
        words=[
            OcrWord(
                text="Order Completed Successfully",
                confidence=0.98,
                bounds=BoundingBox(left=100, top=200, right=400, bottom=240),
            )
        ]
    )

    verifier = ScreenVerifier()
    v_res = verifier.verify_ocr_text_present(
        hwnd=123,
        expected_text="Completed",
        ocr_manager=mock_ocr,
        capture=mock_capture,
    )

    assert v_res.ok
    assert v_res.method == "ocr"
    assert "OCR verified text 'Completed' present" in v_res.detail


def test_verify_ocr_text_present_not_found() -> None:
    mock_capture = MagicMock(spec=WindowCapture)
    mock_capture.capture_window.return_value = b"BM_IMG"

    mock_ocr = MagicMock(spec=OcrLifecycleManager)
    mock_ocr.run_ocr.return_value = OcrResult(words=[])

    verifier = ScreenVerifier()
    v_res = verifier.verify_ocr_text_present(
        hwnd=123,
        expected_text="Completed",
        ocr_manager=mock_ocr,
        capture=mock_capture,
    )

    assert not v_res.ok
    assert v_res.method == "ocr"
    assert "not found" in v_res.detail


def test_verify_ocr_text_absent_success() -> None:
    mock_capture = MagicMock(spec=WindowCapture)
    mock_capture.capture_window.return_value = b"BM_IMG"

    mock_ocr = MagicMock(spec=OcrLifecycleManager)
    mock_ocr.run_ocr.return_value = OcrResult(
        words=[OcrWord(text="Home Page", confidence=0.95, bounds=BoundingBox(left=10, top=10, right=100, bottom=30))]
    )

    verifier = ScreenVerifier()
    v_res = verifier.verify_ocr_text_absent(
        hwnd=123,
        absent_text="Error Dialog",
        ocr_manager=mock_ocr,
        capture=mock_capture,
    )

    assert v_res.ok
    assert v_res.method == "ocr"
    assert "is absent" in v_res.detail


def test_verify_ocr_text_absent_still_present() -> None:
    mock_capture = MagicMock(spec=WindowCapture)
    mock_capture.capture_window.return_value = b"BM_IMG"

    mock_ocr = MagicMock(spec=OcrLifecycleManager)
    mock_ocr.run_ocr.return_value = OcrResult(
        words=[
            OcrWord(
                text="Critical Error Dialog",
                confidence=0.97,
                bounds=BoundingBox(left=100, top=100, right=300, bottom=150),
            )
        ]
    )

    verifier = ScreenVerifier()
    v_res = verifier.verify_ocr_text_absent(
        hwnd=123,
        absent_text="Error Dialog",
        ocr_manager=mock_ocr,
        capture=mock_capture,
    )

    assert not v_res.ok
    assert v_res.method == "ocr"
    assert "unexpected text 'Error Dialog' still present" in v_res.detail
