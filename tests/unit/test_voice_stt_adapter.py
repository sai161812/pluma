"""tests/unit/test_voice_stt_adapter.py — Phase 6: WhisperSttAdapter unit tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
import pytest

from pluma.core.cancellation import CancellationToken
from pluma.voice.stt_adapter import TranscriptResult, WhisperSttAdapter


def test_stt_adapter_not_imported_at_module_level() -> None:
    """Verify pywhispercpp is not imported at module level."""
    import pluma.voice.stt_adapter
    assert "pywhispercpp" not in sys.modules, "pywhispercpp must not be imported at module level"


def test_transcript_result_low_confidence_flag() -> None:
    adapter = WhisperSttAdapter(low_confidence_threshold=0.65)
    
    res_high = TranscriptResult(text="open notepad", confidence=0.85, is_low_confidence=False)
    assert not res_high.is_low_confidence
    assert res_high.text == "open notepad"

    res_low = TranscriptResult(text="delete file.txt", confidence=0.45, is_low_confidence=True)
    assert res_low.is_low_confidence


def test_stt_transcribe_cancelled_returns_early() -> None:
    adapter = WhisperSttAdapter()
    token = CancellationToken()
    token.cancel()

    res = adapter.transcribe(b"\x00" * 1000, cancellation_token=token)
    assert res.text == ""
    assert res.is_low_confidence


def test_stt_transcribe_empty_audio_returns_empty() -> None:
    adapter = WhisperSttAdapter()
    res = adapter.transcribe(b"")
    assert res.text == ""


def test_stt_missing_model_raises_file_not_found(tmp_path: object) -> None:
    adapter = WhisperSttAdapter()
    non_existent = str(tmp_path / "non_existent_model.bin")
    with pytest.raises(FileNotFoundError, match="Whisper model file not found"):
        adapter.load(non_existent)


def test_stt_unload_resets_state() -> None:
    adapter = WhisperSttAdapter()
    adapter._model = MagicMock()
    adapter._model_path = "/path/model.bin"
    assert adapter.is_loaded

    adapter.unload()
    assert not adapter.is_loaded
    assert adapter._model_path is None
