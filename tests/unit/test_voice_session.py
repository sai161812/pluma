"""P07 lifecycle evidence: inert microphones/models, owned SQLite/runtime.

No physical voice, desktop action, hotkey listener or STT model is started.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from pluma.core.request import InputMode, PlumaRequest
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.tools.base import ToolResult
from pluma.voice.capture import AudioCapture
from tests.unit.test_runtime_shutdown import runtime, registered


class Stream:
    def __init__(self, **kwargs):
        self.callback = kwargs['callback']
        self.closed = False
        self.active = False
        self.failure = None
    def start(self):
        self.active = True
        if self.failure == 'start':
            raise PermissionError('private driver detail')
    def stop(self):
        if self.failure == 'stop':
            raise RuntimeError('private driver detail')
        self.active = False
    def abort(self):
        if self.failure == 'abort':
            raise RuntimeError('private driver detail')
        self.active = False
    def close(self):
        if self.failure == 'close':
            raise RuntimeError('private driver detail')
        if self.failure != 'readback':
            self.closed = True


@pytest.fixture
def voice(runtime, monkeypatch):
    streams = []
    def create(**kwargs):
        stream = Stream(**kwargs)
        streams.append(stream)
        return stream
    monkeypatch.setitem(sys.modules, 'sounddevice', SimpleNamespace(RawInputStream=create))
    core = runtime.resident_core
    core.audio_capture = AudioCapture()
    core.voice_pipeline = SimpleNamespace(process_audio=lambda *a, **kw: None)
    yield runtime, core, streams
    for stream in streams:
        stream.failure = None  # release injected native failures before teardown


def journal(runtime, cap):
    query = ActivityQuery(runtime.db)
    data = json.loads(query.cleanup_report_for_task(cap.task_id)['metadata_json'])
    assert data['entries'] == cap.outcome_details()['cleanup_evidence']
    assert 'private' not in json.dumps(data)
    return data


def test_stop_closes_and_discards_before_key_release(voice):
    runtime, core, streams = voice
    stt_calls = []
    core.voice_pipeline.process_audio = lambda *a, **kw: stt_calls.append(True)
    core._on_voice_press()
    cap = core._current_voice_capsule
    core.audio_capture.feed(b'private audio')
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert streams[0].closed and not streams[0].active
    assert core.audio_capture.capture_closed
    assert cap.state == TaskState.STOPPED and cap.terminal_persisted
    assert cap.voice_session is None
    data = journal(runtime, cap)
    assert data['pre_execution_outcome']['final_state'] == 'STOPPED'
    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
    core._on_voice_release()
    assert core._voice_session is None and not runtime.supervisor.get_active_tasks()
    assert stt_calls == []


@pytest.mark.parametrize('path', ['empty', 'silence', 'denied', 'failed', 'missing_pipeline', 'missing_capture', 'missing_executor'])
def test_every_pre_execution_path_finalizes_without_fake_command(voice, path):
    runtime, core, streams = voice
    if path == 'missing_capture':
        core.audio_capture = None
    if path == 'missing_pipeline':
        core.voice_pipeline = None
    if path == 'denied':
        core.voice_pipeline = SimpleNamespace(process_audio=lambda *a, **kw: None)
    if path == 'failed':
        def fail(*a, **kw): raise RuntimeError('private transcript')
        core.voice_pipeline.process_audio = fail
    if path == 'missing_executor':
        core.voice_pipeline.process_audio = lambda *a, **kw: PlumaRequest(input_mode=InputMode.VOICE, text='fixture')
        core.orchestrator = None
    core._on_voice_press()
    cap = core._current_voice_capsule
    if path != 'empty' and core.audio_capture is not None:
        core.audio_capture.feed(b'private audio')
    core._on_voice_release()
    assert cap.terminal_ready.is_set() and cap.terminal_persisted
    assert cap.state == (TaskState.FAILED if path in ('failed', 'missing_capture', 'missing_executor') else TaskState.STOPPED)
    assert not runtime.supervisor.get_active_tasks()
    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
    assert core._voice_session is None
    journal(runtime, cap)


def test_repeated_empty_capture_does_not_accumulate_created_capsules(voice):
    runtime, core, streams = voice
    for _ in range(55):
        core._on_voice_press()
        core._on_voice_release()
    assert len(runtime.supervisor._tasks) <= 50
    assert not runtime.supervisor.get_active_tasks()
    assert all(s.closed for s in streams)


def test_duplicate_press_and_release_share_one_owner(voice):
    runtime, core, streams = voice
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: core._on_voice_press(), range(8)))
    assert len(streams) == len(runtime.supervisor._tasks) == 1
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: core._on_voice_release(), range(8)))
    assert not runtime.supervisor.get_active_tasks() and streams[0].closed


@pytest.mark.parametrize('failure', ['start', 'stop', 'abort', 'close', 'readback'])
def test_native_capture_failure_retains_owner_until_readback(voice, monkeypatch, failure):
    runtime, core, streams = voice
    if failure == 'start':
        original = Stream.start
        def fail_start(self):
            self.failure = 'start'
            original(self)
        monkeypatch.setattr(Stream, 'start', fail_start)
    core._on_voice_press()
    cap = core._current_voice_capsule
    stream = streams[0]
    if failure == 'start':
        assert cap.state == TaskState.FAILED and stream.closed
        assert core.audio_capture.capture_closed
    else:
        stream.failure = failure
        core.audio_capture.feed(b'private audio')
        if failure == 'stop':
            core._on_voice_release()
            # Abort is a verified fallback for a normal stop failure.
            assert cap.state == TaskState.FAILED and stream.closed
        else:
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
            assert cap.voice_session is not None and core.audio_capture._stream is stream
            assert not runtime.close(.3).complete and runtime.db.is_open
            stream.failure = None
            assert runtime.close(3).complete
    assert core.audio_capture._buffer == b''


@pytest.mark.parametrize('operation', ['start', 'close'])
def test_stop_is_latched_while_native_capture_operation_is_blocked(voice, monkeypatch, operation):
    runtime, core, streams = voice
    entered, release = threading.Event(), threading.Event()
    original = getattr(Stream, operation)
    def blocked(self):
        entered.set()
        assert release.wait(4)
        return original(self)
    monkeypatch.setattr(Stream, operation, blocked)
    if operation == 'close':
        core._on_voice_press()
    with ThreadPoolExecutor(2) as pool:
        call = pool.submit(core._on_voice_press if operation == 'start' else core._on_voice_release)
        assert entered.wait(2)
        cap = core._current_voice_capsule
        try:
            stop = pool.submit(runtime.supervisor.stop_task, cap.task_id, grace_s=0)
            stop.result(1)
            assert cap.stop_latch_set and cap.state == TaskState.STOPPED_WITH_RESIDUAL
            assert cap.voice_session is not None
            assert runtime.db.is_open and not runtime.close(.03).complete
        finally:
            release.set()
        call.result(3)
    assert runtime.close(3).complete
    assert streams[0].closed and core.audio_capture.capture_closed


def test_release_racing_start_cannot_lose_or_replace_capture(voice, monkeypatch):
    runtime, core, streams = voice
    entered, release = threading.Event(), threading.Event()
    original = Stream.start
    def blocked(self):
        entered.set()
        assert release.wait(3)
        original(self)
    monkeypatch.setattr(Stream, 'start', blocked)
    with ThreadPoolExecutor(3) as pool:
        press = pool.submit(core._on_voice_press)
        assert entered.wait(2)
        cap = core._current_voice_capsule
        finish = pool.submit(core._on_voice_release)
        try:
            core._on_voice_press()
            assert len(runtime.supervisor._tasks) == 1
        finally:
            release.set()
        press.result(3)
        finish.result(3)
    assert streams[0].closed and cap.state == TaskState.STOPPED
    assert core._voice_session is None


def test_stop_during_stt_keeps_owner_and_prevents_execution(voice):
    runtime, core, streams = voice
    entered, release = threading.Event(), threading.Event()
    calls = []
    registered(runtime, lambda args: calls.append(args) or ToolResult.success(tool='shutdown_probe'))
    def transcribe(audio, cancellation_token):
        assert cancellation_token is core._current_voice_capsule.cancellation_token
        entered.set()
        assert release.wait(3)
        return PlumaRequest(input_mode=InputMode.VOICE, text='fixture')
    core.voice_pipeline.process_audio = transcribe
    core._on_voice_press()
    cap = core._current_voice_capsule
    core.audio_capture.feed(b'private audio')
    with ThreadPoolExecutor(1) as pool:
        call = pool.submit(core._on_voice_release)
        assert entered.wait(2)
        try:
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            assert cap.state == TaskState.STOPPED_WITH_RESIDUAL and cap.voice_session is not None
            journal(runtime, cap)
            assert not runtime.close(.03).complete and runtime.db.is_open
        finally:
            release.set()
        call.result(3)
    assert calls == [] and core.audio_capture.capture_closed
    assert not runtime.supervisor.get_active_tasks()
    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
    journal(runtime, cap)


def test_voice_and_text_use_real_registered_executor_and_same_capsule(voice):
    runtime, core, streams = voice
    calls, tokens = [], []
    registered(runtime, lambda args: calls.append('verified') or ToolResult.success(tool='shutdown_probe'))
    def transcribe(audio, cancellation_token):
        tokens.append(cancellation_token)
        return PlumaRequest(input_mode=InputMode.VOICE, text='fixture', original_transcript='Fixture.')
    core.voice_pipeline.process_audio = transcribe
    core._on_voice_press()
    cap = core._current_voice_capsule
    core.audio_capture.feed(b'private audio')
    core._on_voice_release()
    assert tokens == [cap.cancellation_token]
    assert cap.state == TaskState.SUCCEEDED and cap.voice_session is None
    row = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    assert row['input_mode'] == 'voice' and row['final_state'] == 'SUCCEEDED'
    assert row['request_id'] == cap.request_id and row['command_text'] == 'fixture'
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=InputMode.TEXT, text='fixture'))
    assert result.success and calls == ['verified', 'verified']
    journal(runtime, cap)


def test_stop_between_stt_and_actual_tool_admission(voice):
    runtime, core, streams = voice
    calls = []
    registered(runtime, lambda args: calls.append('started') or ToolResult.success(tool='shutdown_probe'))
    execute = runtime.orchestrator.execute
    def stopped(request, capsule):
        runtime.supervisor.stop_task(capsule.task_id, grace_s=0)
        return execute(request, capsule=capsule)
    core.orchestrator = SimpleNamespace(execute=stopped)
    core.voice_pipeline.process_audio = lambda *a, **kw: PlumaRequest(input_mode=InputMode.VOICE, text='fixture')
    core._on_voice_press()
    cap = core._current_voice_capsule
    core.audio_capture.feed(b'private audio')
    core._on_voice_release()
    assert calls == [] and cap.stop_latch_set
    row = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    assert row['final_state'] == cap.state.value and row['input_mode'] == 'voice'


def test_old_callback_cannot_feed_new_recording(voice):
    runtime, core, streams = voice
    capture = core.audio_capture
    capture.start()
    old = streams[0].callback
    capture.cancel()
    capture.start()
    old(b'private stale audio', 1, None, None)
    assert capture.stop_and_get() == b''
    assert capture.capture_closed


def test_missing_device_library_fails_closed(voice, monkeypatch):
    runtime, core, streams = voice
    monkeypatch.setitem(sys.modules, 'sounddevice', None)
    core._on_voice_press()
    cap = core._current_voice_capsule
    assert cap.state == TaskState.FAILED and core.audio_capture.capture_closed
    assert not streams and not runtime.supervisor.get_active_tasks()


def test_stop_between_capsule_publication_and_capture_attachment(voice, monkeypatch):
    runtime, core, streams = voice
    attach = runtime.supervisor.attach_voice_session
    def stopped(cap, session):
        runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        attach(cap, session)
    monkeypatch.setattr(runtime.supervisor, 'attach_voice_session', stopped)
    core._on_voice_press()
    cap = core._current_voice_capsule
    assert cap.state == TaskState.STOPPED and not streams
    core._on_voice_release()
    assert not runtime.supervisor.get_active_tasks()


def test_release_without_press_does_not_touch_capture(voice):
    runtime, core, streams = voice
    core._on_voice_release()
    assert not streams and not runtime.supervisor._tasks


def test_failed_close_blocks_new_capture_until_retry_verified(voice):
    runtime, core, streams = voice
    core._on_voice_press()
    cap = core._current_voice_capsule
    streams[0].failure = 'close'
    core._on_voice_release()
    assert cap.state == TaskState.FAILED and cap.voice_session is not None
    core._on_voice_press()
    assert len(streams) == 1 and core._current_voice_capsule is cap
    streams[0].failure = None
    core._on_voice_press()
    assert len(streams) == 2 and core._current_voice_capsule is not cap
    assert cap.voice_session is None
    journal(runtime, cap)
    core._on_voice_release()


def test_unknown_capture_readback_never_establishes_clean_stop(voice, monkeypatch):
    runtime, core, streams = voice
    core._on_voice_press()
    cap = core._current_voice_capsule
    closed = AudioCapture.capture_closed
    def unavailable(self): raise OSError('private readback error')
    monkeypatch.setattr(AudioCapture, 'capture_closed', property(unavailable))
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert cap.state == TaskState.STOPPED_WITH_RESIDUAL and cap.voice_session is not None
    journal(runtime, cap)
    monkeypatch.setattr(AudioCapture, 'capture_closed', closed)
    assert runtime.close().complete


def test_global_stop_latches_other_tasks_before_blocked_voice_close(voice, monkeypatch):
    runtime, core, streams = voice
    core._on_voice_press()
    voice_cap = core._current_voice_capsule
    other = runtime.supervisor.create_task_capsule(history_expected=False)
    observed = []
    original = Stream.abort
    def check(self):
        observed.append((voice_cap.stop_latch_set, other.stop_latch_set))
        original(self)
    monkeypatch.setattr(Stream, 'abort', check)
    runtime.supervisor.stop_all_active_tasks()
    assert observed and all(all(row) for row in observed)
    assert voice_cap.state == other.state == TaskState.STOPPED
    assert streams[0].closed


def test_real_pipeline_low_confidence_target_never_dispatches(voice):
    import math
    import struct
    from pluma.voice.pipeline import VoicePipeline
    from pluma.voice.stt_adapter import TranscriptResult
    runtime, core, streams = voice
    tokens = []
    def transcribe(audio, sample_rate, cancellation_token):
        tokens.append(cancellation_token)
        return TranscriptResult(text='delete private.txt', confidence=.2, is_low_confidence=True)
    core.voice_pipeline = VoicePipeline(lifecycle_manager=SimpleNamespace(transcribe=transcribe))
    core._on_voice_press()
    cap = core._current_voice_capsule
    tone = struct.pack('<6400h', *[int(8000 * math.sin(i)) for i in range(6400)])
    core.audio_capture.feed(tone)
    core._on_voice_release()
    assert tokens == [cap.cancellation_token]
    assert cap.state == TaskState.STOPPED and not cap.steps
    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) is None
    assert core.audio_capture.capture_closed
    journal(runtime, cap)


def test_voice_stt_timeout_is_failed_and_read_back_in_ledger(voice):
    import math
    import struct
    from pluma.core.cancellation import StopReason

    runtime, core, _streams = voice

    def timeout(_audio, cancellation_token):
        cancellation_token.cancel(StopReason.TASK_TIMEOUT)
        raise TimeoutError("private timeout details")

    core.voice_pipeline = SimpleNamespace(process_audio=timeout)
    core._on_voice_press()
    capsule = core._current_voice_capsule
    tone = struct.pack("<6400h", *[int(8000 * math.sin(index)) for index in range(6400)])
    core.audio_capture.feed(tone)
    core._on_voice_release()

    assert capsule.cancellation_token.reason == StopReason.TASK_TIMEOUT
    assert capsule.state == TaskState.FAILED
    report = journal(runtime, capsule)
    assert report["pre_execution_outcome"]["final_state"] == "FAILED"
    assert report["pre_execution_outcome"]["stop_reason"] == StopReason.TASK_TIMEOUT.value
