"""tests/unit/test_voice_vad.py — Phase 6: EnergyVAD unit tests."""

from __future__ import annotations

import math
import struct
import pytest

from pluma.voice.vad import EnergyVAD


def _make_pcm_tone(duration_ms: int, freq_hz: int = 440, amplitude: int = 10000, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit mono PCM sine wave audio."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    samples = []
    for i in range(num_samples):
        val = int(amplitude * math.sin(2.0 * math.pi * freq_hz * (i / sample_rate)))
        # clamp to int16 range
        val = max(-32767, min(32767, val))
        samples.append(val)
    return struct.pack(f"<{num_samples}h", *samples)


def _make_pcm_silence(duration_ms: int, sample_rate: int = 16000) -> bytes:
    """Generate 16-bit mono PCM silence."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    return struct.pack(f"<{num_samples}h", *([0] * num_samples))


def test_empty_audio_is_not_speech() -> None:
    vad = EnergyVAD(energy_threshold=300.0)
    assert vad.calculate_rms(b"") == 0.0
    assert not vad.is_speech_present(b"")
    assert vad.trim_silence(b"") == b""
    assert not vad.is_utterance_complete(b"")


def test_speech_present_above_threshold() -> None:
    vad = EnergyVAD(energy_threshold=300.0)
    loud_tone = _make_pcm_tone(duration_ms=100, amplitude=5000)
    rms = vad.calculate_rms(loud_tone)
    assert rms > 300.0
    assert vad.is_speech_present(loud_tone)


def test_speech_absent_below_threshold() -> None:
    vad = EnergyVAD(energy_threshold=300.0)
    silence = _make_pcm_silence(duration_ms=100)
    rms = vad.calculate_rms(silence)
    assert rms == 0.0
    assert not vad.is_speech_present(silence)


def test_silence_trim_removes_leading_trailing_silence() -> None:
    vad = EnergyVAD(energy_threshold=300.0, frame_duration_ms=30)
    leading_silence = _make_pcm_silence(duration_ms=300)
    tone = _make_pcm_tone(duration_ms=300, amplitude=6000)
    trailing_silence = _make_pcm_silence(duration_ms=300)
    
    full_audio = leading_silence + tone + trailing_silence
    trimmed = vad.trim_silence(full_audio, padding_ms=60)
    
    # Trimmed should be shorter than full audio but contain the tone
    assert len(trimmed) < len(full_audio)
    assert len(trimmed) > 0
    assert vad.calculate_rms(trimmed) > 300.0


def test_utterance_complete_after_trailing_silence() -> None:
    vad = EnergyVAD(energy_threshold=300.0, frame_duration_ms=30)
    tone = _make_pcm_tone(duration_ms=400, amplitude=6000)
    silence_short = _make_pcm_silence(duration_ms=200)
    silence_long = _make_pcm_silence(duration_ms=700)

    # Incomplete: trailing silence is only 200ms
    assert not vad.is_utterance_complete(tone + silence_short, min_speech_duration_ms=300, trailing_silence_ms=600)
    # Complete: trailing silence is 700ms (>= 600ms threshold)
    assert vad.is_utterance_complete(tone + silence_long, min_speech_duration_ms=300, trailing_silence_ms=600)
