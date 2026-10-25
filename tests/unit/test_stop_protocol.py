"""P08 receipts: real SQLite/native fixture pipes; inert cleanup failure seams."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from pluma.core.cancellation import TaskCancelledError
from pluma.core.cleanup import CleanupEvidence
from pluma.core.ipc import IpcClient
from pluma.core.stop_protocol import StopOperation, StopOutcome, StopReply, StopTaskOutcome
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback.engine import RollbackResult, RollbackStepResult
from pluma.tools.base import ToolResult
from tests.unit.test_runtime_shutdown import runtime, registered, task


def stop(runtime, cap=None):
    req = {'command': 'stop_task', 'task_id': cap.task_id} if cap else {'command': 'stop_all'}
    data = runtime.resident_core.handle_ipc_command(req)
    # Validate the actual wire form, including aggregates and strict booleans.
    return StopReply.model_validate_json(json.dumps(data))


def settled(runtime, cap):
    assert runtime.supervisor.join_stop_operations(3)
    reply = stop(runtime, cap)
    assert len(reply.tasks) == 1
    return reply, reply.tasks[0]


def persisted(runtime, cap, item):
    row = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    assert row['final_state'] == item.final_state == cap.state.value
    metadata = json.loads(ActivityQuery(runtime.db).cleanup_report_for_task(cap.task_id)['metadata_json'])
    assert metadata['entries'] == [e.model_dump() for e in item.cleanup_evidence]
    return row


@pytest.mark.parametrize('command', ['stop', 'STOP', 'stop_all', 'stop_task'])
def test_all_aliases_report_only_verified_clean_cancellation(runtime, command):
    cap = task(runtime)
    data = runtime.resident_core.handle_ipc_command({'command': command, 'task_id': cap.task_id})
    first = StopReply.model_validate_json(json.dumps(data))
    assert first.tasks[0].latch_acknowledged
    reply, item = settled(runtime, cap)
    assert item.outcome == StopOutcome.STOPPED and item.cleanup_verified
    assert item.completion_verified and item.terminal_persisted is True
    assert reply.stopped_tasks == [cap.task_id] and reply.stopped_count == 1
    persisted(runtime, cap, item)


def test_empty_global_stop_does_not_claim_any_cleaned_tasks(runtime):
    reply = stop(runtime)
    assert reply.status == 'ok' and reply.tasks == [] and reply.stopped_count == 0
    assert reply.latch_acknowledged_count == 0
    assert not runtime.supervisor._stop_operations and runtime.supervisor._global_stop_depth == 0


@pytest.mark.parametrize('value', [None, '', ' ', [], {}, 1, True, 'x' * 129])
def test_invalid_task_ids_are_typed_errors_without_global_stop(runtime, value):
    cap = task(runtime)
    data = runtime.resident_core.handle_ipc_command({'command': 'stop_task', 'task_id': value})
    reply = StopReply.model_validate_json(json.dumps(data))
    assert reply.status == 'error' and reply.error_code == 'INVALID_TASK_ID'
    assert reply.stopped_count == 0 and not reply.tasks and not cap.stop_latch_set


def test_unknown_task_does_not_claim_acknowledgement_or_clean_stop(runtime):
    data = runtime.resident_core.handle_ipc_command({'command': 'stop_task', 'task_id': 'unknown-fixture'})
    reply = StopReply.model_validate_json(json.dumps(data))
    assert reply.stopped_count == reply.latch_acknowledged_count == 0
    item = reply.tasks[0]
    assert item.outcome == StopOutcome.ERROR and item.error_code == 'TASK_NOT_FOUND'
    assert item.final_state is None and not item.latch_acknowledged


@pytest.mark.parametrize('state', [TaskState.SUCCEEDED, TaskState.FAILED, TaskState.ABORTED_BY_CRASH])
def test_terminal_tasks_are_not_relabelled_as_stopped(runtime, state):
    cap = task(runtime)
    runtime.supervisor.transition(cap.task_id, state)
    before = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    reply = stop(runtime, cap)
    item = reply.tasks[0]
    assert reply.stopped_count == reply.latch_acknowledged_count == 0
    assert item.final_state == state.value and not cap.stop_latch_set
    assert item.outcome == (StopOutcome.ERROR if state == TaskState.FAILED else StopOutcome.TERMINAL)
    assert ActivityQuery(runtime.db).task_by_id(cap.task_id) == before


def test_residual_and_partial_rollback_are_not_clean_stop(runtime):
    cap = task(runtime)
    cap.undo_stack.append({'action': 'fixture_inverse', 'non_undoable': False})
    runtime.supervisor._rollback_engine = SimpleNamespace(rollback_task=lambda **kw: RollbackResult(
        task_id=cap.task_id, all_ok=False, has_residual=True,
        steps_attempted=1, steps_succeeded=0, steps_failed=1,
        step_results=[RollbackStepResult(action='fixture_inverse', ok=False, message='Fixture refusal')]))
    stop(runtime, cap)
    reply, item = settled(runtime, cap)
    assert item.outcome == StopOutcome.RESIDUAL and item.has_residual
    assert item.final_state == 'STOPPED_WITH_RESIDUAL' and not item.cleanup_verified
    assert item.rollback_performed and item.rollback_success is False
    rollback = next(e for e in item.cleanup_evidence if e.kind == 'rollback')
    assert rollback.code == 'ROLLBACK_RESIDUAL' and rollback.identity['failed'] == 1
    assert reply.stopped_count == 0 and cap.undo_stack
    persisted(runtime, cap, item)


def test_irreversible_commit_remains_residual_on_repeated_stop(runtime):
    cap = task(runtime)
    cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
    stop(runtime, cap)
    first, item = settled(runtime, cap)
    assert item.outcome == StopOutcome.RESIDUAL and first.stopped_tasks == []
    row = persisted(runtime, cap, item)
    again = stop(runtime, cap)
    assert again == first and ActivityQuery(runtime.db).task_by_id(cap.task_id) == row
    assert not runtime.supervisor._stop_operations


def test_blocked_cleanup_acknowledges_latch_and_retains_shutdown_owner(runtime, monkeypatch):
    first, second = task(runtime, 'first'), task(runtime, 'second')
    entered, release = threading.Event(), threading.Event()
    cleanup = runtime.supervisor._cleanup_stopped_task
    def blocked(cap, *args, **kwargs):
        assert first.stop_latch_set and second.stop_latch_set
        entered.set()
        assert release.wait(4)
        return cleanup(cap, *args, **kwargs)
    monkeypatch.setattr(runtime.supervisor, '_cleanup_stopped_task', blocked)
    try:
        reply = stop(runtime)
        assert entered.is_set()
        assert reply.latch_acknowledged_count == 2 and reply.stopped_count == 0
        assert all(t.outcome == StopOutcome.PENDING and t.cleanup_in_progress for t in reply.tasks)
        operations = list(runtime.supervisor._stop_operations.values())
        assert len(operations) == 1 and operations[0].thread.is_alive()
        repeat = stop(runtime, second)
        assert repeat.stopped_count == 0 and len(runtime.supervisor._stop_operations) == 1
        repeated_global = stop(runtime)
        assert repeated_global.stopped_count == 0 and repeated_global.latch_acknowledged_count == 2
        assert runtime.supervisor._global_stop_depth == 1
        with pytest.raises(TaskCancelledError):
            runtime.supervisor.create_task('cannot_cross_global_stop')
        assert not runtime.close(.03).complete and runtime.db.is_open
    finally:
        release.set()
    assert runtime.close(3).complete
    assert not operations[0].thread.is_alive() and not runtime.supervisor._stop_operations


def test_cleanup_exception_is_error_with_actual_nonterminal_state(runtime, monkeypatch):
    cap = task(runtime)
    transition = runtime.supervisor._transition
    def fail(cap, state):
        transition(cap, state)
        if state == TaskState.ROLLING_BACK:
            raise RuntimeError('private fixture cleanup failure')
    monkeypatch.setattr(runtime.supervisor, '_transition', fail)
    stop(runtime, cap)
    reply, item = settled(runtime, cap)
    assert item.outcome == StopOutcome.ERROR and item.error_code == 'STOP_CLEANUP_ERROR'
    assert item.final_state == 'ROLLING_BACK' and not item.completion_verified
    assert reply.stopped_tasks == [] and item.latch_acknowledged
    report = ActivityQuery(runtime.db).cleanup_report_for_task(cap.task_id)
    assert 'STOP_CLEANUP_ERROR' in report['metadata_json'] and 'private' not in reply.model_dump_json()
    assert not runtime.close(.03).complete and runtime.db.is_open
    # The fixture owner releases its injected broken boundary explicitly.
    monkeypatch.setattr(runtime.supervisor, '_transition', transition)
    # No tool or undo ran in this fixture. Publish the actual residual state
    # through the normal supervisor transition and real ledger readback.
    runtime.supervisor.transition(cap.task_id, TaskState.STOPPED_WITH_RESIDUAL)


def test_persistence_failure_cannot_be_verified_clean_stop(runtime, monkeypatch):
    cap = task(runtime)
    finalize = runtime.ledger.finalize_task
    def denied(*args, **kwargs): raise OSError('private SQLite failure')
    monkeypatch.setattr(runtime.ledger, 'finalize_task', denied)
    stop(runtime, cap)
    reply, item = settled(runtime, cap)
    assert reply.stopped_count == 0 and item.terminal_persisted is False
    assert item.outcome == StopOutcome.RESIDUAL and item.has_residual
    assert not runtime.close(.03).complete and runtime.db.is_open
    monkeypatch.setattr(runtime.ledger, 'finalize_task', finalize)


def test_locked_outcome_owner_returns_pending_without_waiting(runtime):
    cap = task(runtime)
    entered, release = threading.Event(), threading.Event()
    def hold():
        with runtime.supervisor._lock:
            entered.set()
            assert release.wait(4)
    with ThreadPoolExecutor(1) as pool:
        held = pool.submit(hold)
        assert entered.wait(2)
        try:
            reply = stop(runtime, cap)
            item = reply.tasks[0]
            assert item.latch_acknowledged and item.outcome == StopOutcome.PENDING
            assert item.error_code == 'EVIDENCE_BUSY' and reply.stopped_count == 0
        finally:
            release.set()
        held.result(2)
    _, item = settled(runtime, cap)
    assert item.outcome == StopOutcome.STOPPED


def test_repeated_concurrent_requests_do_not_duplicate_cleanup(runtime, monkeypatch):
    cap = task(runtime)
    calls = []
    original = runtime.supervisor._cleanup_stopped_task
    def counted(*args, **kwargs):
        calls.append(args[0].task_id)
        return original(*args, **kwargs)
    monkeypatch.setattr(runtime.supervisor, '_cleanup_stopped_task', counted)
    with ThreadPoolExecutor(8) as pool:
        replies = list(pool.map(lambda _: stop(runtime, cap), range(12)))
    reply, item = settled(runtime, cap)
    assert calls == [cap.task_id] and item.outcome == StopOutcome.STOPPED
    assert all(r.stopped_count == 0 or r.tasks[0].outcome == StopOutcome.STOPPED for r in replies)
    persisted(runtime, cap, item)


def test_published_operation_is_not_reaped_before_thread_start(runtime, monkeypatch):
    cap = task(runtime)
    entered, release = threading.Event(), threading.Event()
    original = StopOperation.start
    def delayed(self, run):
        entered.set()
        assert release.wait(3)
        original(self, run)
    monkeypatch.setattr(StopOperation, 'start', delayed)
    with ThreadPoolExecutor(1) as pool:
        call = pool.submit(stop, runtime, cap)
        assert entered.wait(2)
        try:
            assert not runtime.supervisor.join_stop_operations(0)
            reply = stop(runtime, cap)
            assert reply.tasks[0].outcome == StopOutcome.PENDING
            assert len(runtime.supervisor._stop_operations) == 1
        finally:
            release.set()
        call.result(3)
    assert settled(runtime, cap)[1].outcome == StopOutcome.STOPPED


def test_native_authenticated_stop_remains_independent_of_execute(runtime):
    entered, release = threading.Event(), threading.Event()
    calls = []
    def execute(args):
        calls.append('started')
        entered.set()
        assert release.wait(4)
        return ToolResult.success(tool='shutdown_probe')
    registered(runtime, execute, timeout=5)
    core = runtime.resident_core
    core.ipc.start()  # fixture pipe/key only; no resident hotkey or capture start
    with ThreadPoolExecutor(1) as pool:
        client = IpcClient(address=core.ipc.address, require_auth=True)
        running = pool.submit(client.send_command, {'command': 'execute', 'text': 'owned fixture'})
        assert entered.wait(2)
        try:
            reply = StopReply.model_validate_json(json.dumps(
                IpcClient(address=core.ipc.address, require_auth=True).send_command({'command': 'STOP'})))
            assert reply.latch_acknowledged_count == 1 and reply.stopped_count == 0
            assert reply.tasks[0].outcome in (StopOutcome.PENDING, StopOutcome.RESIDUAL)
            assert reply.tasks[0].latch_acknowledged
        finally:
            release.set()
        result = running.result(3)
    assert calls == ['started'] and result['final_state'].startswith('STOPPED')
    assert runtime.supervisor.join_stop_operations(3)


def test_no_ledger_cannot_prove_clean_stop(runtime):
    cap = task(runtime)
    ledger = runtime.supervisor._ledger
    runtime.supervisor._ledger = None
    try:
        stop(runtime, cap)
        _, item = settled(runtime, cap)
        assert item.outcome == StopOutcome.ERROR and item.error_code == 'TERMINAL_HISTORY_UNVERIFIED'
        assert item.final_state == 'STOPPED' and item.terminal_persisted is None
    finally:
        runtime.supervisor._ledger = ledger
    # Real persistence is recovered by the existing shutdown outcome stage.
    assert runtime.close().complete


def test_thread_start_failure_keeps_claimed_task_unverified(runtime, monkeypatch):
    cap = task(runtime)
    original = threading.Thread.start
    def denied(self):
        if self.name.startswith('PlumaStop:'):
            raise RuntimeError('private native thread failure')
        return original(self)
    monkeypatch.setattr(threading.Thread, 'start', denied)
    reply = stop(runtime, cap)
    item = reply.tasks[0]
    assert item.outcome == StopOutcome.ERROR and item.error_code == 'STOP_START_FAILED'
    assert item.latch_acknowledged and not item.completion_verified and reply.stopped_count == 0
    assert runtime.supervisor.join_stop_operations(0)
    monkeypatch.setattr(threading.Thread, 'start', original)
    runtime.supervisor.transition(cap.task_id, TaskState.STOPPED_WITH_RESIDUAL)


def test_uncommitted_terminal_event_is_pending(runtime):
    cap = task(runtime)
    stop(runtime, cap)
    assert runtime.supervisor.join_stop_operations(3)
    cap.terminal_ready.clear()  # injected interruption before terminal publication
    try:
        reply = stop(runtime, cap)
        assert reply.stopped_count == 0 and reply.tasks[0].outcome == StopOutcome.PENDING
        assert not reply.tasks[0].completion_verified
    finally:
        cap.terminal_ready.set()


def test_strict_wire_rejects_string_boolean_in_cleanup():
    raw = StopReply().wire()
    raw['tasks'] = [dict(task_id='fixture', outcome='residual', latch_acknowledged=True,
        cleanup_evidence=[dict(resource_id='fixture', kind='worker', code='UNVERIFIED', verified='false')])]
    with pytest.raises(ValidationError):
        StopReply.model_validate_json(json.dumps(raw))


def test_terminal_capsule_is_retained_until_cleanup_owner_returns(runtime, monkeypatch):
    cap = task(runtime)
    entered, release = threading.Event(), threading.Event()
    cleanup = runtime.supervisor._cleanup_stopped_task
    def before_return(*args, **kwargs):
        cleanup(*args, **kwargs)
        entered.set()
        assert release.wait(3)
    monkeypatch.setattr(runtime.supervisor, '_cleanup_stopped_task', before_return)
    try:
        reply = stop(runtime, cap)
        assert entered.is_set() and cap.terminal_ready.is_set()
        assert reply.tasks[0].outcome == StopOutcome.PENDING and reply.stopped_count == 0
        assert runtime.supervisor.prune_terminal_tasks(0) == 0
        assert runtime.supervisor.get_task(cap.task_id) is cap
    finally:
        release.set()
    assert settled(runtime, cap)[1].outcome == StopOutcome.STOPPED
    assert runtime.supervisor.prune_terminal_tasks(0) == 1
    assert stop(runtime, cap).tasks[0].error_code == 'TASK_NOT_FOUND'


def test_one_failed_cleanup_does_not_hide_another_task_outcome(runtime, monkeypatch):
    first, second = task(runtime, 'failed_fixture'), task(runtime, 'clean_fixture')
    transition = runtime.supervisor._transition
    def fail_first(cap, state):
        transition(cap, state)
        if cap is first and state == TaskState.ROLLING_BACK:
            raise RuntimeError('private boundary detail')
    monkeypatch.setattr(runtime.supervisor, '_transition', fail_first)
    reply = stop(runtime)
    assert runtime.supervisor.join_stop_operations(3)
    assert settled(runtime, first)[1].outcome == StopOutcome.ERROR
    clean_reply, clean = settled(runtime, second)
    assert clean.outcome == StopOutcome.STOPPED and clean_reply.stopped_tasks == [second.task_id]
    persisted(runtime, second, clean)
    assert first.stop_latch_set and second.stop_latch_set
    monkeypatch.setattr(runtime.supervisor, '_transition', transition)
    runtime.supervisor.transition(first.task_id, TaskState.STOPPED_WITH_RESIDUAL)


def test_reentrant_stop_observes_existing_cleanup_without_self_join(runtime):
    cap = task(runtime)
    nested = []
    engine = runtime.supervisor._rollback_engine
    def rollback(**kwargs):
        nested.append(stop(runtime, cap))
        return engine.rollback_task(**kwargs)
    runtime.supervisor._rollback_engine = SimpleNamespace(rollback_task=rollback)
    stop(runtime, cap)
    _, item = settled(runtime, cap)
    assert len(nested) == 1 and nested[0].tasks[0].outcome == StopOutcome.PENDING
    assert nested[0].stopped_count == 0 and item.outcome == StopOutcome.STOPPED
    persisted(runtime, cap, item)


@pytest.mark.parametrize('change', [dict(final_state='ROLLING_BACK'), dict(terminal_persisted=False),
    dict(completion_verified=False), dict(cleanup_in_progress=True), dict(has_residual=True),
    dict(latch_acknowledged=False), dict(cleanup_verified=False), dict(rollback_success=False), dict(error_code='STOP_CLEANUP_ERROR'),
    dict(cleanup_evidence=[CleanupEvidence(resource_id='unknown', kind='worker', code='UNVERIFIED')])])
def test_typed_clean_stop_requires_all_proof(change):
    values = dict(task_id='fixture', outcome=StopOutcome.STOPPED, final_state='STOPPED',
        latch_acknowledged=True, completion_verified=True, terminal_persisted=True, cleanup_verified=True)
    values.update(change)
    with pytest.raises(ValidationError):
        StopTaskOutcome(**values)


@pytest.mark.parametrize('field,value', [('stopped_count', 1), ('stopped_tasks', ['fake']),
    ('latch_acknowledged_count', 1), ('stopped_count', True), ('status', 'success')])
def test_typed_reply_rejects_fabricated_aggregate(field, value):
    with pytest.raises(ValidationError):
        StopReply(**{field: value})
