"""Timing criteria used by the physical P14 C-02 microphone acceptance."""

from __future__ import annotations

import struct

from pluma.voice.vad import EnergyVAD
from tests.windows.p14_voice_boundary_acceptance import (
    BOUNDARY_EARLY_TOLERANCE_MS,
    BOUNDARY_LATE_TOLERANCE_MS,
    _boundary_error_ms,
    _boundary_timing_matches,
    _speech_profile,
)


def test_boundary_profile_finds_last_speech_and_internal_quiet_gap() -> None:
    vad = EnergyVAD()
    speech_frame = struct.pack("<480h", *([4000] * 480))
    silence_frame = b"\0" * vad.bytes_per_frame
    pcm = speech_frame * 12 + silence_frame * 2 + speech_frame * 4 + silence_frame * 25

    profile = _speech_profile(pcm, vad)

    assert profile["speech_active_start_ms"] == 0
    assert profile["speech_active_end_ms"] == 540
    assert profile["longest_internal_silence_ms"] == 60
    assert profile["tail_silence_ms"] == 750


def test_boundary_timing_rejects_stop_before_speech_end_and_bounds_device_delay() -> None:
    expected_boundary_ms = 4500
    pre_playback_ms = 200
    expected_capture_ms = pre_playback_ms + expected_boundary_ms
    measured_error = _boundary_error_ms(
        expected_capture_ms, pre_playback_ms, expected_boundary_ms
    )
    # Fixture speech ends at 3900 ms and trailing VAD silence is 600 ms. A
    # captured stop at 3800 ms is 100 ms before speech ends (error -700 ms).
    stop_before_speech_end_error = _boundary_error_ms(
        pre_playback_ms + 3800, pre_playback_ms, expected_boundary_ms
    )
    early_device_delay_error = -BOUNDARY_EARLY_TOLERANCE_MS
    late_device_delay_error = BOUNDARY_LATE_TOLERANCE_MS

    assert measured_error == 0
    assert stop_before_speech_end_error == -700
    assert not _boundary_timing_matches(stop_before_speech_end_error)
    assert _boundary_timing_matches(early_device_delay_error)
    assert _boundary_timing_matches(late_device_delay_error)
    assert not _boundary_timing_matches(-BOUNDARY_EARLY_TOLERANCE_MS - 1)
    assert not _boundary_timing_matches(BOUNDARY_LATE_TOLERANCE_MS + 1)
