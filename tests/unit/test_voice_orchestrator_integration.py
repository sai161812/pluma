"""tests/unit/test_voice_orchestrator_integration.py — Phase 6: Voice and text pipeline parity tests."""

from __future__ import annotations

import math
import json
import struct
from unittest.mock import MagicMock
import pytest

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery
from pluma.memory.db import DbConnection
from pluma.tools.apps import OpenAppArgs
from pluma.tools.audio import MuteArgs, SetVolumeArgs
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.files import FILE_TOOL_SPECS
from pluma.tools.registry import ToolRegistry
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
    state = {}

    def register_fixture_tool(name, args_schema, state_key, readback_value, undo=True):
        def execute(args, _context=None):
            value = readback_value(args)
            state[state_key] = value
            return ToolResult.success(
                name,
                data={"readback": state[state_key]},
                factual_message="Fixture state change was read back.",
                verified=True,
            )

        def verify(result):
            matches = result.ok and state.get(state_key) == result.data.get("readback")
            return VerifyResult(
                ok=matches,
                method="fixture_state_readback",
                detail="Fixture state matched the executor receipt." if matches
                else "Fixture state did not match the executor receipt.",
            )

        def capture(args, _context=None):
            return {"state_key": state_key, "prior": state.get(state_key)}

        reg.register(ToolSpec(
            name=name,
            description="Owned in-memory fixture tool for voice routing acceptance.",
            args_schema=args_schema,
            risk_class=RiskClass.LOW,
            timeout_s=5.0,
            process_isolated=False,
            executor=execute,
            verifier=verify,
            undo_builder=capture if undo else None,
        ))

    register_fixture_tool("open_app", OpenAppArgs, "open_app", lambda args: args["app_name"])
    register_fixture_tool("set_volume", SetVolumeArgs, "volume", lambda args: args["level"])
    register_fixture_tool("mute", MuteArgs, "muted", lambda _args: True)
    sup = TaskSupervisor(ledger=ledger)
    result = Orchestrator(registry=reg, supervisor=sup, ledger=ledger)
    result.fixture_state = state
    return result


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
    class PlannerProbe:
        calls = 0
        def plan(self, **_kwargs):
            self.calls += 1
            raise AssertionError("FAST voice command must bypass planner inference.")

    planner = PlannerProbe()
    orchestrator._llm_manager = planner
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="Set volume twenty",
        confidence=0.94,
    )

    pipeline = VoicePipeline(lifecycle_manager=mock_lifecycle, vad=EnergyVAD(energy_threshold=100.0))
    raw_audio = _make_pcm_tone(duration_ms=400)

    request = pipeline.process_audio(raw_audio)
    assert request is not None
    assert request.text == "Set volume twenty"

    result = orchestrator.execute(request)
    assert result.route == RouteMode.FAST
    assert result.final_state == "SUCCEEDED"
    assert len(result.steps) == 1
    assert result.steps[0].tool == "set_volume"
    assert result.steps[0].result.data["readback"] == 20
    assert orchestrator.fixture_state["volume"] == 20
    assert planner.calls == 0

    typed = orchestrator.execute(PlumaRequest.from_text("Set volume twenty"))
    assert typed.route == result.route == RouteMode.FAST
    assert [step.tool for step in typed.steps] == [step.tool for step in result.steps]
    assert typed.steps[0].result.data == result.steps[0].result.data
    assert planner.calls == 0


def test_voice_open_notepad_matches_typed_tool_path(orchestrator: Orchestrator) -> None:
    class PlannerProbe:
        calls = 0
        def plan(self, **_kwargs):
            self.calls += 1
            raise AssertionError("FAST voice command must bypass planner inference.")

    planner = PlannerProbe()
    orchestrator._llm_manager = planner
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text="Open Notepad.", confidence=0.95, is_low_confidence=False
    )
    pipeline = VoicePipeline(
        lifecycle_manager=mock_lifecycle,
        vad=EnergyVAD(energy_threshold=100.0),
    )
    voice_request = pipeline.process_audio(_make_pcm_tone(duration_ms=400))
    assert voice_request is not None and voice_request.text == "Open Notepad"

    voice_result = orchestrator.execute(voice_request)
    text_result = orchestrator.execute(PlumaRequest.from_text("open notepad"))

    assert voice_result.route == text_result.route == RouteMode.FAST
    assert [step.tool for step in voice_result.steps] == ["open_app"]
    assert [step.tool for step in text_result.steps] == ["open_app"]
    assert voice_result.steps[0].result.data == text_result.steps[0].result.data
    assert voice_result.steps[0].result.verified and text_result.steps[0].result.verified
    assert orchestrator.fixture_state["open_app"] == "notepad"
    assert planner.calls == 0


def test_orchestrator_log_and_history_redact_spoken_clipboard_payload(
    orchestrator: Orchestrator, query: ActivityQuery, monkeypatch, caplog,
) -> None:
    payload = "clipboard-private-fixture-91a2@example.test"
    utterance = f"Paste {payload} into the open field"
    request = PlumaRequest(
        input_mode=InputMode.VOICE,
        text=utterance,
        original_transcript=utterance,
    )
    plan = Plan(
        task_id=request.request_id,
        route=RouteMode.FAST,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="mute", arguments={}, purpose="Run an isolated privacy fixture.")],
    )
    monkeypatch.setattr(
        orchestrator._router,
        "route",
        lambda _request: RouteResult(route=RouteMode.FAST, reason="isolated fixture", plan=plan),
    )

    with caplog.at_level("INFO", logger="pluma.core.orchestrator"):
        result = orchestrator.execute(request)

    assert result.final_state == "SUCCEEDED"
    assert payload not in caplog.text
    stored = query.task_by_id(result.task_id)
    assert stored is not None
    assert stored["command_text"] == "[REDACTED CLIPBOARD COMMAND]"
    assert stored["original_transcript"] == "[REDACTED CLIPBOARD COMMAND]"


def test_orchestrator_redacts_full_clipboard_command_before_log_preview(
    orchestrator: Orchestrator, query: ActivityQuery, monkeypatch, caplog,
) -> None:
    payload = "long-preview-private-fixture-7c21@example.test"
    filler = "ordinary context " * 12
    utterance = f"Please use {payload} as the value. {filler}The clipboard is the target."
    assert utterance.index("clipboard") >= 120
    request = PlumaRequest(
        input_mode=InputMode.VOICE,
        text=utterance,
        original_transcript=utterance,
    )
    plan = Plan(
        task_id=request.request_id,
        route=RouteMode.FAST,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="mute", arguments={}, purpose="Run an isolated privacy fixture.")],
    )
    monkeypatch.setattr(
        orchestrator._router,
        "route",
        lambda _request: RouteResult(route=RouteMode.FAST, reason="isolated fixture", plan=plan),
    )

    with caplog.at_level("INFO", logger="pluma.core.orchestrator"):
        result = orchestrator.execute(request)

    assert result.final_state == "SUCCEEDED"
    assert payload not in caplog.text
    stored = query.task_by_id(result.task_id)
    assert stored is not None
    assert payload not in stored["command_text"]
    assert payload not in stored["original_transcript"]
    assert stored["command_text"] == "[REDACTED CLIPBOARD COMMAND]"
    assert stored["original_transcript"] == "[REDACTED CLIPBOARD COMMAND]"


def test_complex_voice_command_selects_smart_planner_and_registered_read_tool(
    db_conn: DbConnection, ledger: ActivityLedger, tmp_path
) -> None:
    fixture_file = tmp_path / "owned-fixture.txt"
    fixture_file.write_text("owned test content", encoding="utf-8")
    directory_tool = next(spec for spec in FILE_TOOL_SPECS if spec.name == "list_folder")
    registry = ToolRegistry()
    registry.register(directory_tool)

    class PlannerProbe:
        def __init__(self):
            self.calls = []

        def plan(self, **kwargs):
            self.calls.append(kwargs)
            return Plan(
                route=RouteMode.SMART,
                mode=PlanMode.DIRECT,
                steps=[ToolCall(
                    tool="list_folder",
                    arguments={"path": str(tmp_path), "max_entries": 10},
                    purpose="Inspect the owned fixture directory.",
                )],
            )

    planner = PlannerProbe()
    runtime_orchestrator = Orchestrator(
        registry=registry,
        supervisor=TaskSupervisor(ledger=ledger),
        ledger=ledger,
        llm_manager=planner,
    )
    command = f"List the files in this exact directory: {tmp_path}"
    mock_lifecycle = MagicMock(spec=VoiceLifecycleManager)
    mock_lifecycle.transcribe.return_value = TranscriptResult(
        text=command, confidence=0.92, is_low_confidence=False
    )
    pipeline = VoicePipeline(
        lifecycle_manager=mock_lifecycle,
        vad=EnergyVAD(energy_threshold=100.0),
    )
    request = pipeline.process_audio(_make_pcm_tone(duration_ms=400))
    assert request is not None and request.input_mode == InputMode.VOICE
    assert request.text == command and request.original_transcript == command

    result = runtime_orchestrator.execute(request)

    assert result.route == RouteMode.SMART
    assert result.final_state == "SUCCEEDED"
    assert [step.tool for step in result.steps] == ["list_folder"]
    assert planner.calls and planner.calls[0]["command"] == command
    action = ActivityQuery(db_conn).actions_for_task(result.task_id)[0]
    assert json.loads(action["args_json_sanitized"])["args"]["path"] == str(tmp_path)
    assert any(entry.get("name") == fixture_file.name
               for entry in result.steps[0].result.data.get("entries", []))
    task = ActivityQuery(db_conn).task_by_id(result.task_id)
    assert task is not None
    assert task["input_mode"] == "voice"
    assert task["original_transcript"] == command
