"""P11 pre-state lifecycle: owned inert barriers and native Job workers only."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import threading
import time

import pytest

from pluma.core import job_object
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.memory.activity import ActivityQuery
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import WorkerRequest
from tests.unit.test_mutation_journal import EmptyArgs
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, task, reopened
from tests.unit.test_worker_cancellation import await_file, owned_noop


def register(registry, capture, execute, *, isolated=False, timeout=1):
    registry.register(ToolSpec(name='prestate_probe', description='Owned pre-state fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=timeout,
        process_isolated=isolated, undo_builder=capture, executor=execute,
        verifier=lambda result: VerifyResult(ok=result.ok, method='api', detail='Fixture readback.')))


def test_blocked_thread_capture_returns_before_release_and_remains_owned(runtime):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def capture(args):
        entered.set()
        assert release.wait(5)
        return {'action': 'fixture', 'previous': 1}
    def execute(args):
        calls.append('executor')
        return ToolResult.success('prestate_probe', factual_message='Inert fixture returned.')
    register(runtime.tool_registry, capture, execute, timeout=.15)
    cap = task(runtime, 'prestate-thread-deadline')
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'prestate_probe', {}, cap, runtime.ledger)
        try:
            assert entered.wait(2)
            # Observe before releasing capture, then drain even on old-code failure.
            returned = threading.Event()
            running.add_done_callback(lambda _: returned.set())
            bounded = returned.wait(.8)
            owned = list(cap.owned_work.values())
        finally:
            release.set()
        result = running.result(3)
    assert bounded, 'Pre-state capture blocked the caller beyond the tool deadline.'
    assert any(item['identity']['command_class'] == 'prestate' for item in owned)
    assert not result.ok and result.error_code == 'TOOL_TIMEOUT'
    assert cap.cancellation_token.reason == StopReason.TASK_TIMEOUT
    assert calls == [] and cap.undo_stack == []
    assert runtime.tool_registry.work_gate.wait_idle(2)
    actions = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(actions) == 1 and 'TOOL_TIMEOUT' in actions[0]['error_json']
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@dataclass
class NativeCapture:
    root: str
    block: bool = True

    def __call__(self, args):
        root = Path(self.root)
        (root / 'capture-entered').write_text(str(__import__('os').getpid()), encoding='utf-8')
        if self.block:
            time.sleep(30)
            (root / 'capture-late').touch()
        return {'action': 'fixture', 'previous': 1}


@dataclass
class NativeExecute:
    root: str

    def __call__(self, args, context):
        (Path(self.root) / 'executed').write_text(str(__import__('os').getpid()), encoding='utf-8')
        return ToolResult.success('prestate_probe', factual_message='Owned fixture observed.')


@pytest.mark.parametrize('stop', [True, False])
def test_native_capture_stop_or_deadline_drains_without_execution(runtime, monkeypatch, tmp_path, stop):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    register(runtime.tool_registry, NativeCapture(str(tmp_path)), NativeExecute(str(tmp_path)),
        isolated=True, timeout=2 if stop else 1)
    cap = task(runtime, 'prestate-native')
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    assert controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'prestate_probe', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)[0] == 'ok'
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'prestate_probe', {}, cap, runtime.ledger)
        try:
            await_file(tmp_path / 'capture-entered', running)
            assert int((tmp_path / 'capture-entered').read_text()) == controller.worker_identity['pid']
            if stop:
                cap.cancellation_token.cancel()
            try:
                result = running.result(3)
            except TaskCancelledError:
                assert stop
                result = None
        finally:
            if not running.done():
                cap.cancellation_token.cancel()
                controller.terminate_and_join()
    assert result is None or (not result.ok and result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT'))
    assert controller.verify_cleanup()
    assert not (tmp_path / 'executed').exists() and not (tmp_path / 'capture-late').exists()
    assert not cap.undo_stack


def test_native_capture_and_execution_reuse_same_owned_process(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    register(runtime.tool_registry, NativeCapture(str(tmp_path), block=False), NativeExecute(str(tmp_path)),
        isolated=True, timeout=6)
    cap = task(runtime, 'prestate-native-success')
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    controller = cap.worker_controller
    assert result.ok and result.verified
    assert (tmp_path / 'capture-entered').read_text() == (tmp_path / 'executed').read_text()
    assert int((tmp_path / 'executed').read_text()) == controller.worker_identity['pid']
    assert cap.undo_stack == [{'action': 'fixture', 'previous': 1}]
    assert len(ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)) == 1
    controller.terminate_and_join()
    assert controller.verify_cleanup()


def test_stop_retains_thread_capture_and_storage_until_actual_exit(runtime):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def capture(args):
        entered.set()
        assert release.wait(5)
        return {'action': 'fixture', 'previous': 1}
    register(runtime.tool_registry, capture, lambda args: calls.append('executor'), timeout=4)
    cap = task(runtime, 'prestate-thread-stop')
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'prestate_probe', {}, cap, runtime.ledger)
        try:
            assert entered.wait(2)
            cap.cancellation_token.cancel()
            with pytest.raises(TaskCancelledError):
                running.result(1)
            assert not runtime.tool_registry.work_gate.wait_idle(0)
            assert any(not item['future'].done() for item in cap.owned_work.values())
            report = runtime.close(.1)
            assert not report.complete and runtime.db.is_open
        finally:
            release.set()
    assert runtime.tool_registry.work_gate.wait_idle(2)
    assert runtime.close(3).complete
    assert not calls and not cap.undo_stack
    reopened(runtime, cap)
    with DbConnection(str(runtime.paths.db_path)) as db:
        assert not ActivityQuery(db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('bad', [None, {}, [], 'private-prestate-fixture'])
def test_invalid_capture_cannot_dispatch_or_publish_undo(runtime, bad):
    calls = []
    register(runtime.tool_registry, lambda args: bad, lambda args: calls.append('executor'))
    cap = task(runtime, 'prestate-invalid')
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
    assert not calls and not cap.undo_stack
    actions = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(actions) == 1 and 'private-prestate-fixture' not in str(actions)


def test_required_worker_never_falls_back_to_local_capture(runtime):
    calls = []
    register(runtime.tool_registry, lambda args: calls.append('capture'), NativeExecute('unused'), isolated=True)
    cap = task(runtime, 'prestate-serialization')
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'PROCESS_ISOLATION_FAILED'
    assert not calls and cap.worker_controller is None and not cap.undo_stack


def test_capture_exception_does_not_leak_or_execute(runtime):
    calls = []
    def capture(args):
        raise OSError('password=private-prestate-fixture')
    register(runtime.tool_registry, capture, lambda args: calls.append('executor'))
    cap = task(runtime, 'prestate-exception')
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
    assert 'private-prestate-fixture' not in str(result)
    assert not calls and not cap.undo_stack


def test_failed_capture_history_uses_bounded_ack_and_fails_closed(runtime, monkeypatch):
    calls, budgets = [], []
    register(runtime.tool_registry, lambda args: None, lambda args: calls.append('executor'))
    cap = task(runtime, 'prestate-history')
    def fail(record, *, _timeout_s=None):
        budgets.append(_timeout_s)
        raise TimeoutError('password=private-prestate-fixture')
    monkeypatch.setattr(runtime.ledger, 'insert_action', fail)
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'LEDGER_WRITE_FAILED'
    assert budgets == [2.0] and not calls and not cap.undo_stack
    assert 'private-prestate-fixture' not in str(result)


def test_capture_consumes_execution_budget(runtime):
    def capture(args):
        time.sleep(.25)
        return {'action': 'fixture', 'previous': 1}
    def execute(args):
        time.sleep(.35)
        return ToolResult.success('prestate_probe', factual_message='Inert delayed fixture returned.')
    register(runtime.tool_registry, capture, execute, timeout=.45)
    cap = task(runtime, 'prestate-budget')
    result = runtime.tool_registry.execute('prestate_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'TOOL_TIMEOUT'
    assert cap.cancellation_token.reason == StopReason.TASK_TIMEOUT
    assert cap.undo_stack[0]['action'] == 'pending_mutation'
    assert runtime.tool_registry.work_gate.wait_idle(2)
