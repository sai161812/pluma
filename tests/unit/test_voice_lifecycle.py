"""tests/unit/test_voice_lifecycle.py — Phase 6: VoiceLifecycleManager unit tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.stt_adapter import TranscriptResult, WhisperSttAdapter


def test_cold_load_on_first_call() -> None:
    mock_adapter = MagicMock(spec=WhisperSttAdapter)
    mock_adapter.is_loaded = False
    mock_adapter.transcribe.return_value = TranscriptResult(text="open notepad", confidence=0.95)

    def fake_load(*args: object, **kwargs: object) -> None:
        mock_adapter.is_loaded = True

    mock_adapter.load.side_effect = fake_load

    mgr = VoiceLifecycleManager(adapter=mock_adapter, model_path="fake_model.bin", idle_unload_seconds=0.1)
    assert mgr.state == "COLD"

    res = mgr.transcribe(b"\x00" * 1600)
    assert res.text == "open notepad"
    assert mock_adapter.load.called
    assert mgr.state == "WARM"
    mgr.shutdown()


def test_warm_reuse_within_grace_window() -> None:
    mock_adapter = MagicMock(spec=WhisperSttAdapter)
    mock_adapter.is_loaded = True
    mock_adapter.transcribe.return_value = TranscriptResult(text="mute", confidence=0.99)

    mgr = VoiceLifecycleManager(adapter=mock_adapter, model_path="fake_model.bin", idle_unload_seconds=5.0)
    mgr._state = "WARM"

    res1 = mgr.transcribe(b"\x00" * 1600)
    res2 = mgr.transcribe(b"\x00" * 1600)

    assert res1.text == "mute"
    assert res2.text == "mute"
    # load() should not be called since already warm
    assert not mock_adapter.load.called
    mgr.shutdown()


def test_cold_after_grace_expires() -> None:
    mock_adapter = MagicMock(spec=WhisperSttAdapter)
    mock_adapter.is_loaded = False
    mock_adapter.transcribe.return_value = TranscriptResult(text="volume 30", confidence=0.95)

    def fake_load(*args: object, **kwargs: object) -> None:
        mock_adapter.is_loaded = True

    def fake_unload(*args: object, **kwargs: object) -> None:
        mock_adapter.is_loaded = False

    mock_adapter.load.side_effect = fake_load
    mock_adapter.unload.side_effect = fake_unload

    # Set very short grace period: 0.05s
    mgr = VoiceLifecycleManager(adapter=mock_adapter, model_path="fake_model.bin", idle_unload_seconds=0.05)
    mgr.transcribe(b"\x00" * 1600)
    assert mgr.state == "WARM"

    # Wait for timer to expire
    time.sleep(0.12)
    assert mgr.state == "COLD"
    assert mock_adapter.unload.called
    mgr.shutdown()


def test_shutdown_unloads_immediately() -> None:
    mock_adapter = MagicMock(spec=WhisperSttAdapter)
    mock_adapter.is_loaded = True

    mgr = VoiceLifecycleManager(adapter=mock_adapter, model_path="fake_model.bin")
    mgr._state = "WARM"

    mgr.shutdown()
    assert mgr.state == "COLD"
    assert mock_adapter.unload.called
