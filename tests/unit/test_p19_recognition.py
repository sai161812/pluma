"""Recognition contracts and owned process transport; never microphone input."""
from concurrent.futures import ThreadPoolExecutor
import threading
import time
from types import SimpleNamespace

import pytest

from pluma.core.cancellation import CancellationToken, StopReason
from pluma.tools.base import ToolResult
from pluma.tools.registry import WorkerRequest, TaskWorkerController
from pluma.voice.recognition import RecognitionProgress, MAX_TRANSCRIPT_BYTES
from tests.unit.test_ipc_request_contract import resident_fixture
from tests.unit.test_p18_runtime import capsule


def test_prefix_and_final_are_redacted_and_not_execution_admission(caplog):
    token = CancellationToken()
    progress = RecognitionProgress("owned", token)
    progress.accept(1, "put PRIVATE_SENTINEL")
    progress.accept(2, "in the clipboard")
    assert "PRIVATE_SENTINEL" not in progress.snapshot().text
    progress.finish("RECOGNIZED", "put PRIVATE_SENTINEL in the clipboard")
    assert progress.snapshot().state == "RECOGNIZED" and "PRIVATE_SENTINEL" not in progress.snapshot().text
    assert "PRIVATE_SENTINEL" not in caplog.text and progress._raw == ""
    assert not hasattr(progress.snapshot(), "committed")


@pytest.mark.parametrize("sequence,text", [(True, "a"), (0, "a"), (129, "a"), (1, ""), (1, "文" * 1500)])
def test_malformed_segments_are_refused_without_mutating_state(sequence, text):
    progress = RecognitionProgress("owned", CancellationToken())
    with pytest.raises(ValueError):
        progress.accept(sequence, text)
    assert progress.snapshot().sequence == 0 and progress.snapshot().text == ""


def test_contiguous_bounded_observations_and_new_generations():
    token = CancellationToken()
    progress = RecognitionProgress("owned", token)
    progress.accept(1, "hello")
    with pytest.raises(ValueError): progress.accept(3, "late")
    assert progress.snapshot().text == "hello"
    for seq in range(2, 7): progress.accept(seq, "x" * 4096)
    assert progress.snapshot().state == "UNAVAILABLE" and progress.snapshot().text == ""
    progress.finish("RECOGNIZED", "x" * (MAX_TRANSCRIPT_BYTES + 1))
    assert progress.snapshot().state == "UNAVAILABLE"
    replacement = RecognitionProgress("owned", token)
    assert replacement.recognition_id != progress.recognition_id and replacement.snapshot().sequence == 0


@pytest.mark.parametrize("reason,expected", [(StopReason.USER_STOP, "CANCELLED"), (StopReason.TASK_TIMEOUT, "TIMED_OUT"), (StopReason.INTERNAL_ERROR, "FAILED")])
def test_latch_hides_text_and_late_completion_cannot_restore_it(reason, expected):
    token = CancellationToken()
    progress = RecognitionProgress("owned", token)
    progress.accept(1, "owned preview")
    token.cancel(reason)
    assert progress.snapshot().text == "" and progress.snapshot().state == expected
    progress.accept(2, "late")
    progress.finish("RECOGNIZED", "late result")
    assert progress.snapshot().state == expected and progress.snapshot().text == ""


def test_failed_recognition_is_not_reanimated_by_a_late_final():
    progress = RecognitionProgress("owned", CancellationToken())
    progress.accept(1, "preview")
    progress.finish("FAILED")
    progress.finish("RECOGNIZED", "late")
    assert progress.snapshot().state == "FAILED" and progress.snapshot().text == ""


def test_empty_final_is_not_recognition_or_admission():
    progress = RecognitionProgress("owned", CancellationToken())
    progress.finish("RECOGNIZED", "   ")
    assert progress.snapshot().state == "EMPTY" and progress.snapshot().text == ""


def owned_recognition_worker(args, context):
    context.publish_recognition(1 if not args.get("bad") else 2, "owned recognition")
    while True:
        context.cancellation_token.raise_if_cancelled()
        time.sleep(.01)


def test_owned_channel_stop_cleanup_and_persisted_readback(resident_fixture):
    from pluma.memory.activity import ActivityQuery
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    progress = cap.recognition_progress = RecognitionProgress(cap.task_id, cap.cancellation_token)
    controller = cap.worker_controller = TaskWorkerController(cap.task_id)
    observed = threading.Event()
    def receive(sequence, text):
        progress.accept(sequence, text)
        observed.set()
    request = WorkerRequest(cap.task_id, "voice_stt", {}, 5, recognition_updates=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(controller.execute_call, owned_recognition_worker, {}, request, 5,
                job_object=cap.job_object, cancellation_token=cap.cancellation_token, on_recognition=receive)
            assert observed.wait(3) and not future.done()
            assert progress.snapshot().state == "DECODING" and progress.snapshot().sequence == 1
            assert "recognition_progress" not in cap.model_dump()
            supervisor.request_stop(cap.task_id)
            assert progress.snapshot().state == "CANCELLED" and progress.snapshot().text == ""
            assert future.result(3)[0] == "cancelled" and supervisor.join_stop_operations(3)
            assert controller.verify_cleanup() and cap.terminal_persisted
            row = ActivityQuery(ledger._db).cleanup_report_for_task(cap.task_id)
            assert row and row["released_at"]
            assert "owned recognition" not in row["metadata_json"]
    finally:
        supervisor.stop_task(cap.task_id, grace_s=0)
        # The terminal supervisor may already have retired this native event.
        # A final caller/disposer must still return its factual STOP outcome.
        controller.dispose_owned_worker()


def test_channel_scope_and_sequence_fail_closed(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    controller = cap.worker_controller = TaskWorkerController(cap.task_id)
    request = WorkerRequest(cap.task_id, "fixture_read", {}, 3, recognition_updates=True)
    try:
        assert controller.execute_call(owned_recognition_worker, {}, request, 3, on_recognition=lambda *_: None)[0] == "error"
        assert controller.worker_identity is None
        request.tool_name = "voice_stt"
        status, error = controller.execute_call(owned_recognition_worker, {"bad": True}, request, 3,
            on_recognition=lambda *_: pytest.fail("Out-of-order evidence was published."))
        assert status == "error" and "owned recognition" not in error and controller.verify_cleanup()
    finally:
        supervisor.stop_task(cap.task_id, grace_s=0)
        if not controller.verify_cleanup():
            controller.dispose_owned_worker()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_native_adapter_uses_real_callback_instead_of_returned_segments(tmp_path, monkeypatch, cleanup_fails):
    from tests.unit.test_voice_native_worker import _Capsule, _Token, _Controller, _Registry, _fake_whisper_modules
    import sys
    from pluma.voice.stt_adapter import WhisperSttAdapter
    segments = [SimpleNamespace(text="actual callback", probability=.9, t0=0, t1=1)]
    _fake_whisper_modules(monkeypatch, segments)
    model = sys.modules["pywhispercpp.model"].Model
    model._params = object()
    cleared = []
    def unregister(params, callback):
        if cleanup_fails:
            raise RuntimeError("Owned binding fault fixture")
        cleared.append(("segments", callback))
    sys.modules["pywhispercpp.model"].pw = SimpleNamespace(
        assign_new_segment_callback=unregister,
        assign_abort_callback=lambda params, callback: cleared.append(("abort", callback)))
    returned = model.transcribe
    cap = _Capsule(); token = _Token(cap)
    class Controller(_Controller):
        def execute_call(self, executor, args, request, **kwargs):
            context = SimpleNamespace(cancellation_token=token, publish_recognition=kwargs["on_recognition"])
            from pluma.tools.registry import WorkerResponse
            return "ok", WorkerResponse(result=executor(args, context))
    def transcribe(self, samples, **kwargs):
        kwargs["new_segment_callback"](segments[0])
        snapshot = cap.recognition_progress.snapshot()
        assert snapshot.state == "DECODING" and snapshot.text == "actual callback"
        return returned(self, samples, **kwargs)
    monkeypatch.setattr(model, "transcribe", transcribe)
    path = tmp_path / "owned-model.bin"; path.write_bytes(b"fixture")
    adapter = WhisperSttAdapter(registry=_Registry(Controller()))
    adapter.load(str(path))
    if cleanup_fails:
        with pytest.raises(RuntimeError, match="model cleanup was not verified"):
            adapter.transcribe(b"\x01\x00" * 1600, cancellation_token=token)
        assert cap.recognition_progress.snapshot().state == "FAILED" and cap.recognition_progress.snapshot().text == ""
        return
    assert adapter.transcribe(b"\x01\x00" * 1600, cancellation_token=token).text == "actual callback"
    assert cap.recognition_progress.snapshot().state == "RECOGNIZED"
    assert cleared == [("segments", None), ("abort", None)]


def test_native_absence_assertion_rejects_a_live_matching_identity(monkeypatch):
    from tests.windows import p14_native_stt_acceptance as acceptance
    current = 1762000000.0
    identity = {"pid": 123, "creation_time": int((current + 11644473600) * 10_000_000)}
    monkeypatch.setattr(acceptance.psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: current))
    with pytest.raises(AssertionError, match="remained alive"):
        acceptance._assert_original_process_absent(identity)
    # A reused PID has a different generation, even less than one second away.
    monkeypatch.setattr(acceptance.psutil, "Process", lambda pid: SimpleNamespace(create_time=lambda: current + .5))
    acceptance._assert_original_process_absent(identity)
