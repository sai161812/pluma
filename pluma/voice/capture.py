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
        vad: Optional[Any] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration_s = max_duration_s
        self.max_buffer_bytes = int(sample_rate * channels * 2 * max_duration_s)
        self._buffer = bytearray()
        self._vad_pending = bytearray()
        self._lock = threading.Lock()
        self._operation = threading.RLock()
        self._generation = 0
        self._stream: Any = None
        self._is_recording = False
        self._utterance_complete = threading.Event()
        detector_factory = getattr(vad, "streaming_detector", None)
        self._boundary_detector = detector_factory() if callable(detector_factory) else None

    @property
    def is_recording(self) -> bool:
        """Return True if capture is currently active."""
        with self._lock:
            return self._is_recording

    @property
    def capture_closed(self) -> bool:
        with self._lock:
            return (self._stream is None and not self._is_recording
                    and not self._buffer and not self._vad_pending)

    @property
    def utterance_complete(self) -> bool:
        """Whether the stream stopped at its configured VAD silence boundary."""
        return self._utterance_complete.is_set()

    def _append_audio_locked(self, chunk: bytes) -> bool:
        """Append bounded audio; return true when the stream must stop now."""
        if not self._is_recording or not chunk:
            return False
        detector = self._boundary_detector
        if detector is None:
            remaining = self.max_buffer_bytes - len(self._buffer)
            if remaining > 0:
                self._buffer.extend(chunk[:remaining])
            return False

        self._vad_pending.extend(chunk)
        frame_bytes = detector.bytes_per_frame
        if frame_bytes <= 0:
            raise RuntimeError("VAD frame size is invalid.")
        while len(self._vad_pending) >= frame_bytes:
            frame = bytes(self._vad_pending[:frame_bytes])
            del self._vad_pending[:frame_bytes]
            if len(self._buffer) + frame_bytes > self.max_buffer_bytes:
                self._is_recording = False
                return True
            self._buffer.extend(frame)
            if detector.consume_frame(frame):
                self._is_recording = False
                self._utterance_complete.set()
                self._vad_pending.clear()
                return True
        return False

    @_serialized
    def start(self) -> None:
        """Start microphone capture stream."""
        with self._lock:
            if self._is_recording:
                return
            if self._stream is not None:
                raise RuntimeError("Previous capture stream remains owned.")
            self._buffer.clear()
            self._vad_pending.clear()
            self._utterance_complete.clear()
            if self._boundary_detector is not None:
                self._boundary_detector.reset()
            self._generation += 1
            generation = self._generation
            self._is_recording = True

        try:
            # Lazy import inside method to protect idle runtime footprint
            import sounddevice as sd  # type: ignore[import-not-found,import-untyped]

            def _callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
                if status:
                    logger.debug("Audio capture status: %s", status)
                chunk = (
                    indata
                    if isinstance(indata, bytes)
                    else indata.tobytes()
                    if hasattr(indata, "tobytes")
                    else bytes(indata)
                )
                reached_boundary = False
                with self._lock:
                    if self._is_recording and generation == self._generation:
                        reached_boundary = self._append_audio_locked(chunk)
                if reached_boundary:
                    callback_stop = getattr(sd, "CallbackStop", None)
                    if callback_stop is not None:
                        raise callback_stop

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
                self._vad_pending.clear()
            raise

    def feed(self, pcm_chunk: bytes) -> None:
        """Feed external PCM chunk into the capture buffer (used for testing or programmatic feed)."""
        with self._lock:
            self._append_audio_locked(pcm_chunk)

    @_serialized
    def cancel(self) -> None:
        """Discard transient audio and retain the stream on failed closure."""
        with self._lock:
            self._is_recording = False
            self._buffer.clear()
            self._vad_pending.clear()
            self._utterance_complete.clear()
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
                if (self._boundary_detector is not None and self._vad_pending
                        and not self._utterance_complete.is_set()):
                    remaining = self.max_buffer_bytes - len(self._buffer)
                    self._buffer.extend(self._vad_pending[:remaining])
                self._vad_pending.clear()
                captured = (b"" if cancellation_token is not None and cancellation_token.is_cancelled
                            else bytes(self._buffer))
                return captured
        finally:
            with self._lock:
                self._buffer.clear()
                self._vad_pending.clear()
