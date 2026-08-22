"""pluma.voice.stt_adapter — Speech-to-text adapter for whisper.cpp.

Spec §7.1: whisper.cpp local STT.
PLUMA_TECH_STACK.md: whisper.cpp, quantized local Whisper model.
Boundary: Zero whisper or ML bindings imported at module level.
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    """Outcome of transcribing an audio buffer."""
    text: str
    confidence: float = 1.0
    language: str = "en"
    is_low_confidence: bool = False
    segments: List[Dict[str, Any]] = field(default_factory=list)


class WhisperSttAdapter:
    """Adapter for whisper.cpp local STT engine with on-demand lifecycle."""

    def __init__(self, low_confidence_threshold: float = 0.65) -> None:
        self.low_confidence_threshold = low_confidence_threshold
        self._model: Any = None
        self._model_path: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        """Return True if model is currently loaded in memory."""
        with self._lock:
            return self._model is not None

    def load(self, model_path: str, cancellation_token: Optional[Any] = None) -> None:
        """Load local Whisper GGML model on demand."""
        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            logger.debug("Model load aborted due to cancellation.")
            return

        with self._lock:
            if self._model is not None and self._model_path == model_path:
                return

            if not os.path.exists(model_path):
                raise FileNotFoundError(
                    f"Whisper model file not found at '{model_path}'. "
                    f"Set voice.stt_model_path in config to a valid GGML model."
                )

            try:
                # Lazy import of pywhispercpp inside load method
                from pywhispercpp.model import Model  # type: ignore[import-not-found,import-untyped]
                
                logger.info("Loading Whisper model from '%s'...", model_path)
                self._model = Model(model_path, n_threads=max(1, (os.cpu_count() or 4) // 2))
                self._model_path = model_path
                logger.info("Whisper model loaded successfully.")
            except ImportError:
                raise ImportError(
                    "pywhispercpp is not installed. Install pywhispercpp to enable local speech-to-text."
                )

    def unload(self) -> None:
        """Unload model from memory to restore idle zero-footprint."""
        with self._lock:
            if self._model is not None:
                logger.info("Unloading Whisper model to restore idle state.")
                self._model = None
                self._model_path = None

    def transcribe(
        self,
        audio: bytes,
        sample_rate: int = 16000,
        cancellation_token: Optional[Any] = None,
    ) -> TranscriptResult:
        """Transcribe raw 16-bit 16kHz PCM audio bytes."""
        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            logger.debug("Transcription aborted due to cancellation.")
            return TranscriptResult(text="", confidence=0.0, is_low_confidence=True)

        if not audio or len(audio) < 320:  # < 10ms
            return TranscriptResult(text="", confidence=1.0)

        with self._lock:
            if self._model is None:
                raise RuntimeError("Whisper model is not loaded. Call load() before transcribe().")
            model = self._model

        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            return TranscriptResult(text="", confidence=0.0, is_low_confidence=True)

        try:
            # Convert 16-bit PCM bytes to float32 numpy array normalized to [-1.0, 1.0]
            import numpy as np
            samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0

            # Execute transcription through pywhispercpp
            segments_out: List[Dict[str, Any]] = []
            transcript_parts: List[str] = []
            probs: List[float] = []

            whisper_segments = model.transcribe(samples, language="en")
            for seg in whisper_segments:
                seg_text = getattr(seg, "text", "")
                transcript_parts.append(seg_text)
                prob = getattr(seg, "probability", 1.0)
                probs.append(prob)
                segments_out.append({
                    "text": seg_text,
                    "t0": getattr(seg, "t0", 0),
                    "t1": getattr(seg, "t1", 0),
                    "probability": prob,
                })

            full_text = " ".join(t.strip() for t in transcript_parts if t.strip())
            avg_prob = sum(probs) / len(probs) if probs else 1.0
            is_low = avg_prob < self.low_confidence_threshold

            return TranscriptResult(
                text=full_text,
                confidence=avg_prob,
                language="en",
                is_low_confidence=is_low,
                segments=segments_out,
            )
        except Exception as exc:
            logger.error("Whisper transcription failed: %s", exc)
            raise
