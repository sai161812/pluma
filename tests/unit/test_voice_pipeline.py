"""tests/unit/test_voice_pipeline.py — Phase 6: VoicePipeline end-to-end unit tests."""

from __future__ import annotations

import math
import struct
from unittest.mock import MagicMock
import pytest

from pluma.core.cancellation import CancellationToken
from pluma.core.request import InputMode, PlumaRequest
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.pipeline import VoicePipeline, is_material_target, normalize_transcript
from pluma.voice.stt_adapter import TranscriptResult
from pluma.voice.vad import EnergyVAD


def _make_pcm_tone(duration_ms: int = 500, amplitude: int = 8000, sample_rate: int = 16000) -> bytes:
    """Helper to create dummy speech PCM audio."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    samples = [int(amplitude * math.sin(2 * math.pi * 440 * (i / sample_rate))) for i in range(num_samples)]
    return struct.pack(f"<{num_samples}h", *samples)


def test_normalize_transcript_behavior() -> None:
    assert normalize_transcript("  open   notepad.  ") == "open notepad"
    assert normalize_transcript("MUTE!") == "MUTE"
    assert normalize_transcript("volume 50") == "volume 50"


def test_is_material_target_detection() -> None:
    assert is_material_target("delete old_file.txt")
    assert is_material_target("remove database")
    assert is_material_target("move file.pdf to folder")
    assert is_material_target("volume 20")
    assert is_material_target("set volume to fifty percent")
    assert not is_material_target("open notepad")
    assert not is_material_target("show activity")


def test_voice_pipeline_produces_pluma_request() -> None:
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="Open Notepad.",
        confidence=0.95,
        is_low_confidence=False,
    )

    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    raw_audio = _make_pcm_tone(duration_ms=400)

    request = pipeline.process_audio(raw_audio)
    assert request is not None
    assert isinstance(request, PlumaRequest)
    assert request.input_mode == InputMode.VOICE
    assert request.text == "Open Notepad"
    assert request.original_transcript == "Open Notepad."


def test_voice_pipeline_silence_returns_none() -> None:
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=500.0))
    
    silence = struct.pack("<1600h", *([0] * 1600))
    request = pipeline.process_audio(silence)
    assert request is None
    assert not mock_lifecycle.transcribe.called


def test_voice_pipeline_cancelled_token_returns_none() -> None:
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    
    token = CancellationToken()
    token.cancel()

    raw_audio = _make_pcm_tone(duration_ms=400)
    request = pipeline.process_audio(raw_audio, cancellation_token=token)
    assert request is None
    assert not mock_lifecycle.transcribe.called


def test_voice_pipeline_low_confidence_with_material_target_returns_none() -> None:
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    # Low confidence on destructive/filename command
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="delete important_report.pdf",
        confidence=0.45,
        is_low_confidence=True,
    )

    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    raw_audio = _make_pcm_tone(duration_ms=400)

    request = pipeline.process_audio(raw_audio)
    # Must refuse to guess and return None
    assert request is None
