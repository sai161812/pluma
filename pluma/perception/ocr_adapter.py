"""pluma.perception.ocr_adapter — On-demand OCR worker with PaddleOCR/ONNX Runtime.

Spec §8.3: "Use an on-demand local OCR worker. A practical baseline is a
lightweight PaddleOCR/ONNX Runtime configuration using tiny/small text
detection and recognition models."

Architecture constraints:
- paddleocr and onnxruntime must NEVER be imported at module level.
  All heavy imports are inside method bodies only.
- OCR images are passed in as ephemeral bytes; the adapter never creates
  or reads files from disk.
- The adapter supports dependency injection of a mock recognition backend
  for deterministic CI and headless unit test execution.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import BoundingBox

logger = logging.getLogger(__name__)

_PADDLEOCR_DETECTION_MODEL = "PP-OCRv6_small_det"
_PADDLEOCR_RECOGNITION_MODEL = "PP-OCRv6_small_rec"
_ONNX_CPU_PROVIDERS = ["CPUExecutionProvider"]
ACTION_OCR_MIN_CONFIDENCE = 0.9


# ---------------------------------------------------------------------------
# Output data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OcrWord:
    """One text token detected by the OCR engine.

    Bounds are window-relative (or region-relative) BoundingBox pixels.
    Confidence is in [0.0, 1.0].
    """
    text: str
    confidence: float
    bounds: BoundingBox

    def contains_text(self, query: str, case_sensitive: bool = False, exact_match: bool = False) -> bool:
        """Return True if this word matches *query* as a whole word or exact token."""
        import re
        src = self.text if case_sensitive else self.text.lower()
        q = query if case_sensitive else query.lower()
        if exact_match or len(q.strip()) <= 3:
            return src.strip() == q.strip()
        # Word boundary regex: "OK" will NOT match "BOOK"
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = r"\b" + re.escape(q.strip()) + r"\b"
        return bool(re.search(pattern, self.text, flags=flags))


@dataclass
class OcrResult:
    """Result from a single OCR run."""
    words: List[OcrWord] = field(default_factory=list)
    full_text: str = ""
    duration_ms: float = 0.0

    @property
    def is_empty(self) -> bool:
        return len(self.words) == 0

    def find_words(
        self,
        query: str,
        min_confidence: float = 0.0,
        case_sensitive: bool = False,
        exact_match: bool = False,
    ) -> List[OcrWord]:
        """Return all words matching *query* at or above *min_confidence* with word-boundary protection."""
        return [
            w for w in self.words
            if w.contains_text(query, case_sensitive=case_sensitive, exact_match=exact_match)
            and w.confidence >= min_confidence
        ]


# ---------------------------------------------------------------------------
# OCR recognition backend protocol (for dependency injection)
# ---------------------------------------------------------------------------

class OcrBackend(Protocol):
    """Protocol for an OCR recognition backend."""

    def recognize(self, image_bytes: bytes) -> List[OcrWord]:
        """Recognize text in *image_bytes* and return detected words."""
        ...


# ---------------------------------------------------------------------------
# PaddleOCR Backend — lazy-loaded
# ---------------------------------------------------------------------------

class _PaddleOcrBackend:
    """PaddleOCR/ONNX Runtime backend loaded lazily inside method bodies."""

    def __init__(self) -> None:
        self._ocr: Optional[Any] = None

    def load(self) -> None:
        """Load the PaddleOCR model. Called explicitly by OcrLifecycleManager."""
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]

            if "CPUExecutionProvider" not in ort.get_available_providers():
                raise RuntimeError("ONNX Runtime CPU provider is unavailable.")

            from paddleocr import PaddleOCR  # type: ignore[import-not-found]

            # Keep the OCR engine explicit, local and CPU-only. These small
            # PP-OCRv6 models are selected for rendered screen text; no
            # document-orientation or unwarping models are needed for a window
            # crop. Runtime imports and model loading remain on-demand.
            self._ocr = PaddleOCR(
                text_detection_model_name=_PADDLEOCR_DETECTION_MODEL,
                text_recognition_model_name=_PADDLEOCR_RECOGNITION_MODEL,
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device="cpu",
                engine="onnxruntime",
                engine_config={
                    "onnxruntime": {
                        "device_type": "cpu",
                        "providers": list(_ONNX_CPU_PROVIDERS),
                        "intra_op_num_threads": 2,
                        "inter_op_num_threads": 1,
                        "execution_mode": "sequential",
                    }
                },
            )
            logger.info(
                "PaddleOCR loaded with %s/%s through ONNX Runtime CPU.",
                _PADDLEOCR_DETECTION_MODEL,
                _PADDLEOCR_RECOGNITION_MODEL,
            )
        except ImportError as exc:
            logger.error(
                "PaddleOCR/ONNX Runtime is not installed. "
                "Install the optional runtime with: pip install 'pluma[ocr]'"
            )
            raise ImportError(
                "PaddleOCR/ONNX Runtime is required for OCR. "
                "Install the optional runtime with: pip install 'pluma[ocr]'"
            ) from exc

    def unload(self) -> None:
        """Release the PaddleOCR model from memory."""
        self._ocr = None
        logger.info("PaddleOCR engine unloaded.")

    def recognize(self, image_bytes: bytes) -> List[OcrWord]:
        """Run text detection and recognition on *image_bytes*."""
        if self._ocr is None:
            raise RuntimeError("PaddleOCR backend is not loaded. Call load() first.")

        import io
        import numpy as np  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]

        # Decode only the in-memory target crop. PaddleOCR's result-saving APIs
        # are intentionally not called, so neither the input nor a rendering
        # of the result is written to disk.
        with Image.open(io.BytesIO(image_bytes)) as source:
            rgb_image = source.convert("RGB")
            try:
                image_width, image_height = rgb_image.size
                # PaddleX's ndarray reader expects OpenCV BGR. Preserve color
                # channels correctly for colored labels and antialiased text.
                img_array = np.array(rgb_image)[:, :, ::-1].copy()
            finally:
                rgb_image.close()

        results = self._ocr.predict(img_array)
        words: List[OcrWord] = []

        if results is None:
            return words

        if not isinstance(results, (list, tuple)):
            results = [results]

        for result in results:
            result_json = getattr(result, "json", None)
            if callable(result_json):
                result_json = result_json()
            if not isinstance(result_json, dict):
                raise ValueError("PaddleOCR returned an unsupported result object.")

            payload = result_json.get("res", result_json)
            if not isinstance(payload, dict):
                raise ValueError("PaddleOCR returned an invalid result payload.")

            texts = self._as_list(payload.get("rec_texts"))
            scores = self._as_list(payload.get("rec_scores"))
            polygons = self._as_list(payload.get("rec_polys"))
            boxes = self._as_list(payload.get("rec_boxes"))
            if not polygons and boxes:
                polygons = boxes

            if not texts and not scores and not polygons:
                continue
            if not (len(texts) == len(scores) == len(polygons)):
                raise ValueError("PaddleOCR result text, score and bounds counts differ.")

            for text, score, coordinates in zip(texts, scores, polygons):
                text = str(text).strip()
                confidence = float(score)
                if not text:
                    continue
                if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                    raise ValueError("PaddleOCR returned an invalid confidence score.")

                coordinates = self._as_list(coordinates)
                if len(coordinates) == 4 and all(
                    not isinstance(value, (list, tuple)) and not hasattr(value, "__len__")
                    for value in coordinates
                ):
                    xs = [float(coordinates[0]), float(coordinates[2])]
                    ys = [float(coordinates[1]), float(coordinates[3])]
                else:
                    points = [self._as_list(point) for point in coordinates]
                    if len(points) < 3 or any(len(point) < 2 for point in points):
                        raise ValueError("PaddleOCR returned invalid text bounds.")
                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]

                if not all(math.isfinite(value) for value in xs + ys):
                    raise ValueError("PaddleOCR returned non-finite text bounds.")
                left, top = math.floor(min(xs)), math.floor(min(ys))
                right, bottom = math.ceil(max(xs)), math.ceil(max(ys))
                if right <= left or bottom <= top:
                    continue
                if left < 0 or top < 0 or right > image_width or bottom > image_height:
                    raise ValueError("PaddleOCR returned text bounds outside the input image.")

                words.append(OcrWord(
                    text=text,
                    confidence=confidence,
                    bounds=BoundingBox(
                        left=left,
                        top=top,
                        right=right,
                        bottom=bottom,
                    ),
                ))

        return words

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        """Convert PaddleOCR/NumPy result arrays into ordinary Python lists."""
        if value is None:
            return []
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            value = tolist()
        if isinstance(value, (str, bytes)):
            raise ValueError("PaddleOCR returned an invalid sequence field.")
        try:
            return list(value)
        except TypeError as exc:
            raise ValueError("PaddleOCR returned an invalid sequence field.") from exc


# ---------------------------------------------------------------------------
# OcrAdapter — orchestrates capture → recognition → OcrResult
# ---------------------------------------------------------------------------

class OcrAdapter:
    """On-demand OCR adapter. Lazy-loads PaddleOCR/ONNX only when needed.

    Usage:
        adapter = OcrAdapter()
        adapter.load()
        result = adapter.run(bmp_bytes)
        adapter.unload()

    For testing: inject a mock backend via *custom_backend*.
    """

    def __init__(
        self,
        custom_backend: Optional[OcrBackend] = None,
    ) -> None:
        self._backend: Optional[Any] = custom_backend
        self._owned_backend: Optional[_PaddleOcrBackend] = None

    @property
    def is_loaded(self) -> bool:
        """True if the OCR backend is currently loaded and ready."""
        if self._backend is not None:
            return True
        return self._owned_backend is not None and self._owned_backend._ocr is not None

    def load(self) -> None:
        """Load the OCR backend. No-op if a custom backend is injected."""
        if self._backend is not None:
            return  # Custom backend manages its own lifecycle
        if self._owned_backend is None:
            self._owned_backend = _PaddleOcrBackend()
        self._owned_backend.load()

    def unload(self) -> None:
        """Unload the OCR backend to free memory. No-op if using custom backend."""
        if self._backend is not None:
            return
        if self._owned_backend is not None:
            self._owned_backend.unload()
            self._owned_backend = None

    def run(
        self,
        image_bytes: bytes,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> OcrResult:
        """Run OCR recognition on the provided image bytes.

        Args:
            image_bytes: Ephemeral BMP/PNG image data. Discard after calling this.
            cancellation_token: If set, checks for cancellation before recognition.

        Returns:
            OcrResult with detected words, full text, and duration.

        Raises:
            TaskCancelledError: If the task is cancelled before OCR starts.
            RuntimeError: If OCR backend is not loaded.
        """
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

        active_backend = self._backend or self._owned_backend
        if active_backend is None:
            raise RuntimeError("OcrAdapter is not loaded. Call load() first.")

        start_ms = time.perf_counter()
        try:
            words = active_backend.recognize(image_bytes)
            # Backends such as PaddleOCR perform a synchronous native call.
            # The owning process worker supplies the hard cancellation bound;
            # this post-call check prevents any result or follow-up action from
            # proceeding when cancellation arrived during recognition.
            if cancellation_token is not None:
                cancellation_token.raise_if_cancelled()
        except TaskCancelledError:
            raise
        except Exception as exc:
            logger.warning("OCR recognition error: %s", exc)
            raise RuntimeError(f"OCR recognition failed: {type(exc).__name__}.") from exc

        duration_ms = (time.perf_counter() - start_ms) * 1000.0
        full_text = " ".join(w.text for w in words)

        result = OcrResult(
            words=words,
            full_text=full_text,
            duration_ms=round(duration_ms, 1),
        )
        logger.debug(
            "OCR completed: %d words, %.1f ms", len(words), duration_ms
        )
        return result
