"""pluma.voice.capture — Microphone capture interface.

Spec §7.1: Push-to-talk -> microphone capture -> VAD.
Uses sounddevice (or raw PCM streams) with lazy imports inside methods.
Zero audio libraries imported at module level.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class AudioCapture:
    """Microphone audio capture manager for 16-bit 16kHz mono PCM audio."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stream: Any = None
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """Return True if capture is currently active."""
        with self._lock:
            return self._is_recording

    def start(self) -> None:
        """Start microphone capture stream."""
        with self._lock:
            if self._is_recording:
                return
            self._buffer.clear()
            self._is_recording = True

        try:
            # Lazy import inside method to protect idle runtime footprint
            import sounddevice as sd  # type: ignore[import-not-found,import-untyped]

            def _callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
                if status:
                    logger.debug("Audio capture status: %s", status)
                with self._lock:
                    if self._is_recording:
                        if isinstance(indata, bytes):
                            self._buffer.extend(indata)
                        elif hasattr(indata, "tobytes"):
                            self._buffer.extend(indata.tobytes())
                        elif hasattr(indata, "tobytes") or isinstance(indata, (bytearray, memoryview)):
                            self._buffer.extend(bytes(indata))

            self._stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                callback=_callback,
            )
            self._stream.start()
            logger.debug("Microphone capture started (%d Hz, mono).", self.sample_rate)
        except ImportError:
            logger.warning("sounddevice is not installed. AudioCapture running in buffer-only mode.")
        except Exception as exc:
            logger.error("Failed to start sounddevice audio stream: %s", exc)
            with self._lock:
                self._is_recording = False
            raise

    def feed(self, pcm_chunk: bytes) -> None:
        """Feed external PCM chunk into the capture buffer (used for testing or programmatic feed)."""
        with self._lock:
            if self._is_recording:
                self._buffer.extend(pcm_chunk)

    def stop_and_get(self, cancellation_token: Optional[Any] = None) -> bytes:
        """Stop capture stream, return raw PCM bytes, and clear memory buffer."""
        with self._lock:
            self._is_recording = False

        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("Error closing audio stream: %s", exc)
            finally:
                self._stream = None

        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            logger.debug("Capture stopped due to cancellation; discarding buffer.")
            with self._lock:
                self._buffer.clear()
            return b""

        with self._lock:
            captured = bytes(self._buffer)
            self._buffer.clear()

        logger.debug("Captured %d bytes of PCM audio.", len(captured))
        return captured
