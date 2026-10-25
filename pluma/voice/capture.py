"""pluma.voice.capture — Microphone capture interface.

Spec §7.1: Push-to-talk -> microphone capture -> VAD.
Uses sounddevice (or raw PCM streams) with lazy imports inside methods.
Zero audio libraries imported at module level.
"""

from __future__ import annotations

import logging
import threading
from functools import wraps
from typing import Any, Optional

logger = logging.getLogger(__name__)


MAX_RECORDING_SECONDS: float = 30.0


def _serialized(method):
    @wraps(method)
    def run(self, *args, **kwargs):
        with self._operation:
            return method(self, *args, **kwargs)
    return run


class AudioCapture:
    """Microphone audio capture manager for 16-bit 16kHz mono PCM audio with bounded memory buffer."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        max_duration_s: float = MAX_RECORDING_SECONDS,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration_s = max_duration_s
        self.max_buffer_bytes = int(sample_rate * channels * 2 * max_duration_s)
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._operation = threading.RLock()
        self._generation = 0
        self._stream: Any = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Return True if capture is currently active."""
        with self._lock:
            return self._is_recording

    @property
    def capture_closed(self) -> bool:
        with self._lock:
            return self._stream is None and not self._is_recording and not self._buffer

    @_serialized
    def start(self) -> None:
        """Start microphone capture stream."""
        with self._lock:
            if self._is_recording:
                return
            if self._stream is not None:
                raise RuntimeError("Previous capture stream remains owned.")
            self._buffer.clear()
            self._generation += 1
            generation = self._generation
            self._is_recording = True

        try:
            # Lazy import inside method to protect idle runtime footprint
            import sounddevice as sd  # type: ignore[import-not-found,import-untyped]

            def _callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
                if status:
                    logger.debug("Audio capture status: %s", status)
                with self._lock:
                    if self._is_recording and generation == self._generation:
                        if len(self._buffer) >= self.max_buffer_bytes:
                            # Reached maximum duration limit — auto-cap buffer
                            return
                        chunk = (
                            indata
                            if isinstance(indata, bytes)
                            else indata.tobytes()
                            if hasattr(indata, "tobytes")
                            else bytes(indata)
                        )
                        remaining = self.max_buffer_bytes - len(self._buffer)
                        self._buffer.extend(chunk[:remaining])

            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=_callback,
            )
            self._stream.start()
            logger.debug("Microphone capture started (%d Hz, mono).", self.sample_rate)
        except Exception as exc:
            logger.warning("Microphone capture could not start.")
            with self._lock:
                self._is_recording = False
                self._buffer.clear()
            raise

    def feed(self, pcm_chunk: bytes) -> None:
        """Feed external PCM chunk into the capture buffer (used for testing or programmatic feed)."""
        with self._lock:
            if self._is_recording:
                remaining = self.max_buffer_bytes - len(self._buffer)
                if remaining > 0:
                    self._buffer.extend(pcm_chunk[:remaining])

    @_serialized
    def cancel(self) -> None:
        """Discard transient audio and retain the stream on failed closure."""
        with self._lock:
            self._is_recording = False
            self._buffer.clear()
            stream = self._stream
        if stream is not None:
            stream.abort()
            stream.close()
            if stream.closed is not True:
                raise RuntimeError("Capture stream closure is unverified.")
            with self._lock:
                if self._stream is stream:
                    self._stream = None

    @_serialized
    def stop_and_get(self, cancellation_token: Optional[Any] = None) -> bytes:
        """Return transient PCM only after positive stream-close readback."""
        with self._lock:
            self._is_recording = False
            stream = self._stream
        try:
            if stream is not None:
                stream.stop()
                stream.close()
                if stream.closed is not True:
                    raise RuntimeError("Capture stream closure is unverified.")
                with self._lock:
                    self._stream = None
            with self._lock:
                captured = (b"" if cancellation_token is not None and cancellation_token.is_cancelled
                            else bytes(self._buffer))
                return captured
        finally:
            with self._lock:
                self._buffer.clear()
