"""tests/unit/test_perception_ocr_adapter.py — Phase 8: OcrAdapter unit tests."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock
import pytest

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import BoundingBox
from pluma.perception.ocr_adapter import OcrAdapter, OcrResult, OcrWord
from pluma.perception.ocr_adapter import _PaddleOcrBackend


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


def test_ocr_adapter_does_not_turn_recognition_errors_into_empty_text() -> None:
    mock_backend = MagicMock()
    mock_backend.recognize.side_effect = ValueError("bad image data")
    adapter = OcrAdapter(custom_backend=mock_backend)

    with pytest.raises(RuntimeError, match="OCR recognition failed: ValueError"):
        adapter.run(b"BM_DUMMY")


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


def test_paddle_backend_selects_locked_small_onnx_cpu_models(monkeypatch) -> None:
    """The production backend must not use Paddle's implicit engine/model defaults."""
    paddle_module = ModuleType("paddleocr")
    constructor = MagicMock(return_value=SimpleNamespace())
    paddle_module.PaddleOCR = constructor
    ort_module = ModuleType("onnxruntime")
    ort_module.get_available_providers = lambda: ["CPUExecutionProvider"]
    monkeypatch.setitem(sys.modules, "paddleocr", paddle_module)
    monkeypatch.setitem(sys.modules, "onnxruntime", ort_module)

    backend = _PaddleOcrBackend()
    backend.load()

    args = constructor.call_args.kwargs
    assert args["text_detection_model_name"] == "PP-OCRv6_small_det"
    assert args["text_recognition_model_name"] == "PP-OCRv6_small_rec"
    assert args["engine"] == "onnxruntime"
    assert args["device"] == "cpu"
    assert args["engine_config"]["onnxruntime"]["providers"] == ["CPUExecutionProvider"]
    assert args["use_doc_orientation_classify"] is False
    assert args["use_doc_unwarping"] is False
    assert args["use_textline_orientation"] is False


def test_paddle_backend_refuses_missing_cpu_provider(monkeypatch) -> None:
    """A missing CPU provider must fail closed before PaddleOCR initialization."""
    paddle_module = ModuleType("paddleocr")
    constructor = MagicMock()
    paddle_module.PaddleOCR = constructor
    ort_module = ModuleType("onnxruntime")
    ort_module.get_available_providers = lambda: ["CUDAExecutionProvider"]
    monkeypatch.setitem(sys.modules, "paddleocr", paddle_module)
    monkeypatch.setitem(sys.modules, "onnxruntime", ort_module)

    with pytest.raises(RuntimeError, match="CPU provider is unavailable"):
        _PaddleOcrBackend().load()

    constructor.assert_not_called()


def test_paddle_backend_parses_structured_results_without_persisting_images(monkeypatch) -> None:
    """PaddleOCR 3.x result objects become window-relative words in memory."""
    class FakeImage:
        size = (200, 100)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def convert(self, mode):
            assert mode == "RGB"
            return self

        def close(self):
            return None

    numpy_module = ModuleType("numpy")
    numpy_module.array = lambda value: ("array", value.size)
    pil_module = ModuleType("PIL")
    pil_module.Image = SimpleNamespace(open=lambda stream: FakeImage())
    monkeypatch.setitem(sys.modules, "numpy", numpy_module)
    monkeypatch.setitem(sys.modules, "PIL", pil_module)

    result = SimpleNamespace(json={"res": {
        "rec_texts": ["Save Changes", "Cancel"],
        "rec_scores": [0.97, 0.91],
        "rec_polys": [
            [[10, 20], [110, 20], [110, 50], [10, 50]],
            [[120, 20], [180, 20], [180, 50], [120, 50]],
        ],
    }}, save_to_img=MagicMock(), save_to_json=MagicMock())
    engine = SimpleNamespace(predict=MagicMock(return_value=[result]))
    backend = _PaddleOcrBackend()
    backend._ocr = engine

    words = backend.recognize(b"ephemeral-image-bytes")

    engine.predict.assert_called_once_with(("array", (200, 100)))
    assert [(word.text, word.confidence) for word in words] == [
        ("Save Changes", 0.97),
        ("Cancel", 0.91),
    ]
    assert words[0].bounds == BoundingBox(left=10, top=20, right=110, bottom=50)
    assert words[1].bounds == BoundingBox(left=120, top=20, right=180, bottom=50)
    result.save_to_img.assert_not_called()
    result.save_to_json.assert_not_called()


def test_paddle_backend_rejects_misaligned_result_fields(monkeypatch) -> None:
    """Malformed OCR arrays must be an error, not a partial or empty success."""
    class FakeImage:
        size = (200, 100)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def convert(self, _mode):
            return self

        def close(self):
            return None

    numpy_module = ModuleType("numpy")
    numpy_module.array = lambda value: value
    pil_module = ModuleType("PIL")
    pil_module.Image = SimpleNamespace(open=lambda _stream: FakeImage())
    monkeypatch.setitem(sys.modules, "numpy", numpy_module)
    monkeypatch.setitem(sys.modules, "PIL", pil_module)

    backend = _PaddleOcrBackend()
    backend._ocr = SimpleNamespace(predict=lambda _image: [SimpleNamespace(json={"res": {
        "rec_texts": ["Save"],
        "rec_scores": [],
        "rec_polys": [],
    }})])

    with pytest.raises(ValueError, match="counts differ"):
        backend.recognize(b"ephemeral-image-bytes")


def test_paddle_backend_refuses_bounds_outside_input_image(monkeypatch) -> None:
    """OCR coordinates outside the captured target crop must never ground input."""
    class FakeImage:
        size = (200, 100)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def convert(self, _mode):
            return self

        def close(self):
            return None

    numpy_module = ModuleType("numpy")
    numpy_module.array = lambda value: value
    pil_module = ModuleType("PIL")
    pil_module.Image = SimpleNamespace(open=lambda _stream: FakeImage())
    monkeypatch.setitem(sys.modules, "numpy", numpy_module)
    monkeypatch.setitem(sys.modules, "PIL", pil_module)

    backend = _PaddleOcrBackend()
    backend._ocr = SimpleNamespace(predict=lambda _image: [SimpleNamespace(json={"res": {
        "rec_texts": ["Outside"],
        "rec_scores": [0.95],
        "rec_polys": [[[199, 10], [205, 10], [205, 20], [199, 20]]],
    }})])

    with pytest.raises(ValueError, match="outside the input image"):
        backend.recognize(b"ephemeral-image-bytes")
