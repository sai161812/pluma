"""tests/unit/test_ocr_grounding_integration.py — Phase 8: OCR grounding & click_ocr_text tool tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from pluma.adapters.base import Rect
from pluma.perception.context import ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement
from pluma.perception.ocr_adapter import OcrResult, OcrWord
from pluma.tools.ui import (
    ALL_UI_TOOLS,
    CLICK_OCR_TEXT_SPEC,
    ClickOcrTextArgs,
    execute_click_ocr_text,
)


def test_click_ocr_text_spec_registration() -> None:
    assert CLICK_OCR_TEXT_SPEC.name == "click_ocr_text"
    assert CLICK_OCR_TEXT_SPEC in ALL_UI_TOOLS
    assert CLICK_OCR_TEXT_SPEC.cancellable


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_execute_click_ocr_text_success(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500,
        process_name="custom_app.exe",
        window_title="Custom Dashboard",
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
        is_valid=True,
    )
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(
        words=[
            OcrWord(
                text="Export Report",
                confidence=0.96,
                bounds=BoundingBox(left=200, top=300, right=300, bottom=340),
            )
        ]
    )

    result = execute_click_ocr_text({"text": "Export Report"})

    assert result.ok
    assert "Export Report" in result.factual_message
    assert result.data["matched_text"] == "Export Report"
    assert result.data["confidence"] == 0.96

    # Center of word: x = (200+300)//2 = 250, y = (300+340)//2 = 320
    # Desktop coordinates: desktop_x = 100 + 250 = 350, desktop_y = 100 + 320 = 420
    assert result.data["window_rel_x"] == 250
    assert result.data["window_rel_y"] == 320
    assert result.data["desktop_x"] == 350
    assert result.data["desktop_y"] == 420

    mock_mouse_click.assert_called_once_with(350, 420)


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
def test_execute_click_ocr_text_no_match(
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, rect=BoundingBox(left=0, top=0, right=800, bottom=600)
    )
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(words=[])

    result = execute_click_ocr_text({"text": "NonExistentText", "hwnd": 500})
    assert not result.ok
    assert result.error == "OCR_NO_MATCH"
    assert "no text matching" in result.factual_message


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_window")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
def test_execute_click_ocr_text_ambiguous_duplicate_labels(
    mock_run_ocr: MagicMock,
    mock_capture_window: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500, is_valid=True, rect=BoundingBox(left=0, top=0, right=800, bottom=600)
    )
    mock_context_cls.return_value = mock_context

    mock_capture_window.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(
        words=[
            OcrWord(text="Delete Item 1", confidence=0.9, bounds=BoundingBox(left=10, top=10, right=50, bottom=30)),
            OcrWord(text="Delete Item 2", confidence=0.9, bounds=BoundingBox(left=10, top=60, right=50, bottom=80)),
        ]
    )

    # Search for "Delete" which matches both words -> should reject ambiguity
    result = execute_click_ocr_text({"text": "Delete", "hwnd": 500})
    assert not result.ok
    assert result.error == "OCR_AMBIGUOUS"
    assert "Ambiguous OCR result" in result.factual_message


@patch("pluma.tools.ui.ActiveWindowContext")
@patch("pluma.perception.capture.WindowCapture.capture_region")
@patch("pluma.perception.ocr_lifecycle.OcrLifecycleManager.run_ocr")
@patch("pluma.adapters.input.InputAdapter.mouse_click")
def test_execute_click_ocr_text_with_region_offset(
    mock_mouse_click: MagicMock,
    mock_run_ocr: MagicMock,
    mock_capture_region: MagicMock,
    mock_context_cls: MagicMock,
) -> None:
    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=500,
        rect=BoundingBox(left=100, top=100, right=900, bottom=700),
        is_valid=True,
    )
    mock_context_cls.return_value = mock_context

    mock_capture_region.return_value = b"BM_BYTES"
    mock_run_ocr.return_value = OcrResult(
        words=[
            OcrWord(
                text="Apply",
                confidence=0.99,
                bounds=BoundingBox(left=10, top=20, right=50, bottom=40),
            )
        ]
    )

    # Sub-region at window-rel (50, 100, 300, 400)
    region_arg = {"left": 50, "top": 100, "right": 300, "bottom": 400}
    result = execute_click_ocr_text({"text": "Apply", "region": region_arg})

    assert result.ok
    # Word center inside region: x = (10+50)//2 = 30, y = (20+40)//2 = 30
    # Region offset: left=50, top=100 -> Window-relative: x = 30+50 = 80, y = 30+100 = 130
    # Desktop absolute: 100+80 = 180, 100+130 = 230
    assert result.data["window_rel_x"] == 80
    assert result.data["window_rel_y"] == 130
    assert result.data["desktop_x"] == 180
    assert result.data["desktop_y"] == 230
    mock_mouse_click.assert_called_once_with(180, 230)


def test_uia_snapshot_builder_with_ocr_fallback() -> None:
    from pluma.perception.uia_snapshot import UiaSnapshotBuilder
    from pluma.perception.element_refs import ElementSource

    mock_context = MagicMock()
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=101,
        process_name="graphic_app.exe",
        window_title="Canvas Editor",
        rect=BoundingBox(left=0, top=0, right=1000, bottom=800),
        dpi_scale=1.0,
        is_valid=True,
    )

    mock_capture = MagicMock()
    mock_capture.capture_window.return_value = b"BM_BYTES"

    mock_ocr = MagicMock()
    mock_ocr.run_ocr.return_value = OcrResult(
        words=[
            OcrWord(text="Layers", confidence=0.91, bounds=BoundingBox(left=10, top=10, right=80, bottom=30))
        ]
    )

    builder = UiaSnapshotBuilder(context=mock_context, custom_extractor=lambda hwnd: [])
    snapshot = builder.capture(
        hwnd=101,
        include_ocr=True,
        window_capture=mock_capture,
        ocr_manager=mock_ocr,
    )

    assert len(snapshot.controls) == 0
    assert len(snapshot.ocr_words) == 1
    assert snapshot.ocr_words[0].label == "Layers"
    assert snapshot.ocr_words[0].source == ElementSource.OCR
    assert snapshot.ocr_words[0].confidence == 0.91
