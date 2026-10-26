"""Timing criteria used by the physical P14 C-02 microphone acceptance."""

from __future__ import annotations

import struct

from pluma.voice.vad import EnergyVAD
from tests.windows.p14_voice_boundary_acceptance import (
    BOUNDARY_TIMING_TOLERANCE_MS,
    _boundary_error_ms,
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


def test_boundary_timing_accepts_configured_stop_and_rejects_early_stop() -> None:
    expected_boundary_ms = 4500
    pre_playback_ms = 200
    expected_capture_ms = pre_playback_ms + expected_boundary_ms
    measured_error = _boundary_error_ms(
        expected_capture_ms, pre_playback_ms, expected_boundary_ms
    )
    early_error = _boundary_error_ms(
        expected_capture_ms - 1000, pre_playback_ms, expected_boundary_ms
    )

    assert abs(measured_error) <= BOUNDARY_TIMING_TOLERANCE_MS
    assert abs(early_error) > BOUNDARY_TIMING_TOLERANCE_MS
