"""P11 postcondition lifetime and unknown-effect evidence, using owned fixtures."""
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import StopReason
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools import registry as runner
from pluma.tools.registry import WorkerRequest, WorkerResponse
from tests.unit.test_mutation_journal import EmptyArgs, setup, PartialRename
from tests.unit.test_runtime_shutdown import runtime, task, reopened
from tests.unit.test_worker_cancellation import await_file, owned_noop


def test_blocked_verifier_returns_before_release_and_keeps_pending_prestate(runtime):
    entered, release = threading.Event(), threading.Event()
    counter = [0]
    def execute(args):
        counter[0] += 1
        return ToolResult.success('verification_probe', factual_message='Inert counter changed.')
    def verify(result):
        entered.set()
        assert release.wait(5)
        return VerifyResult(ok=counter[0] == 1, method='state', detail='Inert counter read back.')
    runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Owned verifier fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=.2, executor=execute,
        undo_builder=lambda args: {'action': 'fixture', 'previous': counter[0]}, verifier=verify))
    cap = task(runtime, 'verification-thread-deadline')
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'verification_probe', {}, cap, runtime.ledger)
        try:
            assert entered.wait(2)
            done = threading.Event()
            running.add_done_callback(lambda _: done.set())
            bounded = done.wait(.8)
            pending = list(cap.undo_stack)
        finally:
            release.set()
        result = running.result(3)
    assert bounded, 'Verifier blocked the caller beyond the tool deadline.'
    assert counter == [1] and pending[0]['action'] == 'pending_mutation'
    assert not result.ok and not result.verified and result.error_code == 'TOOL_TIMEOUT'
    assert cap.undo_stack[0]['action'] == 'pending_mutation'
    assert runtime.tool_registry.work_gate.wait_idle(2)


@dataclass
class NativeVerifier:
    root: str
    mode: str = 'block'

    def __call__(self, result):
        root = Path(self.root)
        (root / 'verification-entered').write_text(str(os.getpid()), encoding='utf-8')
        if self.mode == 'block':
            time.sleep(30)
            (root / 'verification-late').touch()
        if self.mode == 'raise':
            raise OSError('password=private-verifier-fixture')
        if self.mode == 'invalid':
            return True
        actual = (root / 'after').read_bytes() == b'owned journal fixture' and not (root / 'before').exists()
        return VerifyResult(ok=actual and self.mode != 'false', method='api', detail='Owned file postcondition read back.')


def prepare(runtime, monkeypatch, root, *, mode='block', timeout=2, smart=False):
    setup(runtime, monkeypatch, root, finish='success', timeout=timeout)
    spec = runtime.tool_registry.lookup('journal_probe')
    monkeypatch.setattr(spec, 'verifier', NativeVerifier(str(root), mode))
    planner_calls = []
    if smart:
        plan = Plan(route=RouteMode.SMART, mode=PlanMode.MULTI_STEP, steps=[
            ToolCall(tool='journal_probe', arguments={}, purpose='Owned mutation'),
            ToolCall(tool='journal_probe', arguments={}, purpose='Must not execute after uncertain effect')])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
            route=RouteMode.SMART, reason='P11 verifier fixture', plan=plan))
        runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kw: planner_calls.append('plan') or plan)
    return planner_calls


def warmed(runtime):
    req = PlumaRequest.from_text('Owned verifier fixture')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    assert controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'journal_probe', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)[0] == 'ok'
    return req, cap, controller


def causes_before_completion(runtime, monkeypatch):
    causes = []
    original = runtime.ledger.finish_mutation
    def finish(row, action, *args, **kwargs):
        causes.append(runtime.supervisor.get_task(action.task_id).cancellation_token.reason)
        return original(row, action, *args, **kwargs)
    monkeypatch.setattr(runtime.ledger, 'finish_mutation', finish)
    return causes


@pytest.mark.parametrize('stop', [True, False])
def test_native_verifier_stop_or_timeout_preserves_unknown_effect_and_history(runtime, monkeypatch, tmp_path, stop):
    prepare(runtime, monkeypatch, tmp_path, timeout=2 if stop else 1)
    req, cap, controller = warmed(runtime)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'verification-entered', running)
            assert int((tmp_path / 'verification-entered').read_text()) == controller.worker_identity['pid']
            assert cap.undo_stack[0]['action'] == 'pending_mutation'
            if stop: runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done(): runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.success and result.final_state == ('STOPPED_WITH_RESIDUAL' if stop else 'FAILED')
    assert result.has_residual and controller.verify_cleanup()
    assert cap.cancellation_token.reason == (StopReason.USER_STOP if stop else StopReason.TASK_TIMEOUT)
    assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
    assert not (tmp_path / 'before').exists() and not (tmp_path / 'verification-late').exists()
    assert result.steps[0].result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert runtime.close(3).complete
    reopened(runtime, cap)
    with DbConnection(str(runtime.paths.db_path)) as db:
        actions = ActivityQuery(db).actions_for_task(cap.task_id)
        records = ActivityQuery(db).available_undo_records_for_task(cap.task_id)
        assert len(actions) == len(records) == 1 and not actions[0]['verified']
        assert json.loads(records[0]['undo_json'])['action'] == 'pending_mutation'


@pytest.mark.parametrize('smart', [False, True])
def test_timeout_stays_failed_when_history_acknowledgement_also_fails(runtime, monkeypatch, tmp_path, smart):
    planner_calls = prepare(runtime, monkeypatch, tmp_path, timeout=1, smart=smart)
    def fail(*a, **kw):
        raise TimeoutError('password=private-verifier-fixture')
    monkeypatch.setattr(runtime.ledger, 'finish_mutation', fail)
    req, cap, controller = warmed(runtime)
    result = runtime.orchestrator.execute(req, cap)
    assert not result.success and result.final_state == 'FAILED' and result.has_residual
    assert cap.cancellation_token.reason == StopReason.TASK_TIMEOUT
    assert result.steps[0].result.error_code == 'LEDGER_WRITE_FAILED'
    assert 'private-verifier-fixture' not in str(result)
    assert len(result.steps) == 1 and planner_calls == (['plan'] if smart else [])
    assert controller.verify_cleanup() and cap.undo_stack[0]['action'] == 'pending_mutation'
    assert runtime.close(3).complete
    reopened(runtime, cap)


@pytest.mark.parametrize('mode', ['false', 'raise', 'invalid'])
def test_failed_native_proof_cannot_replan_or_run_next_mutation(runtime, monkeypatch, tmp_path, mode):
    planner_calls = prepare(runtime, monkeypatch, tmp_path, mode=mode, timeout=6, smart=True)
    causes = causes_before_completion(runtime, monkeypatch)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned failed proof fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    assert not result.success and result.final_state == 'FAILED' and result.has_residual
    assert result.steps[0].result.error_code == 'POSTCONDITION_FAILED'
    assert len(result.steps) == 1 and planner_calls == ['plan']
    assert causes == [None] and cap.undo_stack[0]['action'] == 'pending_mutation'
    assert 'private-verifier-fixture' not in str(result)
    assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'


def test_successful_native_proof_uses_same_worker_and_one_verified_action(runtime, monkeypatch, tmp_path):
    prepare(runtime, monkeypatch, tmp_path, mode='success', timeout=6)
    req, cap, controller = warmed(runtime)
    causes = causes_before_completion(runtime, monkeypatch)
    pid = controller.worker_identity['pid']
    result = runtime.orchestrator.execute(req, cap)
    assert result.success and result.final_state == 'SUCCEEDED'
    assert int((tmp_path / 'verification-entered').read_text()) == pid
    action = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    records = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    assert len(action) == len(records) == 1 and action[0]['verified']
    assert causes == [None]
    assert cap.undo_stack[0]['action'] == 'rename_file' and controller.verify_cleanup()


@pytest.mark.parametrize('bad', ['untyped', 'wrong_tool', 'coerced_proof'])
def test_malformed_worker_proof_is_failure_not_fabricated_timeout(runtime, monkeypatch, tmp_path, bad):
    prepare(runtime, monkeypatch, tmp_path, mode='success', timeout=6)
    req, cap, controller = warmed(runtime)
    causes = causes_before_completion(runtime, monkeypatch)
    original = controller.execute_call
    def respond(executor, *args, **kwargs):
        if getattr(executor, 'func', None) is runner._check_postcondition:
            if bad == 'untyped': return 'ok', 'malformed proof'
            proof = {'ok': 'true' if bad == 'coerced_proof' else True, 'method': 'fixture', 'detail': 'Injected proof'}
            return 'ok', WorkerResponse(ToolResult.success('other_tool' if bad == 'wrong_tool' else 'journal_probe',
                data={'verification': proof}))
        return original(executor, *args, **kwargs)
    monkeypatch.setattr(controller, 'execute_call', respond)
    result = runtime.orchestrator.execute(req, cap)
    assert not result.success and result.final_state == 'FAILED' and result.has_residual
    assert result.steps[0].result.error_code == 'POSTCONDITION_FAILED'
    assert causes == [None] and controller.verify_cleanup()


def test_required_verifier_serialization_refuses_before_mutation(runtime, monkeypatch, tmp_path):
    prepare(runtime, monkeypatch, tmp_path, mode='success', timeout=6)
    calls = []
    monkeypatch.setattr(runtime.tool_registry.lookup('journal_probe'), 'verifier', lambda result: calls.append('verify'))
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned refused proof fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    assert not result.success and result.steps[0].result.error_code == 'PROCESS_ISOLATION_FAILED'
    assert (tmp_path / 'before').exists() and not (tmp_path / 'after').exists()
    assert not cap.undo_stack and not calls


def test_stop_retains_running_thread_verifier_and_storage_until_exit(runtime):
    entered, release = threading.Event(), threading.Event()
    def verify(result):
        entered.set()
        assert release.wait(5)
        return VerifyResult(ok=True, method='state', detail='Inert late proof.')
    runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Owned thread read fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=4,
        executor=lambda args: ToolResult.success('verification_probe', factual_message='Inert observation.'), verifier=verify))
    cap = task(runtime, 'verification-thread-stop')
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'verification_probe', {}, cap, runtime.ledger)
        try:
            assert entered.wait(2)
            cap.cancellation_token.cancel()
            result = running.result(1)
            assert not result.ok and not result.verified and result.error_code == 'TASK_CANCELLED'
            assert any(not item['future'].done() and item['identity']['command_class'] == 'verification'
                       for item in cap.owned_work.values())
            assert not runtime.tool_registry.work_gate.wait_idle(0)
            assert not runtime.close(.1).complete and runtime.db.is_open
        finally:
            release.set()
    assert runtime.tool_registry.work_gate.wait_idle(2)
    assert runtime.close(3).complete
    reopened(runtime, cap)


def test_stop_cancels_queued_verifier_without_late_entry(runtime, monkeypatch):
    occupied, release = threading.Event(), threading.Event()
    calls, blockers = [], []
    with ThreadPoolExecutor(1) as workers, ThreadPoolExecutor(1) as callers:
        def block():
            occupied.set()
            assert release.wait(5)
        def execute(args):
            blockers.append(workers.submit(block))
            return ToolResult.success('verification_probe', factual_message='Inert read returned.')
        def verify(result):
            calls.append('verified')
            return VerifyResult(ok=True, method='state', detail='Inert read proof.')
        runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Queued verifier fixture',
            args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=4, executor=execute, verifier=verify))
        monkeypatch.setattr(runner, '_GLOBAL_TOOL_EXECUTOR', workers)
        cap = task(runtime, 'verification-queued-stop')
        running = callers.submit(runtime.tool_registry.execute, 'verification_probe', {}, cap, runtime.ledger)
        try:
            assert occupied.wait(2)
            deadline = time.monotonic() + 2
            while not any(item['identity']['command_class'] == 'verification' for item in cap.owned_work.values()):
                assert time.monotonic() < deadline
                time.sleep(.005)
            cap.cancellation_token.cancel()
            result = running.result(1)
            assert not result.ok and result.error_code == 'TASK_CANCELLED'
        finally:
            release.set()
        for blocker in blockers: blocker.result(2)
    assert not calls and runtime.tool_registry.work_gate.wait_idle(2)


def test_stop_before_thread_proof_publication_cannot_upgrade_pending_state(runtime):
    cap = task(runtime, 'verification-late-proof')
    def verify(result):
        cap.cancellation_token.cancel()
        return VerifyResult(ok=True, method='state', detail='Inert late proof.')
    runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Late proof fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=2,
        executor=lambda args: ToolResult.success('verification_probe', factual_message='Inert mutation returned.'),
        undo_builder=lambda args: {'action': 'fixture', 'previous': 0}, verifier=verify))
    result = runtime.tool_registry.execute('verification_probe', {}, cap, runtime.ledger)
    assert not result.ok and not result.verified and result.error_code == 'TASK_CANCELLED'
    assert result.undo_record is None and cap.undo_stack[0]['action'] == 'pending_mutation'
    record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
    assert json.loads(record['undo_json'])['action'] == 'pending_mutation'


def test_admitted_thread_without_started_marker_keeps_prestate_on_stop(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='success', timeout=4)
    spec = runtime.tool_registry.lookup('journal_probe')
    monkeypatch.setattr(spec, 'process_isolated', False)
    admitted, release = threading.Event(), threading.Event()
    original = runner._invoke_executor
    def invoke(executor, args, context, admission, observation=None):
        if isinstance(executor, PartialRename):
            admission.admit_executor()
            admitted.set()
            assert release.wait(5)
            observation['started'] = True
            return executor(args, context)
        return original(executor, args, context, admission, observation)
    monkeypatch.setattr(runner, '_invoke_executor', invoke)
    cap = task(runtime, 'verification-admission-observation-race')
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'journal_probe', {}, cap, runtime.ledger)
        try:
            assert admitted.wait(2)
            cap.cancellation_token.cancel()
            result = running.result(1)
            assert not result.ok and result.error_code == 'TASK_CANCELLED'
            assert cap.undo_stack[0]['action'] == 'pending_mutation'
            assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
            assert not runtime.close(.1).complete and runtime.db.is_open
        finally:
            release.set()
    assert runtime.tool_registry.work_gate.wait_idle(2)
    assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
    assert not (tmp_path / 'before').exists()
    assert runtime.close(3).complete
    reopened(runtime, cap)
    with DbConnection(str(runtime.paths.db_path)) as db:
        actions = ActivityQuery(db).actions_for_task(cap.task_id)
        records = ActivityQuery(db).available_undo_records_for_task(cap.task_id)
        assert len(actions) == len(records) == 1 and not actions[0]['verified']
        assert json.loads(records[0]['undo_json'])['action'] == 'pending_mutation'


@dataclass
class UnhandledExecutor:
    timeout_error: bool

    def __call__(self, args, context):
        error = TimeoutError if self.timeout_error else OSError
        raise error('password=private-unhandled-fixture')


@pytest.mark.parametrize('isolated', [False, True])
@pytest.mark.parametrize('timeout_error', [False, True])
def test_unhandled_executor_error_is_private_and_not_a_deadline(runtime, monkeypatch, isolated, timeout_error):
    from pluma.core import job_object
    from tests.unit.test_runtime_shutdown import NATIVE_JOB
    from tests.unit.test_mutation_journal import verify_fixture
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Unhandled error fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=2, process_isolated=isolated,
        executor=UnhandledExecutor(timeout_error), verifier=verify_fixture))
    cap = task(runtime, 'verification-private-error')
    result = runtime.tool_registry.execute('verification_probe', {}, cap, runtime.ledger)
    assert not result.ok and not result.verified and result.error_code == 'TOOL_FAILED'
    assert cap.cancellation_token.reason is None
    actions = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert 'private-unhandled-fixture' not in str(result) + str(actions)


def test_successful_future_completion_racing_poll_timeout_is_not_an_error(runtime, monkeypatch):
    from tests.unit.test_mutation_journal import verify_fixture
    def execute(args):
        return ToolResult.success('verification_probe', factual_message='Inert completed read.')
    class CompletedAfterPoll(Future):
        first = True
        def result(self, timeout=None):
            if self.first:
                self.first = False
                raise TimeoutError
            return super().result(timeout)
    original = runner._GLOBAL_TOOL_EXECUTOR
    class Pool:
        def submit(self, fn, *args):
            if fn is runner._invoke_executor and args[0] is execute:
                future = CompletedAfterPoll()
                future.set_result(execute({}))
                return future
            return original.submit(fn, *args)
    monkeypatch.setattr(runner, '_GLOBAL_TOOL_EXECUTOR', Pool())
    runtime.tool_registry.register(ToolSpec(name='verification_probe', description='Completed poll fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=2, executor=execute, verifier=verify_fixture))
    cap = task(runtime, 'verification-completion-poll-race')
    result = runtime.tool_registry.execute('verification_probe', {}, cap, runtime.ledger)
    assert result.ok and result.verified and cap.cancellation_token.reason is None
