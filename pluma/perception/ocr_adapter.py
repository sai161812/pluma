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
import time
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Protocol

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.perception.element_refs import BoundingBox

logger = logging.getLogger(__name__)


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
            from paddleocr import PaddleOCR  # type: ignore[import-not-found]
            # Use lightweight det/rec models; lang='en' for lowest model size
            self._ocr = PaddleOCR(
                use_angle_cls=False,
                lang="en",
                show_log=False,
                use_gpu=False,
            )
            logger.info("PaddleOCR engine loaded.")
        except ImportError:
            logger.error(
                "paddleocr is not installed. Install it with: pip install paddleocr"
            )
            raise

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

        # Convert BMP bytes to numpy array for PaddleOCR
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_array = np.array(img)

        results = self._ocr.ocr(img_array, cls=False)
        words: List[OcrWord] = []

        if results is None or not results or results[0] is None:
            return words

        for line in results[0]:
            if not line:
                continue
            # PaddleOCR returns: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], (text, conf)
            polygon, (text, conf) = line
            if not text or conf < 0.0:
                continue

            # Compute axis-aligned bounding box from polygon points
            xs = [int(pt[0]) for pt in polygon]
            ys = [int(pt[1]) for pt in polygon]
            word = OcrWord(
                text=text,
                confidence=float(conf),
                bounds=BoundingBox(
                    left=min(xs),
                    top=min(ys),
                    right=max(xs),
                    bottom=max(ys),
                ),
            )
            words.append(word)

        return words


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
        except TaskCancelledError:
            raise
        except Exception as exc:
            logger.warning("OCR recognition error: %s", exc)
            words = []

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
