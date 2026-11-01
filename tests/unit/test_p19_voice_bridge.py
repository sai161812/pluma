"""Owned storage/inert stream lifecycle checks; no microphone or native model."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from pluma.core.cancellation import CancellationToken, StopReason
from pluma.core.ipc_contracts import VoiceViewV1
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.cancellation import TaskCancelledError
from pluma.memory.activity import ActivityQuery
from pluma.voice.pipeline import VoiceClarificationRequired
from pluma.voice.presentation import VoicePresentation
from pluma.voice.recognition import RecognitionProgress
from tests.unit.test_voice_session import voice, runtime, registered
from tests.unit.test_voice_orchestrator_integration import orchestrator, ledger, db_conn


def query(core, **fields):
    return core.handle_ipc_command(dict(protocol_version=1, message_type="voice_query",
        request_id=str(uuid4()), **fields))


def test_query_is_read_only_and_cold(voice):
    runtime, core, streams = voice
    first = query(core)
    assert first["voice"] is None and first["reset_required"] is True
    assert query(core, stream_id=first["stream_id"])["reset_required"] is False
    assert streams == [] and not runtime.supervisor.get_active_tasks()


@pytest.mark.parametrize("fields", [{"voice_id": str(uuid4())}, {"stream_id": "bad"},
    {"request_id": "bad"}, {"after_sequence": 1}, {"text": "PRIVATE"}, {"stream_id": True}])
def test_query_strictly_rejects_execution_and_invalid_scope(voice, fields):
    _, core, streams = voice
    request = dict(protocol_version=1, message_type="voice_query", request_id=str(uuid4()))
    request.update(fields)
    reply = core.handle_ipc_command(request)
    assert reply["error_code"] == "INVALID_REQUEST" and streams == []


def test_listening_is_actual_capture_and_generation_resets(voice):
    runtime, core, streams = voice
    core._on_voice_press()
    first = query(core)
    view = first["voice"]
    assert view["phase"] == "LISTENING" and view["capture_active"] is True
    assert view["boundary_complete"] is False and view["task_request_id"] is None and view["text"] == ""
    assert query(core, stream_id=first["stream_id"], voice_id=view["voice_id"])["reset_required"] is False
    old = core._current_voice_capsule
    runtime.supervisor.stop_task(old.task_id, grace_s=0)
    assert query(core)["voice"]["phase"] == "CANCELLED"
    core._on_voice_release()
    core._on_voice_press()
    new = query(core, stream_id=first["stream_id"], voice_id=view["voice_id"])
    assert new["reset_required"] and new["voice"]["voice_id"] != view["voice_id"]
    assert new["voice"]["task_id"] != old.task_id and len(streams) == 2
    runtime.supervisor.stop_task(core._current_voice_capsule.task_id, grace_s=0)


@pytest.mark.parametrize("outcome,phase", [(None, "EMPTY"), (VoiceClarificationRequired(.1), "CLARIFICATION")])
def test_nonrequests_remain_terminal_without_commit_or_transcript(voice, outcome, phase):
    _, core, _ = voice
    core.voice_pipeline.process_audio = lambda *a, **kw: outcome
    core._on_voice_press(); cap = core._current_voice_capsule
    core.audio_capture.feed(b"owned synthetic audio")
    core._on_voice_release()
    view = query(core)["voice"]
    assert view["phase"] == phase and view["text"] == "" and view["task_request_id"] is None
    assert cap.terminal_ready.is_set()
    assert "voice_presentation" not in cap.model_dump() and "recognition_progress" not in cap.model_dump()


def test_empty_capture_does_not_claim_timeout(voice):
    _, core, _ = voice
    core._on_voice_press(); core._on_voice_release()
    assert query(core)["voice"]["phase"] == "EMPTY"


def test_capture_boundary_is_observed_not_invented_timeout(voice):
    runtime, core, _ = voice
    core._on_voice_press()
    core.audio_capture._utterance_complete.set()  # Inject detector signal, not physical evidence.
    view = query(core)["voice"]
    assert view["boundary_complete"] is True and view["phase"] == "LISTENING"
    runtime.supervisor.stop_task(core._current_voice_capsule.task_id, grace_s=0)


@pytest.mark.parametrize("reason,phase", [(StopReason.USER_STOP, "CANCELLED"),
    (StopReason.TASK_TIMEOUT, "TIMED_OUT"), (StopReason.INTERNAL_ERROR, "ERROR")])
def test_decoding_readback_stop_suppresses_real_progress_and_late_commit(voice, reason, phase, caplog):
    runtime, core, _ = voice
    entered, release = threading.Event(), threading.Event()
    def decode(*a, **kw):
        cap = core._current_voice_capsule
        cap.recognition_progress = RecognitionProgress(cap.task_id, cap.cancellation_token)
        cap.recognition_progress.accept(1, "put PRIVATE_BRIDGE_VALUE in the clipboard")
        entered.set()
        assert release.wait(3)
        return PlumaRequest(input_mode=InputMode.VOICE, text="get system status")
    core.voice_pipeline.process_audio = decode
    core._on_voice_press(); cap = core._current_voice_capsule
    core.audio_capture.feed(b"owned synthetic audio")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(core._on_voice_release)
            try:
                assert entered.wait(2)
                view = query(core)["voice"]
                assert view["phase"] == "DECODING" and view["recognition_sequence"] == 1
                assert view["task_request_id"] is None and "PRIVATE_BRIDGE_VALUE" not in json.dumps(view)
                cap.cancellation_token.cancel(reason)
                view = query(core)["voice"]
                assert view["phase"] == phase and view["text"] == ""
            finally:
                release.set()
            future.result(3)
        assert query(core)["voice"]["phase"] == phase
        assert "PRIVATE_BRIDGE_VALUE" not in caplog.text
        report = ActivityQuery(runtime.db).cleanup_report_for_task(cap.task_id)
        assert cap.terminal_ready.is_set() and report is not None
        assert "PRIVATE_BRIDGE_VALUE" not in report["metadata_json"]
        assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
    finally:
        runtime.supervisor.stop_task(cap.task_id, grace_s=0)


def test_denied_start_is_factual_and_closed_owner_allows_retry(voice, monkeypatch):
    runtime, core, streams = voice
    original = core.audio_capture.start
    def denied():
        raise PermissionError("PRIVATE_DEVICE_DETAIL")
    monkeypatch.setattr(core.audio_capture, "start", denied)
    core._on_voice_press()
    first = query(core)["voice"]
    assert first["phase"] == "ERROR" and first["code"] == "CAPTURE_DENIED"
    assert "PRIVATE_DEVICE_DETAIL" not in json.dumps(first)
    assert core._current_voice_capsule.voice_session is None
    monkeypatch.setattr(core.audio_capture, "start", original)
    core._on_voice_press()
    assert query(core)["voice"]["phase"] == "LISTENING" and len(streams) == 1
    runtime.supervisor.stop_task(core._current_voice_capsule.task_id, grace_s=0)


def test_ledger_and_orchestrator_admission_prove_commit(orchestrator):
    request = PlumaRequest(input_mode=InputMode.VOICE, text="mute", original_transcript="Mute.")
    cap = orchestrator._supervisor.create_task_capsule(request_id=str(request.request_id))
    cap.voice_presentation = VoicePresentation(cap.task_id, cap.cancellation_token)
    cap.voice_presentation.listening(); cap.voice_presentation.decoding()
    cap.recognition_progress = RecognitionProgress(cap.task_id, cap.cancellation_token)
    cap.recognition_progress.finish("RECOGNIZED", request.text)
    assert cap.voice_presentation.snapshot(cap, None).phase == "DECODING"
    result = orchestrator.execute(request, capsule=cap)
    view = cap.voice_presentation.snapshot(cap, None)
    assert result.success and view.phase == "COMMITTED" and view.task_request_id == str(request.request_id)
    row = ActivityQuery(orchestrator._ledger._db).task_by_id(cap.task_id)
    assert row["request_id"] == view.task_request_id


def test_closed_execution_gate_does_not_fabricate_commit(orchestrator):
    request = PlumaRequest(input_mode=InputMode.VOICE, text="mute")
    cap = orchestrator._supervisor.create_task_capsule(request_id=str(request.request_id))
    cap.voice_presentation = VoicePresentation(cap.task_id, cap.cancellation_token)
    cap.voice_presentation.listening(); cap.voice_presentation.decoding()
    orchestrator._supervisor.execution_gate.begin_shutdown()
    with pytest.raises(TaskCancelledError):
        orchestrator.execute(request, capsule=cap)
    assert cap.voice_presentation.snapshot(cap, None).phase != "COMMITTED"
    orchestrator._supervisor.stop_task(cap.task_id, grace_s=0)


def test_terminal_retention_is_bounded_and_query_clears_latest_reference(voice):
    _, core, _ = voice
    core._on_voice_press(); cap = core._current_voice_capsule
    now = [0.]
    cap.voice_presentation._clock = lambda: now[0]
    core._on_voice_release()
    first = query(core)
    assert first["voice"]["phase"] == "EMPTY"
    now[0] = 31.
    expired = query(core, stream_id=first["stream_id"], voice_id=first["voice"]["voice_id"])
    assert expired["voice"] is None and expired["reset_required"]
    assert core._current_voice_capsule is None


def test_busy_observer_fails_closed_and_does_not_wait_for_desktop(voice):
    runtime, core, _ = voice
    core._on_voice_press(); cap = core._current_voice_capsule
    with cap.voice_presentation._lock:
        assert query(core)["error_code"] == "VOICE_UNAVAILABLE"
    assert query(core)["voice"]["phase"] == "LISTENING"
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)


def test_restart_and_expired_generation_require_reset(voice):
    _, core, _ = voice
    first = query(core)
    core._voice_stream_id = str(uuid4())  # A new resident would create a new identity.
    reply = query(core, stream_id=first["stream_id"])
    assert reply["reset_required"] and reply["voice"] is None
    core._entry_gate.begin_shutdown()
    refused = query(core)
    assert refused.get("voice") is None and refused["status"] == "error"


def test_private_commit_is_redacted_and_mismatched_ownership_fails(voice, caplog):
    runtime, core, _ = voice
    core._on_voice_press(); cap = core._current_voice_capsule
    presentation = cap.voice_presentation
    presentation.decoding()
    request = PlumaRequest(input_mode=InputMode.VOICE, text="put PRIVATE_COMMIT_VALUE in the clipboard")
    with pytest.raises(ValueError, match="owner mismatch"):
        presentation.committed(request, capsule=cap)
    cap.request_id = str(request.request_id)
    presentation.committed(request, capsule=cap)
    view = query(core)["voice"]
    assert view["phase"] == "COMMITTED" and "PRIVATE_COMMIT_VALUE" not in json.dumps(view)
    other = SimpleNamespace(task_id=str(uuid4()), cancellation_token=cap.cancellation_token)
    with pytest.raises(ValueError, match="owner mismatch"):
        presentation.snapshot(other, core.audio_capture)
    assert "PRIVATE_COMMIT_VALUE" not in caplog.text
    # This direct contract fixture is not native admission/execution acceptance.
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)


def test_foreign_recognition_fails_closed_without_payload(voice):
    runtime, core, _ = voice
    core._on_voice_press(); cap = core._current_voice_capsule
    cap.voice_presentation.decoding()
    cap.recognition_progress = RecognitionProgress(str(uuid4()), cap.cancellation_token)
    cap.recognition_progress.accept(1, "PRIVATE_FOREIGN_PREVIEW")
    reply = query(core)
    assert reply["error_code"] == "VOICE_UNAVAILABLE" and "PRIVATE_FOREIGN_PREVIEW" not in json.dumps(reply)
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)


@pytest.mark.parametrize("updates", [{"phase": "COMMITTED"}, {"phase": "EMPTY", "text": "private"},
    {"recognition_sequence": 1}, {"phase": "CLARIFICATION"}, {"phase": "ERROR"},
    {"text": "x"*16385}, {"capture_active": True}])
def test_inconsistent_reply_is_rejected(updates):
    data = dict(voice_id=str(uuid4()), task_id=str(uuid4()), task_request_id=None,
        phase="DECODING", code=None, capture_active=None, boundary_complete=None,
        recognition_id=None, recognition_sequence=0, text="")
    data.update(updates)
    with pytest.raises(ValidationError):
        VoiceViewV1.model_validate(data)
