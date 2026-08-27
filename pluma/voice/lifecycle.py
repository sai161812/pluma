"""pluma.voice.lifecycle — On-demand warm/cold lifecycle manager for STT.

Spec §4, §7.1: "Start/map it when listening begins; keep it warm only briefly
if follow-up voice commands are likely." Unload after stt_idle_unload_seconds.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from pluma.voice.stt_adapter import TranscriptResult, WhisperSttAdapter

logger = logging.getLogger(__name__)


class VoiceLifecycleManager:
    """Manages on-demand loading, warm grace periods, and unloading of STT models."""

    def __init__(
        self,
        adapter: Optional[WhisperSttAdapter] = None,
        model_path: Optional[str] = None,
        idle_unload_seconds: float = 20.0,
    ) -> None:
        self.adapter = adapter or WhisperSttAdapter()
        self.model_path = model_path
        self.idle_unload_seconds = idle_unload_seconds

        self._state = "COLD"  # COLD | LOADING | WARM | TRANSCRIBING
        self._lock = threading.Lock()
        self._unload_timer: Optional[threading.Timer] = None

    @property
    def state(self) -> str:
        """Current lifecycle state."""
        with self._lock:
            return self._state

    @property
    def is_warm(self) -> bool:
        """Check if model is currently warm in memory."""
        return self.state == "WARM"

    def _cancel_unload_timer(self) -> None:
        """Cancel any scheduled idle unload timer."""
        if self._unload_timer is not None:
            self._unload_timer.cancel()
            self._unload_timer = None

    def _schedule_unload_timer(self) -> None:
        """Schedule automatic unload after idle_unload_seconds."""
        self._cancel_unload_timer()
        if self.idle_unload_seconds > 0:
            self._unload_timer = threading.Timer(
                self.idle_unload_seconds,
                self._on_idle_timeout,
            )
            self._unload_timer.daemon = True
            self._unload_timer.start()

    def _on_idle_timeout(self) -> None:
        """Handler for idle unload timeout."""
        logger.info("STT idle unload timeout reached (%0.1fs). Unloading model...", self.idle_unload_seconds)
        self.unload()

    def ensure_loaded(self, cancellation_token: Optional[Any] = None) -> None:
        """Ensure STT model is loaded into memory."""
        with self._lock:
            if self.adapter.is_loaded:
                return

            if not self.model_path:
                raise RuntimeError(
                    "voice.stt_model_path is not configured. "
                    "Set it to a valid Whisper GGML model file path."
                )

            self._state = "LOADING"

        try:
            self.adapter.load(self.model_path, cancellation_token=cancellation_token)
            with self._lock:
                self._state = "WARM"
        except Exception:
            with self._lock:
                self._state = "COLD"
            raise

    def transcribe(
        self,
        audio: bytes,
        sample_rate: int = 16000,
        cancellation_token: Optional[Any] = None,
    ) -> TranscriptResult:
        """Execute transcription, managing warm/cold lifecycle."""
        self._cancel_unload_timer()
        self.ensure_loaded(cancellation_token=cancellation_token)

        with self._lock:
            self._state = "TRANSCRIBING"

        try:
            result = self.adapter.transcribe(
                audio,
                sample_rate=sample_rate,
                cancellation_token=cancellation_token,
            )
            return result
        finally:
            with self._lock:
                if self.adapter.is_loaded:
                    self._state = "WARM"
                    self._schedule_unload_timer()
                else:
                    self._state = "COLD"

    def unload(self) -> None:
        """Unload STT model and return to COLD state."""
        with self._lock:
            self._cancel_unload_timer()
            self.adapter.unload()
            self._state = "COLD"

    def shutdown(self) -> None:
        """Shutdown lifecycle manager and release all timers and resources."""
        self.unload()
