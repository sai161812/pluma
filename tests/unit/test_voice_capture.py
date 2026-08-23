"""tests/unit/test_voice_capture.py — Phase 6: AudioCapture unit tests."""

from __future__ import annotations

import sys
import pytest

from pluma.core.cancellation import CancellationToken
from pluma.voice.capture import AudioCapture


def test_sounddevice_not_imported_at_module_level() -> None:
    """Verify that importing pluma.voice.capture does NOT import sounddevice."""
    # Ensure sounddevice was not imported
    import pluma.voice.capture
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
