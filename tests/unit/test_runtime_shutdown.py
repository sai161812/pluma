"""P06 runtime shutdown: owned fixtures, real SQLite/native pipes, inert devices.

No production hotkeys, microphone, desktop apps, settings or model are used.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
import uuid

import pytest

from pluma.app import PlumaApplicationRuntime
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.config.paths import PlumaPaths
from pluma.core import job_object
from pluma.core.cancellation import TaskCancelledError
from pluma.core.cleanup import CleanupEvidence
from pluma.core.ipc import IpcClient
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.shutdown import ShutdownSession, WorkGate
from pluma.core.task_supervisor import TaskCapsule, TaskState
from pluma.memory.activity import ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.voice.capture import AudioCapture
from tests.unit.test_cleanup_evidence import Job, Worker

NATIVE_JOB = job_object.WindowsJobObject


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', Job)
    paths = PlumaPaths(tmp_path / 'local', tmp_path / 'roaming')
    paths.ensure_directories()
    monkeypatch.setattr('pluma.config.paths.get_paths', lambda: paths)
    value = PlumaApplicationRuntime(paths, config={'voice': {'required': False}})
    value.resident_core.ipc.address = rf'\\.\pipe\pluma_p06_{uuid.uuid4().hex}'
    yield value
    report = value.close(3)
    assert report.complete, report
    assert value._shutdown_session.worker is None
    assert value.tool_registry.work_gate.wait_idle(0)
    assert value.db.is_open is False


def task(runtime, name='fixture'):
    cap = runtime.supervisor.create_task(name)
    runtime.ledger.insert_task(TaskRecord(task_id=cap.task_id, request_id=name, input_mode='text', command_text='P06 owned fixture'))
    runtime.supervisor.start_task(cap.task_id)
    return cap


def registered(runtime, execute, timeout=1):
    runtime.tool_registry.register(ToolSpec(name='shutdown_probe', description='Owned fixture read',
        args_schema={'type': 'object'}, risk_class=RiskClass.READ, timeout_s=timeout,
        executor=execute, verifier=lambda result: VerifyResult(ok=True, method='state', detail='Inert readback')))
    route = RouteResult(route=RouteMode.FAST, reason='P06 fixture',
        plan=Plan(route=RouteMode.FAST, steps=[ToolCall(tool='shutdown_probe', arguments={}, purpose='Fixture')]))
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: route)


def reopened(runtime, cap):
    assert runtime.db.is_open is False
    with DbConnection(str(runtime.paths.db_path)) as db:
        row = ActivityQuery(db).task_by_id(cap.task_id)
        assert row['final_state'] == cap.state.value
        report = json.loads(ActivityQuery(db).cleanup_report_for_task(cap.task_id)['metadata_json'])
        assert report['entries'] == cap.outcome_details()['cleanup_evidence']
    return row


def test_idle_close_and_repeated_close_read_back_all_owners(runtime):
    cap = task(runtime)
    report = runtime.close()
    assert report.complete and report.code == 'CLOSED_VERIFIED'
    assert cap.stop_latch_set and cap.state == TaskState.STOPPED
    assert runtime._shutdown_session.worker is None
    assert runtime.tool_registry.work_gate.wait_idle(0)
    assert not runtime.tool_registry._worker_controllers and not runtime.tool_registry._idle_workers
    assert not runtime.db._writer_thread.is_alive()
    row = reopened(runtime, cap)
    assert runtime.close() == report
    assert reopened(runtime, cap) == row


@pytest.mark.parametrize('entry', ['task', 'execute', 'registry', 'worker', 'ipc', 'voice'])
def test_shutdown_rejects_every_new_entry(runtime, entry):
    assert runtime.close().complete
    before = len(runtime.supervisor._tasks)
    if entry == 'task':
        with pytest.raises(TaskCancelledError):
            runtime.supervisor.create_task('after-close')
    elif entry == 'execute':
        with pytest.raises(TaskCancelledError):
            runtime.orchestrator.execute(PlumaRequest(input_mode=InputMode.TEXT, text='fixture'))
    elif entry == 'registry':
        with pytest.raises(TaskCancelledError):
            runtime.tool_registry.execute('get_system_status', {})
    elif entry == 'worker':
        with pytest.raises(TaskCancelledError):
            runtime.tool_registry.get_worker('after-close')
    elif entry == 'ipc':
        reply = runtime.resident_core.handle_ipc_command({'command': 'execute', 'text': 'fixture'})
        assert reply['status'] == 'error' and 'shutting down' in reply['message']
    else:
        runtime.resident_core._on_voice_press()
    assert len(runtime.supervisor._tasks) == before


def test_all_latches_precede_capture_or_worker_drain(runtime):
    caps = [task(runtime, str(i)) for i in range(3)]
    seen = []
    class Capture:
        def cancel(self):
            seen.append([cap.stop_latch_set for cap in caps])
    runtime.resident_core.audio_capture = Capture()
    assert runtime.close().complete
    assert seen and all(all(values) for values in seen)


def test_close_during_direct_execution_waits_for_actual_handler(runtime):
    entered = threading.Event()
    def execute(args, context):
        entered.set()
        assert context.cancellation_token.wait_for_cancel(3)
        return ToolResult.failure('shutdown_probe', 'Fixture cancelled')
    registered(runtime, execute)
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(runtime.orchestrator.execute, PlumaRequest(input_mode=InputMode.TEXT, text='fixture'))
        assert entered.wait(3)
        report = runtime.close()
        result = call.result(3)
    assert report.complete
    cap = runtime.supervisor.get_task(result.task_id)
    assert result.final_state == cap.state.value and not result.success
    reopened(runtime, cap)


def test_timed_out_future_stays_owned_and_keeps_storage_open(runtime):
    entered, release = threading.Event(), threading.Event()
    def execute(args):
        entered.set()
        assert release.wait(4)
        return ToolResult.success('shutdown_probe', factual_message='Fixture released')
    registered(runtime, execute, timeout=0.02)
    try:
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=InputMode.TEXT, text='fixture'))
        assert entered.is_set() and runtime.tool_registry.work_gate.futures
        report = runtime.close(0.05)
        assert not report.complete and runtime.db.is_open
        assert runtime.tool_registry.work_gate.futures
    finally:
        release.set()
    assert runtime.close().complete
    assert runtime.tool_registry.work_gate.wait_idle(0)
    reopened(runtime, runtime.supervisor.get_task(result.task_id))


def test_pending_native_execute_ipc_drains_before_storage(runtime):
    entered = threading.Event()
    def execute(args, context):
        entered.set()
        assert context.cancellation_token.wait_for_cancel(3)
        return ToolResult.failure('shutdown_probe', 'Fixture cancelled')
    registered(runtime, execute)
    core = runtime.resident_core
    core.ipc.start()
    listener = core.ipc._thread
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(IpcClient(address=core.ipc.address).send_command, {'command': 'execute', 'text': 'fixture'}, 5)
        assert entered.wait(3)
        report = runtime.close()
        call.result(3)  # reply may be interrupted; history is authoritative
    assert report.complete and not listener.is_alive()
    assert not core.ipc._clients and core.ipc._listener is None
    cap = list(runtime.supervisor._tasks.values())[0]
    reopened(runtime, cap)


def test_idle_native_accept_is_woken_and_joined(runtime):
    runtime.resident_core.ipc.start()
    listener = runtime.resident_core.ipc._thread
    assert runtime.close().complete
    assert not listener.is_alive()
    assert runtime.resident_core.ipc._listener is None


def test_native_auth_wait_is_interrupted_and_joined(runtime):
    from multiprocessing.connection import Client
    core = runtime.resident_core
    core.ipc._read_timeout_s = 0.15
    core.ipc.start()
    conn = Client(core.ipc.address)
    try:
        assert len(conn.recv_bytes()) == 32  # no credential/body is sent
        owners = list(core.ipc._clients)
        assert owners
        report = runtime.close()
        assert report.complete and not runtime.db.is_open
        assert all(not owner.is_alive() for owner in owners)
    finally:
        conn.close()
    assert runtime.close().complete
    assert not core.ipc._clients


def test_shutdown_capture_discards_audio_and_reads_stream_closed(runtime):
    class Stream:
        closed = False
        def abort(self):
            pass
        def close(self):
            self.closed = True
    capture = AudioCapture()
    stream = Stream()
    capture._stream = stream
    capture._is_recording = True
    capture._buffer.extend(b'private fixture audio')
    runtime.resident_core.audio_capture = capture
    assert runtime.close().complete
    assert stream.closed and capture._stream is None and not capture.is_recording
    assert capture._buffer == b''


@pytest.mark.parametrize('failure', ['abort', 'close', 'readback'])
def test_capture_failure_retains_handle_and_storage(runtime, failure):
    class Stream:
        closed = False
        def abort(self):
            if failure == 'abort':
                raise OSError('token=not-for-report')
        def close(self):
            if failure == 'close':
                raise OSError('password=not-for-report')
    stream = Stream()
    capture = AudioCapture()
    capture._stream = stream
    capture._is_recording = True
    capture._buffer.extend(b'private fixture audio')
    runtime.resident_core.audio_capture = capture
    report = runtime.close()
    assert not report.complete and report.stage == 'capture'
    assert runtime.db.is_open and capture._stream is stream
    assert capture._buffer == b'' and 'not-for-report' not in str(report)
    stream.abort = lambda: None
    stream.close = lambda: setattr(stream, 'closed', True)
    assert runtime.close().complete


def test_slow_stage_is_single_owned_worker_and_resumes(runtime):
    entered, release = threading.Event(), threading.Event()
    calls = []
    class Capture:
        def cancel(self):
            calls.append(1)
            entered.set()
            assert release.wait(3)
    runtime.resident_core.audio_capture = Capture()
    try:
        start = time.monotonic()
        report = runtime.close(0.03)
        assert time.monotonic() - start < 0.5
        assert entered.is_set() and not report.complete and report.stage == 'capture'
        owner = runtime._shutdown_session.worker
        assert owner.is_alive() and runtime.db.is_open
        assert not runtime.close(0.02).complete
        assert runtime._shutdown_session.worker is owner and calls == [1]
    finally:
        release.set()
    assert runtime.close().complete
    assert not owner.is_alive()


def test_shutdown_during_rollback_keeps_storage_until_final_readback(runtime, monkeypatch):
    cap = task(runtime)
    entered, release = threading.Event(), threading.Event()
    original = runtime.rollback_engine.rollback_task
    def rollback(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)
    monkeypatch.setattr(runtime.rollback_engine, 'rollback_task', rollback)
    try:
        report = runtime.close(0.03)
        assert entered.is_set() and not report.complete
        assert cap.state == TaskState.ROLLING_BACK and cap.stop_latch_set
        assert runtime.db.is_open and runtime._shutdown_session.worker.is_alive()
    finally:
        release.set()
    assert runtime.close().complete
    reopened(runtime, cap)


def test_terminal_worker_reference_is_retried_before_storage(runtime):
    cap = task(runtime)
    worker = Worker(cap.task_id, fail=True)
    cap.worker_controller = worker
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert cap.state == TaskState.STOPPED_WITH_RESIDUAL and cap.worker_controller is worker
    report = runtime.close()
    assert not report.complete and report.stage == 'outcomes' and runtime.db.is_open
    worker.fail = False
    worker.absent = True
    assert runtime.close().complete
    assert cap.worker_controller is None and worker.calls >= 2
    reopened(runtime, cap)


def test_unpublished_preparation_stays_owned_until_verified(runtime):
    cap = TaskCapsule(request_id='unpublished')
    worker = Worker(cap.task_id, fail=True)
    cap.worker_controller = worker
    runtime.supervisor._retained_preparations[cap.task_id] = cap
    report = runtime.close()
    assert cap.stop_latch_set and not report.complete and runtime.db.is_open
    assert cap.worker_controller is worker
    worker.fail, worker.absent = False, True
    assert runtime.close().complete
    with DbConnection(str(runtime.paths.db_path)) as db:
        assert ActivityQuery(db).task_by_id(cap.task_id) is None
        assert ActivityQuery(db).cleanup_report_for_task(cap.task_id) is not None


def test_preparing_request_cannot_publish_after_shutdown(runtime, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    class PreparingJob(Job):
        def __init__(self, **kwargs):
            super().__init__()
            entered.set()
            assert release.wait(3)
    monkeypatch.setattr(job_object, 'WindowsJobObject', PreparingJob)
    with ThreadPoolExecutor(max_workers=1) as pool:
        preparing = pool.submit(runtime.supervisor.create_task, 'crossing-shutdown')
        assert entered.wait(3)
        try:
            report = runtime.close(0.03)
            assert not report.complete and runtime.db.is_open
        finally:
            release.set()
        with pytest.raises(TaskCancelledError):
            preparing.result(3)
    assert runtime.close().complete
    assert runtime.supervisor._tasks == {} and runtime.supervisor._preparing == 0


def test_terminal_ledger_failure_blocks_storage_and_retries(runtime, monkeypatch):
    cap = task(runtime)
    original = runtime.ledger.finalize_task
    monkeypatch.setattr(runtime.ledger, 'finalize_task', lambda *a, **k: (_ for _ in ()).throw(OSError('secret=not-for-report')))
    report = runtime.close()
    assert not report.complete and report.stage == 'outcomes' and runtime.db.is_open
    assert cap.terminal_persisted is False and cap.state == TaskState.STOPPED_WITH_RESIDUAL
    monkeypatch.setattr(runtime.ledger, 'finalize_task', original)
    assert runtime.close().complete
    reopened(runtime, cap)


def test_storage_writer_timeout_retains_connection_and_single_sentinel(runtime):
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        assert release.wait(4)
        return 1
    runtime.db._write_conn.create_function('p06_gate', 0, block)
    runtime.db.execute_write('SELECT p06_gate()', wait=False)
    assert entered.wait(3)
    try:
        result = runtime.close(0.03)
        assert not result.complete and runtime.db.is_open
        assert runtime.db._writer_thread.is_alive()
    finally:
        release.set()
    assert runtime.close().complete
    assert not runtime.db._writer_thread.is_alive()


@pytest.mark.parametrize('kind', ['single', 'batch', 'transaction'])
def test_storage_rejects_writes_behind_close_sentinel(runtime, kind):
    runtime.db._closing = True  # deterministic close-admission boundary
    try:
        with pytest.raises(RuntimeError, match='shutting down'):
            if kind == 'single':
                runtime.db.execute_write('SELECT 1')
            elif kind == 'batch':
                runtime.db.execute_write_many('SELECT ?', [(1,)])
            else:
                runtime.db.execute_transaction([('SELECT 1', ())])
    finally:
        runtime.db._closing = False
    assert runtime.close().complete


def test_concurrent_close_has_single_stage_owner(runtime):
    cap = task(runtime)
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(lambda _: runtime.close(), range(3)))
    assert all(report.complete for report in reports)
    assert runtime._shutdown_session.worker is None
    reopened(runtime, cap)


def test_unknown_model_unload_is_not_clean_shutdown(runtime):
    lifecycle = SimpleNamespace(adapter=SimpleNamespace(is_loaded=True), shutdown=lambda: None)
    runtime.llm_lifecycle = lifecycle
    report = runtime.close()
    assert not report.complete and report.stage == 'planner' and runtime.db.is_open
    lifecycle.adapter.is_loaded = False
    assert runtime.close().complete


def test_late_callback_cannot_use_closed_storage(runtime):
    entered, release = threading.Event(), threading.Event()
    observed = []
    core = runtime.resident_core
    core.orchestrator = None
    def callback(req):
        entered.set()
        assert release.wait(3)
        observed.append(runtime.db.is_open)
        runtime.db.execute_read('SELECT 1')
    core.on_request_callback = callback
    with ThreadPoolExecutor(max_workers=1) as pool:
        call = pool.submit(core.handle_ipc_command, {'command': 'execute', 'text': 'fixture'})
        assert entered.wait(3)
        try:
            report = runtime.close(0.03)
            assert not report.complete and runtime.db.is_open
            assert core._entry_gate.active == 1
        finally:
            release.set()
        call.result(3)
    assert runtime.close().complete and observed == [True]


def test_admitted_late_capture_is_cancelled_after_handler_drain(runtime):
    entered, release = threading.Event(), threading.Event()
    core = runtime.resident_core
    class Capture:
        recording = False
        def start(self):
            entered.set()
            assert release.wait(3)
            self.recording = True
        def cancel(self):
            self.recording = False
    core.audio_capture = Capture()
    with ThreadPoolExecutor(max_workers=1) as pool:
        press = pool.submit(core._on_voice_press)
        assert entered.wait(3)
        try:
            result = runtime.close(0.03)
            assert not result.complete and runtime.db.is_open
        finally:
            release.set()
        press.result(3)
    assert runtime.close().complete
    assert core.audio_capture.recording is False
    cap = core._current_voice_capsule
    with DbConnection(str(runtime.paths.db_path)) as db:
        assert ActivityQuery(db).task_by_id(cap.task_id) is None
        journal = json.loads(ActivityQuery(db).cleanup_report_for_task(cap.task_id)['metadata_json'])
        assert journal['pre_execution_outcome']['final_state'] == cap.state.value
        assert journal['pre_execution_outcome']['stop_reason'] == 'user_stop'


def test_actual_writer_close_timeout_retains_read_connection(runtime):
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        assert release.wait(3)
        return 1
    runtime.db._write_conn.create_function('p06_close_gate', 0, block)
    runtime.db.execute_write('SELECT p06_close_gate()', wait=False)
    assert entered.wait(3)
    try:
        with pytest.raises(TimeoutError, match='writer remains active'):
            runtime.db.close(timeout_s=0.02)
        assert runtime.db.is_open and runtime.db._read_conn is not None
        assert runtime.db.execute_read_one('SELECT 1')[0] == 1
        queued = runtime.db._write_queue.qsize()
        with pytest.raises(TimeoutError):
            runtime.db.close(timeout_s=0.02)
        assert runtime.db._write_queue.qsize() == queued == 1
        with pytest.raises(RuntimeError, match='shutting down'):
            runtime.db.execute_transaction([('SELECT 1', ())])
    finally:
        release.set()
    runtime.db.close(timeout_s=2)
    assert not runtime.db.is_open and not runtime.db._writer_thread.is_alive()


def test_running_model_timer_is_retained_across_failed_close(runtime):
    entered, release = threading.Event(), threading.Event()
    timer = threading.Timer(0, lambda: (entered.set(), release.wait(3)))
    timer.start()
    assert entered.wait(3)
    lifecycle = SimpleNamespace(adapter=SimpleNamespace(is_loaded=False), _idle_timer=timer)
    lifecycle.shutdown = lambda: setattr(lifecycle, '_idle_timer', None)
    runtime.llm_lifecycle = lifecycle
    try:
        report = runtime.close(0.03)
        assert not report.complete and runtime.db.is_open
        assert timer in runtime._shutdown_timers
    finally:
        release.set()
    assert runtime.close().complete
    assert not timer.is_alive() and not runtime._shutdown_timers


def test_registry_futures_cancel_queued_work_without_losing_running_owner():
    gate = WorkGate()
    entered, release = threading.Event(), threading.Event()
    calls = []
    with ThreadPoolExecutor(max_workers=1) as pool:
        def block():
            entered.set()
            assert release.wait(3)
        running = gate.submit(pool, block, task_id='owned-task')
        assert entered.wait(3)
        queued = gate.submit(pool, lambda: calls.append(1), task_id='owned-task')
        try:
            gate.begin_shutdown()
            assert queued.cancelled() and not running.done()
            assert not gate.wait_idle(0)
            identity = gate.pending_futures()[0]
            assert identity['task_id'] == 'owned-task' and identity['command_class'] == 'tool'
            with pytest.raises(TaskCancelledError):
                gate.submit(pool, lambda: None)
        finally:
            release.set()
        running.result(3)
    assert gate.wait_idle(1) and not calls


def test_native_planner_timeout_future_is_owned_until_actual_exit(runtime):
    from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
    from pluma.brain.interface import PlannerTimeoutError
    entered, release = threading.Event(), threading.Event()
    class Backend:
        def generate(self, **kwargs):
            entered.set()
            assert release.wait(3)
            return '{}'
    cap = task(runtime)
    adapter = LlamaCppAdapter(custom_backend=Backend(), registry=runtime.tool_registry, inference_timeout_s=0.02)
    try:
        with pytest.raises(PlannerTimeoutError):
            adapter.plan('fixture', permitted_tool_specs=[{'name': 'get_system_status'}],
                         cancellation_token=cap.cancellation_token)
        assert entered.is_set()
        identity = runtime.tool_registry.work_gate.pending_futures()[0]
        assert identity['command_class'] == 'planner_inference' and identity['task_id'] == cap.task_id
        report = runtime.close(0.03)
        assert not report.complete and runtime.db.is_open
        assert cap.state in (TaskState.STOPPING, TaskState.ROLLING_BACK, TaskState.STOPPED_WITH_RESIDUAL)
        assert any(item.code == 'INPROCESS_WORK_PENDING' for item in cap.cleanup_evidence)
    finally:
        release.set()
    assert runtime.close().complete
    assert any(item.code == 'INPROCESS_WORK_EXITED' and item.verified for item in cap.cleanup_evidence)
    assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
    reopened(runtime, cap)


def test_native_planner_stop_interrupts_wait_and_never_returns_late_plan(runtime):
    from pluma.brain.interface import PlannerCancelledError
    from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
    from pluma.core.cancellation import StopReason

    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    outcome = []

    class Backend:
        def generate(self, **kwargs):
            entered.set()
            assert release.wait(3)
            return ('{"route":"SMART","mode":"direct","steps":'
                    '[{"tool":"get_system_status","arguments":{},"purpose":"fixture"}]}')

    cap = task(runtime, 'planner-stop')
    adapter = LlamaCppAdapter(custom_backend=Backend(), registry=runtime.tool_registry,
                              inference_timeout_s=2.0)

    def plan():
        try:
            outcome.append(adapter.plan(
                'fixture', permitted_tool_specs=[{'name': 'get_system_status'}],
                cancellation_token=cap.cancellation_token))
        except Exception as exc:
            outcome.append(exc)
        finally:
            returned.set()

    caller = threading.Thread(target=plan, name='test-planner-stop-caller')
    try:
        caller.start()
        assert entered.wait(2)
        assert cap.cancellation_token.cancel(StopReason.USER_STOP)
        assert returned.wait(0.25), 'planner did not return promptly after STOP'
        assert len(outcome) == 1 and isinstance(outcome[0], PlannerCancelledError)
        assert cap.owned_work
        assert any(not item['future'].done() for item in cap.owned_work.values())
        assert any(item['command_class'] == 'planner_inference'
                   and item['task_id'] == cap.task_id
                   for item in runtime.tool_registry.work_gate.pending_futures())
    finally:
        release.set()
        caller.join(2)
    assert not caller.is_alive()


def test_native_planner_stop_cancels_queued_generation_before_executor_entry(runtime, monkeypatch):
    import pluma.tools.registry as registry_module
    from pluma.brain.interface import PlannerCancelledError
    from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
    from pluma.core.cancellation import StopReason

    executor = ThreadPoolExecutor(max_workers=1)
    entered_blocker, release_blocker = threading.Event(), threading.Event()
    backend_started, returned = threading.Event(), threading.Event()
    outcome = []
    monkeypatch.setattr(registry_module, '_GLOBAL_TOOL_EXECUTOR', executor)
    blocker = executor.submit(lambda: (entered_blocker.set(), release_blocker.wait(3)))
    assert entered_blocker.wait(2)

    class Backend:
        def generate(self, **kwargs):
            backend_started.set()
            return '{"route":"SMART","mode":"direct","steps":[]}'

    cap = task(runtime, 'planner-stop-queued')
    adapter = LlamaCppAdapter(custom_backend=Backend(), registry=runtime.tool_registry,
                              inference_timeout_s=2.0)

    def plan():
        try:
            outcome.append(adapter.plan(
                'fixture', permitted_tool_specs=[{'name': 'get_system_status'}],
                cancellation_token=cap.cancellation_token))
        except Exception as exc:
            outcome.append(exc)
        finally:
            returned.set()

    caller = threading.Thread(target=plan, name='test-planner-stop-queued-caller')
    try:
        caller.start()
        deadline = time.monotonic() + 2
        while not cap.owned_work and time.monotonic() < deadline:
            time.sleep(0.005)
        assert cap.owned_work
        future = next(item['future'] for item in cap.owned_work.values())
        assert not future.running()
        assert cap.cancellation_token.cancel(StopReason.USER_STOP)
        assert returned.wait(0.25)
        assert len(outcome) == 1 and isinstance(outcome[0], PlannerCancelledError)
        assert future.cancelled()
    finally:
        release_blocker.set()
        blocker.result(timeout=2)
        caller.join(2)
        executor.shutdown(wait=True)
    assert not caller.is_alive()
    assert not backend_started.is_set()


def test_stop_during_smart_planning_is_reported_as_stop_and_executes_no_tool(runtime, monkeypatch):
    from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
    from pluma.core.cancellation import StopReason

    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    capsules, outcome = [], []

    class Backend:
        def generate(self, **kwargs):
            entered.set()
            assert release.wait(3)
            return ('{"route":"SMART","mode":"direct","steps":'
                    '[{"tool":"get_system_status","arguments":{},"purpose":"fixture"}]}')

    original_create = runtime.supervisor.create_task_capsule

    def capture_capsule(**kwargs):
        capsule = original_create(**kwargs)
        capsules.append(capsule)
        return capsule

    monkeypatch.setattr(runtime.supervisor, 'create_task_capsule', capture_capsule)
    adapter = LlamaCppAdapter(custom_backend=Backend(), registry=runtime.tool_registry,
                              inference_timeout_s=2.0)
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=adapter.plan)
    runtime.orchestrator._router = SimpleNamespace(route=lambda request: RouteResult(
        route=RouteMode.SMART, reason='blocked planner fixture'))

    def execute():
        try:
            outcome.append(runtime.orchestrator.execute(PlumaRequest.from_text('complex fixture request')))
        finally:
            returned.set()

    caller = threading.Thread(target=execute, name='test-smart-stop-caller')
    try:
        caller.start()
        assert entered.wait(2)
        assert len(capsules) == 1
        cap = capsules[0]
        reply = runtime.supervisor.request_stop(cap.task_id, wait_s=0.1)
        assert reply.tasks and reply.tasks[0].latch_acknowledged
        assert cap.cancellation_token.reason == StopReason.USER_STOP
        assert returned.wait(1), 'SMART route did not return after planner STOP'
        assert len(outcome) == 1
        assert outcome[0].final_state in ('STOPPED', 'STOPPED_WITH_RESIDUAL')
        assert outcome[0].error == 'Planning stopped by user request.'
        assert cap.tool_call_count == 0
        assert not outcome[0].steps
        assert any(item.code == 'INPROCESS_WORK_PENDING' for item in cap.cleanup_evidence)
    finally:
        release.set()
        caller.join(3)
    assert not caller.is_alive()


@pytest.mark.parametrize('stage', ['registry', 'outcomes', 'planner', 'voice', 'storage'])
def test_failed_shutdown_stage_does_not_skip_to_storage(runtime, monkeypatch, stage):
    mapping = {'registry': (runtime.tool_registry, 'close'), 'outcomes': (runtime.supervisor, 'finalize_shutdown'),
               'planner': (runtime.llm_lifecycle, 'shutdown'), 'voice': (runtime.voice_lifecycle, 'shutdown'),
               'storage': (runtime.db, 'close')}
    owner, name = mapping[stage]
    original = getattr(owner, name)
    calls = []
    def fail_once():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('password=not-for-report')
        return original()
    monkeypatch.setattr(owner, name, fail_once)
    report = runtime.close()
    assert not report.complete and report.stage == stage and report.code == 'STAGE_UNVERIFIED'
    assert runtime.db.is_open and 'not-for-report' not in str(report)
    assert runtime.close().complete
    assert calls == [1, 1]


def test_model_shutdown_blocks_new_timers_and_joins_existing(runtime):
    runtime.llm_lifecycle.idle_unload_seconds = 3600
    runtime.voice_lifecycle.idle_unload_seconds = 3600
    runtime.llm_lifecycle._schedule_idle_unload()
    runtime.voice_lifecycle._schedule_unload_timer()
    timers = runtime.llm_lifecycle._timers | runtime.voice_lifecycle._timers
    assert len(timers) == 2 and all(timer.is_alive() for timer in timers)
    assert runtime.close().complete
    assert all(not timer.is_alive() for timer in timers)
    runtime.llm_lifecycle._schedule_idle_unload()
    runtime.voice_lifecycle._schedule_unload_timer()
    assert runtime.llm_lifecycle._timers | runtime.voice_lifecycle._timers == timers
    assert not runtime._shutdown_timers


def test_shutdown_preserves_preexisting_resource(runtime):
    from pluma.core.task_supervisor import ResourceOwnership
    cap = task(runtime)
    class UserJob:
        def terminate(self, **kwargs):
            pytest.fail('Shutdown touched a preexisting user resource')
        def close(self):
            pytest.fail('Shutdown closed a preexisting user resource')
    cap.register_owned_resource('application', ResourceOwnership.PREEXISTING,
                                external_id='inert-user-fixture', metadata={'job_object': UserJob()})
    assert runtime.close().complete
    reopened(runtime, cap)


def test_real_runtime_shutdown_verifies_owned_tree_and_unrelated_survival(runtime, monkeypatch, tmp_path):
    import subprocess
    import sys
    from pluma.core.ownership import get_process_creation_time, subprocess_absent
    from tests.unit.test_worker_cancellation import OwnedProbe, EmptyArgs, await_file
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    # Approve only the named owned probe through the real policy engine.
    from tests.fixtures.policy import owned_fixture_policy
    runtime.tool_registry._policy_engine = owned_fixture_policy('worker_probe')
    runtime.tool_registry.register(ToolSpec(name='worker_probe', description='Owned process fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.HIGH, timeout_s=10,
        executor=OwnedProbe(str(tmp_path), descendant=True),
        verifier=lambda res: VerifyResult(ok=True, method='state', detail='Owned fixture')))
    cap = task(runtime)
    unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            executing = pool.submit(runtime.tool_registry.execute, 'worker_probe', {}, cap, runtime.ledger)
            await_file(tmp_path / 'entered', executing)
            child = int((tmp_path / 'child').read_text())
            created = get_process_creation_time(child)
            controller = cap.worker_controller
            root_pid = controller.worker_identity['pid']
            root_created = controller.worker_identity['creation_time']
            result = runtime.close()
            executing.result(3)
        assert result.complete and cap.stop_latch_set
        assert controller.verify_cleanup() is True and controller._proc is None
        assert subprocess_absent(root_pid, root_created) is True
        assert subprocess_absent(child, created) is True
        assert unrelated.poll() is None and not (tmp_path / 'late').exists()
        assert cap.job_object is None and cap.worker_controller is None
        reopened(runtime, cap)
    finally:
        if unrelated.poll() is None:
            unrelated.kill()
        unrelated.wait(timeout=3)


def test_host_waits_for_verified_close_before_claiming_clean_shutdown(tmp_path, monkeypatch):
    from pluma import app
    from pluma.core.shutdown import ShutdownResult
    calls = []
    class Host:
        def __init__(self, **kwargs):
            self.resident_core = SimpleNamespace(start=lambda: None)
        def close(self):
            calls.append(1)
            return ShutdownResult(len(calls) >= 3, 'closed' if len(calls) >= 3 else 'handlers', 'fixture')
    sleeps = []
    def clock(delay):
        sleeps.append(delay)
        if len(sleeps) == 1:
            raise KeyboardInterrupt
    monkeypatch.setattr(app, 'PlumaApplicationRuntime', Host)
    monkeypatch.setattr(app, 'time', SimpleNamespace(sleep=clock))
    monkeypatch.setattr(app.signal, 'signal', lambda *args: None)
    try:
        assert app.run_app(['--local-app-data', str(tmp_path / 'local'),
                            '--roaming-app-data', str(tmp_path / 'roaming')]) == 0
        assert len(calls) == 3 and len(sleeps) == 3
    finally:
        app.shutdown_logging()


def test_preparation_wrapper_preserves_global_stop_generation(runtime, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = runtime.supervisor._prepare_task_capsule
    def prepare(*args):
        entered.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(runtime.supervisor, '_prepare_task_capsule', prepare)
    with ThreadPoolExecutor(max_workers=1) as pool:
        creating = pool.submit(runtime.supervisor.create_task, 'straddled-stop')
        assert entered.wait(3)
        try:
            assert runtime.supervisor.stop_all_active_tasks() == []
        finally:
            release.set()
        with pytest.raises(TaskCancelledError):
            creating.result(3)
    assert runtime.supervisor._tasks == {} and runtime.supervisor._preparing == 0


def test_timed_out_capsule_cannot_be_pruned_while_future_remains(runtime):
    entered, release = threading.Event(), threading.Event()
    def execute(args):
        entered.set()
        assert release.wait(3)
        return ToolResult.success('shutdown_probe', factual_message='Fixture released')
    registered(runtime, execute, timeout=0.02)
    try:
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=InputMode.TEXT, text='fixture'))
        cap = runtime.supervisor.get_task(result.task_id)
        assert entered.is_set() and cap.owned_work
        assert cap.cleanup_pending and result.has_residual
        runtime.supervisor.prune_terminal_tasks(keep_count=0)
        assert runtime.supervisor.get_task(cap.task_id) is cap
        assert not runtime.close(0.02).complete and runtime.db.is_open
    finally:
        release.set()
    assert runtime.close().complete
    assert cap.owned_work == {}
    reopened(runtime, cap)
