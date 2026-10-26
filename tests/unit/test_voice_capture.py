"""tests/unit/test_voice_capture.py — Phase 6: AudioCapture unit tests."""

from __future__ import annotations

import sys
import math
import struct
import pytest

from pluma.core.cancellation import CancellationToken
from pluma.voice.capture import AudioCapture


@pytest.fixture(autouse=True)
def inert_device(monkeypatch):
    # Explicit device seam: never depend on a missing library to avoid a mic.
    from types import SimpleNamespace
    class CallbackStop(Exception):
        pass
    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            self.closed = False
            self.callback_stopped = False
        def start(self): pass
        def stop(self): pass
        def abort(self): pass
        def close(self): self.closed = True
        def emit(self, chunk):
            try:
                self.callback(chunk, len(chunk) // 2, None, None)
            except CallbackStop:
                self.callback_stopped = True
    monkeypatch.setitem(sys.modules, "sounddevice", SimpleNamespace(
        CallbackStop=CallbackStop,
        RawInputStream=lambda **kw: Stream(**kw),
    ))


def _tone_frames(frame_count: int, amplitude: int = 6000) -> bytes:
    frame_samples = 16000 * 30 // 1000
    count = frame_count * frame_samples
    samples = [int(amplitude * math.sin(2 * math.pi * 440 * i / 16000)) for i in range(count)]
    return struct.pack(f"<{count}h", *samples)


def test_sounddevice_not_imported_at_module_level(monkeypatch) -> None:
    """Verify that importing pluma.voice.capture does NOT import sounddevice."""
    # A fresh import must not pull in the lazy device dependency.
    import importlib
    monkeypatch.delitem(sys.modules, "sounddevice")
    import pluma.voice.capture
    importlib.reload(pluma.voice.capture)
    assert "sounddevice" not in sys.modules, "sounddevice must not be imported at module level"


def test_capture_start_feed_stop_returns_bytes() -> None:
    capture = AudioCapture(sample_rate=16000)
    capture.start()
    assert capture.is_recording

    chunk1 = b"\x01\x00" * 100
    chunk2 = b"\x02\x00" * 100
    capture.feed(chunk1)
    capture.feed(chunk2)

    result = capture.stop_and_get()
    assert not capture.is_recording
    assert result == (chunk1 + chunk2)

    # Next call should return empty since buffer was cleared
    assert capture.stop_and_get() == b""


def test_capture_cancelled_before_stop_returns_empty() -> None:
    capture = AudioCapture(sample_rate=16000)
    token = CancellationToken()
    capture.start()
    capture.feed(b"\x05\x00" * 500)

    token.cancel()
    result = capture.stop_and_get(cancellation_token=token)
    assert result == b""
    assert not capture.is_recording


def test_configured_vad_boundary_stops_stream_and_excludes_later_frames() -> None:
    from pluma.voice.vad import EnergyVAD

    vad = EnergyVAD(
        energy_threshold=300.0,
        min_speech_duration_ms=120,
        trailing_silence_ms=180,
    )
    capture = AudioCapture(vad=vad)
    capture.start()
    stream = capture._stream
    assert stream is not None

    # Four speech frames plus the configured six trailing-silence frames end
    # capture. Speech arriving in the same later callback must not be retained.
    ending_audio = _tone_frames(4) + b"\0\0" * (6 * 16000 * 30 // 1000)
    stream.emit(ending_audio + _tone_frames(4))

    assert stream.callback_stopped
    assert capture.utterance_complete
    assert not capture.is_recording
    result = capture.stop_and_get()
    assert result == ending_audio
    assert capture.capture_closed


def test_vad_boundary_waits_for_minimum_speech_and_trailing_silence() -> None:
    from pluma.voice.vad import EnergyVAD

    vad = EnergyVAD(
        energy_threshold=300.0,
        min_speech_duration_ms=120,
        trailing_silence_ms=180,
    )
    capture = AudioCapture(vad=vad)
    capture.start()
    stream = capture._stream
    assert stream is not None

    stream.emit(b"\0\0" * (2 * 16000 * 30 // 1000))
    assert capture.is_recording
    stream.emit(_tone_frames(4) + b"\0\0" * (5 * 16000 * 30 // 1000))
    assert capture.is_recording
    assert not capture.utterance_complete
    stream.emit(b"\0\0" * (16000 * 30 // 1000))
    assert stream.callback_stopped
    assert capture.utterance_complete
    capture.cancel()
    assert capture.capture_closed
