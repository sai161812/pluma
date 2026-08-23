"""tests/unit/test_voice_orchestrator_integration.py — Phase 6: Voice and text pipeline parity tests."""

from __future__ import annotations

import math
import struct
from unittest.mock import MagicMock
import pytest

from pluma.brain.schemas import RouteMode
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery
from pluma.memory.db import DbConnection
from pluma.tools.registry import ToolRegistry, register_default_tools
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.pipeline import VoicePipeline
from pluma.voice.stt_adapter import TranscriptResult
from pluma.voice.vad import EnergyVAD


def _make_pcm_tone(duration_ms: int = 500, amplitude: int = 8000, sample_rate: int = 16000) -> bytes:
    """Helper to create dummy speech PCM audio."""
    num_samples = int(sample_rate * (duration_ms / 1000.0))
    samples = [int(amplitude * math.sin(2 * math.pi * 440 * (i / sample_rate))) for i in range(num_samples)]
    return struct.pack(f"<{num_samples}h", *samples)


@pytest.fixture()
def db_conn() -> DbConnection:
    db = DbConnection(":memory:")
    db.open()
    return db


@pytest.fixture()
def ledger(db_conn: DbConnection) -> ActivityLedger:
    return ActivityLedger(db_conn)


@pytest.fixture()
def query(db_conn: DbConnection) -> ActivityQuery:
    return ActivityQuery(db_conn)


@pytest.fixture()
def orchestrator(ledger: ActivityLedger) -> Orchestrator:
    reg = ToolRegistry()
    register_default_tools(reg)
    sup = TaskSupervisor(ledger=ledger)
    return Orchestrator(registry=reg, supervisor=sup, ledger=ledger)


def test_voice_command_fast_route_execution_and_ledger(
    orchestrator: Orchestrator,
    query: ActivityQuery,
) -> None:
    # Set up mock STT
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="Mute.",
        confidence=0.98,
        is_low_confidence=False,
    )

    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    raw_audio = _make_pcm_tone(duration_ms=400)

    # Process voice
    request = pipeline.process_audio(raw_audio)
    assert request is not None
    assert request.input_mode == InputMode.VOICE
    assert request.text == "Mute"
    assert request.original_transcript == "Mute."

    # Execute through orchestrator
    result = orchestrator.execute(request)
    assert result.route == RouteMode.FAST
    assert result.final_state == "SUCCEEDED"
    assert len(result.steps) == 1
    assert result.steps[0].tool == "mute"

    # Query ledger to verify input_mode was stored as voice
    task_rec = query.get_task(result.task_id)
    assert task_rec is not None
    assert task_rec["input_mode"] == "voice"
    assert task_rec["final_state"] == "SUCCEEDED"


def test_voice_command_volume_fast_route_parity(orchestrator: Orchestrator) -> None:
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="Volume thirty",
        confidence=0.94,
    )

    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    raw_audio = _make_pcm_tone(duration_ms=400)

    request = pipeline.process_audio(raw_audio)
    assert request is not None
    assert request.text == "Volume thirty"

    result = orchestrator.execute(request)
    assert result.route == RouteMode.FAST
    assert result.final_state == "SUCCEEDED"
    assert len(result.steps) == 1
    assert result.steps[0].tool == "set_volume"
