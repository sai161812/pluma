"""P05 authoritative outcome projection using owned files, SQLite and inert tools.

No device/desktop/model acceptance is claimed. The transport case uses an owned
native authenticated pipe; rollback cases read real fixture files back.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import threading
import uuid

import pytest

from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.cleanup import CleanupEvidence
from pluma.core.ipc import IpcClient
from pluma.core.multi_step import MultiStepOrchestrator
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.resident import ResidentCore
from pluma.core.router import RouteResult
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.rollback.engine import RollbackEngine
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry
from tests.unit.test_cleanup_evidence import Job


def _inert_screen_observation(args, context):
    from datetime import datetime, timedelta, timezone
    from pluma.perception.element_refs import ScreenSnapshot, BoundingBox
    now = datetime.now(timezone.utc)
    snapshot = ScreenSnapshot(created_at=now, expires_at=now + timedelta(seconds=3),
        active_process='fixture.exe', active_window_title='Fixture',
        window_rect=BoundingBox(left=0, top=0, right=100, bottom=100), dpi_scale=1)
    context.snapshot_registry.register(snapshot)
    return ToolResult.success('inspect_window_controls', {'snapshot_id': snapshot.snapshot_id},
        'Inert semantic observation for terminal-state tests.', verified=True)


@pytest.fixture
def harness(tmp_path, monkeypatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', Job)
    db = DbConnection(str(tmp_path / 'history.db'))
    db.open()
    ledger = ActivityLedger(db)
    supervisor = TaskSupervisor(ledger=ledger, rollback_engine=RollbackEngine(ledger=ledger))
    registry = ToolRegistry()
    registry.register(ToolSpec(name='inspect_window_controls', description='Inert perception fixture',
        args_schema={'type': 'object'}, risk_class=RiskClass.READ, timeout_s=1,
        executor=_inert_screen_observation,
        verifier=lambda result: VerifyResult(ok=result.ok and result.verified,
            method='inert_fixture', detail='Terminal-state fixture observation.')))
    # Do not change the shared time module or physical adapters.
    original_stop = supervisor.stop_task
    monkeypatch.setattr(supervisor, 'stop_task', lambda tid, reason=StopReason.USER_STOP, grace_s=0:
                        original_stop(tid, reason, grace_s=0))
    yield SimpleNamespace(db=db, ledger=ledger, supervisor=supervisor, registry=registry, path=tmp_path / 'history.db')
    registry.close()
    for cap in supervisor._tasks.values():
        cap.close_resources(stopping=True)
    if db.is_open:
        db.close()


def request():
    return PlumaRequest(input_mode=InputMode.TEXT, text='P05 fixture read')


def register(h, executor):
    h.registry.register(ToolSpec(name='outcome_probe', description='Owned fixture',
        args_schema={'type': 'object'}, risk_class=RiskClass.READ, timeout_s=1,
        executor=executor, verifier=lambda *a: VerifyResult(ok=True, method="state", detail="Inert fixture readback")))


def plan(route):
    return Plan(route=route, steps=[ToolCall(tool='outcome_probe', arguments={}, purpose='Fixture only')])


def orchestrator(h, route, *, llm=None, steps=True):
    value = plan(route) if steps else None
    return Orchestrator(registry=h.registry, supervisor=h.supervisor, ledger=h.ledger,
        router=SimpleNamespace(route=lambda req: RouteResult(route=route, reason='P05 fixture', plan=value)),
        llm_manager=llm or SimpleNamespace(plan=lambda **kwargs: value))


def stored(h, cap, result):
    row = ActivityQuery(h.db).task_by_id(cap.task_id)
    report = json.loads(ActivityQuery(h.db).cleanup_report_for_task(cap.task_id)['metadata_json'])
    mirror = next(row for row in ActivityQuery(h.db).resources_for_task(cap.task_id) if row['resource_type'] == 'cleanup_report')
    assert result.final_state == row['final_state'] == cap.state.value
    assert result.terminal_persisted is True
    assert result.completion_verified is True
    assert result.cleanup_evidence == report['entries'] == json.loads(mirror['metadata_json'])['entries']
    assert result.has_residual == (not report['complete'])
    # Close/reopen real WAL storage; neither result objects nor memory are proof.
    h.db.close()
    with DbConnection(str(h.path)) as reopened:
        assert ActivityQuery(reopened).task_by_id(cap.task_id)['final_state'] == cap.state.value
        assert json.loads(ActivityQuery(reopened).cleanup_report_for_task(cap.task_id)['metadata_json']) == report
    h.db.open()
    return row, report


@pytest.mark.parametrize('route', list(RouteMode))
@pytest.mark.parametrize('effect', ['clean', 'irreversible', 'partial'])
def test_routes_stop_project_state_evidence_and_reopened_sqlite(harness, route, effect, tmp_path):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    before, moved = tmp_path / 'before.txt', tmp_path / 'moved.txt'
    moved.write_text('owned data')
    if effect == 'irreversible':
        cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
    elif effect == 'partial':
        # One real move can restore; the other deliberately conflicts with a
        # subsequent user file and must remain available for later inspection.
        before.write_text('user change')
        other = tmp_path / 'other-moved.txt'
        other.write_text('other owned data')
        cap.undo_stack.extend([
            {'action': 'move_file', 'source': str(before), 'destination': str(moved)},
            {'action': 'move_file', 'source': str(tmp_path / 'other.txt'), 'destination': str(other)},
        ])
    def execute(args):
        cap.cancellation_token.cancel()
        return ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True)
    register(h, execute)
    result = orchestrator(h, route).execute(req, cap)
    assert result.final_state == ('STOPPED' if effect == 'clean' else 'STOPPED_WITH_RESIDUAL')
    assert result.success is False and result.rollback_performed is True
    row, report = stored(h, cap, result)
    assert row['stop_reason'] == 'user_stop'
    if effect == 'partial':
        assert before.read_text() == 'user change' and moved.read_text() == 'owned data'
        assert (tmp_path / 'other.txt').read_text() == 'other owned data'
        rollback = next(item for item in report['entries'] if item['kind'] == 'rollback')
        assert rollback['identity']['attempted'] == 2
        assert rollback['identity']['succeeded'] == 1 and rollback['identity']['failed'] == 1
        assert len(cap.undo_stack) == 1 and result.rollback_success is False
    if effect == 'irreversible':
        assert any(item['code'] == 'NON_UNDOABLE_EFFECT_REMAINS' for item in report['entries'])
        assert cap.undo_stack and 'Residual' in result.user_message


@pytest.mark.parametrize('route', [RouteMode.FAST, RouteMode.SMART, RouteMode.SCREEN])
@pytest.mark.parametrize('cleanup_failure', [False, True])
def test_success_and_cleanup_failure_project_authoritative_state(harness, route, cleanup_failure):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    if cleanup_failure:
        cap.job_object.fail = 'query'
    register(h, lambda args: ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True))
    result = orchestrator(h, route).execute(req, cap)
    assert result.final_state == ('FAILED' if cleanup_failure else 'SUCCEEDED')
    assert result.success is (not cleanup_failure)
    if cleanup_failure:
        assert 'successfully' not in result.user_message
    stored(h, cap, result)
    if cap.job_object:
        cap.job_object.fail = None


def test_empty_fast_plan_is_finalized(harness):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    result = orchestrator(h, RouteMode.FAST, steps=False).execute(req, cap)
    assert result.final_state == 'FAILED'
    stored(h, cap, result)


@pytest.mark.parametrize('route', [RouteMode.SMART, RouteMode.SCREEN, RouteMode.DEEP])
def test_stop_during_failed_planning_preserves_residual(harness, route):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
    def failed(**kwargs):
        h.supervisor.stop_task(cap.task_id)
        raise RuntimeError('Planner cancelled')
    result = orchestrator(h, route, llm=SimpleNamespace(plan=failed), steps=False).execute(req, cap)
    assert result.final_state == 'STOPPED_WITH_RESIDUAL'
    stored(h, cap, result)


def test_precancelled_request_has_real_history_without_routing(harness):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    cap.cancellation_token.cancel()
    cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    assert result.final_state == 'STOPPED_WITH_RESIDUAL'
    row, _ = stored(h, cap, result)
    assert row['input_mode'] == 'text' and row['command_text'] == req.text


@pytest.mark.parametrize('requested', [TaskState.SUCCEEDED, TaskState.FAILED])
def test_stop_wins_at_last_step_commit_boundary(harness, monkeypatch, requested):
    h = harness
    cap = h.supervisor.create_task('race')
    h.ledger.insert_task(TaskRecord(task_id=cap.task_id, request_id=cap.request_id, input_mode='text', command_text='Fixture'))
    h.supervisor.start_task(cap.task_id)
    entered, release = threading.Event(), threading.Event()
    original = h.supervisor._transition
    def transition(candidate, state):
        if state == requested:
            entered.set()
            assert release.wait(3)
        return original(candidate, state)
    monkeypatch.setattr(h.supervisor, '_transition', transition)
    with ThreadPoolExecutor(max_workers=2) as pool:
        completing = pool.submit(h.supervisor.finalize_task, cap.task_id, requested)
        assert entered.wait(3)
        stopping = pool.submit(h.supervisor.stop_task, cap.task_id)
        assert cap.cancellation_token.wait_for_cancel(3)
        release.set()
        completing.result(5)
        stopping.result(5)
    assert cap.state == TaskState.STOPPED
    assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] == 'STOPPED'


@pytest.mark.parametrize('fault', ['before_commit', 'after_commit'])
@pytest.mark.parametrize('stopping', [False, True])
def test_persistence_failure_cannot_preserve_success_or_stale_history(harness, monkeypatch, fault, stopping):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    def execute(args):
        if stopping:
            cap.cancellation_token.cancel()
        return ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True)
    register(h, execute)
    original = h.ledger.finalize_task
    calls = []
    def finalize(*args, **kwargs):
        calls.append(kwargs['final_state'])
        if len(calls) == 1:
            if fault != 'before_commit':
                original(*args, **kwargs)
            raise TimeoutError('password=not-for-output')
        return original(*args, **kwargs)
    monkeypatch.setattr(h.ledger, 'finalize_task', finalize)
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    assert calls == (['STOPPED', 'STOPPED_WITH_RESIDUAL'] if stopping else ['SUCCEEDED', 'FAILED'])
    assert result.final_state == ('STOPPED_WITH_RESIDUAL' if stopping else 'FAILED') and result.success is False
    row, report = stored(h, cap, result)
    assert row['error_code'] == 'TERMINAL_PERSISTENCE_UNVERIFIED'
    assert 'not-for-output' not in json.dumps(report)
    assert any(item['code'] == 'TERMINAL_PERSISTENCE_UNVERIFIED' for item in result.cleanup_evidence)


def test_storage_outage_is_explicit_and_retry_does_not_repeat_cleanup(harness, monkeypatch):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    register(h, lambda args: ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True))
    original = h.ledger.finalize_task
    monkeypatch.setattr(h.ledger, 'finalize_task', lambda *a, **kw: (_ for _ in ()).throw(OSError('secret=not-for-output')))
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    assert result.final_state == 'FAILED' and result.terminal_persisted is False
    assert 'history could not be verified' in result.user_message
    assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] is None
    evidence = list(cap.cleanup_evidence)
    monkeypatch.setattr(h.ledger, 'finalize_task', original)
    h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    assert cap.state == TaskState.FAILED and cap.terminal_persisted is True
    assert cap.cleanup_evidence == evidence
    assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] == 'FAILED'


def test_repeated_finalization_preserves_timestamp_state_and_rollback(harness, monkeypatch):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
    register(h, lambda args: (cap.cancellation_token.cancel() or True) and ToolResult.failure('outcome_probe', 'Stopped'))
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    row, report = stored(h, cap, result)
    for state in [TaskState.SUCCEEDED, TaskState.FAILED, TaskState.STOPPED]:
        h.supervisor.finalize_task(cap.task_id, state)
        h.supervisor.stop_task(cap.task_id)
        assert ActivityQuery(h.db).task_by_id(cap.task_id) == row
        assert cap.outcome_details()['cleanup_evidence'] == report['entries']


def test_authenticated_native_execute_ipc_preserves_residual_fields(harness):
    h = harness
    def execute(args):
        cap = h.supervisor.get_active_tasks()[0]
        cap.undo_stack.append({'action': 'fixture_commit', 'non_undoable': True})
        cap.cancellation_token.cancel()
        return ToolResult.failure('outcome_probe', 'Stopped')
    register(h, execute)
    core = ResidentCore(config={'voice': {'required': False}}, supervisor=h.supervisor,
        orchestrator=orchestrator(h, RouteMode.FAST), ledger=h.ledger,
        ipc_address=rf'\\.\pipe\pluma_p05_{uuid.uuid4().hex}')
    core.ipc.start()
    try:
        reply = IpcClient(address=core.ipc.address).send_command({'command': 'execute', 'text': 'P05 fixture'}, timeout=5)
        assert reply['status'] == 'ok' and reply['success'] is False
        cap = h.supervisor.get_task(reply['task_id'])
        assert reply['final_state'] == cap.state.value == 'STOPPED_WITH_RESIDUAL'
        assert reply['terminal_persisted'] and reply['completion_verified'] and reply['has_residual']
        assert reply['cleanup_evidence'] == cap.outcome_details()['cleanup_evidence']
        history = IpcClient(address=core.ipc.address).send_command({'command': 'recent_tasks'})
        assert history['tasks'][0]['final_state'] == reply['final_state']
    finally:
        core.ipc.stop()


def test_terminal_readback_mismatch_degrades_and_reconciles(harness, monkeypatch):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    register(h, lambda args: ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True))
    original = h.db.execute_read_one
    reads = []
    def read(sql, params=()):
        if 't.final_state' in sql:
            reads.append(sql)
            if len(reads) == 1:
                return None  # actual transaction committed, readback unverified
        return original(sql, params)
    monkeypatch.setattr(h.db, 'execute_read_one', read)
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    assert len(reads) == 2 and result.final_state == 'FAILED'
    stored(h, cap, result)


def test_late_queued_terminal_write_cannot_overwrite_conservative_retry(harness, monkeypatch):
    h = harness
    cap = h.supervisor.create_task('late-writer')
    h.ledger.insert_task(TaskRecord(task_id=cap.task_id, request_id=cap.request_id, input_mode='text', command_text='Owned fixture'))
    h.supervisor.start_task(cap.task_id)
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        assert release.wait(3)
        return 1
    h.db._write_conn.create_function('p05_gate', 0, block)
    # Queue the terminal transactions behind a real blocked SQLite writer.
    h.db.execute_write('SELECT p05_gate()', wait=False)
    assert entered.wait(3)
    original = h.db.execute_transaction
    monkeypatch.setattr(h.db, 'execute_transaction', lambda statements, **kwargs:
                        original(statements, timeout_s=0.03))
    # Avoid the separate cleanup journal acknowledgement; terminal writes still
    # contain the complete real cleanup snapshot and its resource mirror.
    monkeypatch.setattr(h.supervisor, '_persist_cleanup_report', lambda cap: None)
    try:
        h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        assert cap.state == TaskState.FAILED and cap.terminal_persisted is False
        assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] is None
    finally:
        release.set()
    h.db.execute_write('SELECT 1', timeout_s=2)
    assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] == 'FAILED'
    report = json.loads(ActivityQuery(h.db).cleanup_report_for_task(cap.task_id)['metadata_json'])
    assert any(item['code'] == 'TERMINAL_PERSISTENCE_UNVERIFIED' for item in report['entries'])
    monkeypatch.setattr(h.db, 'execute_transaction', original)
    h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    assert cap.state == TaskState.FAILED and cap.terminal_persisted is True


def test_terminal_transaction_rolls_back_evidence_and_state_together(harness):
    h = harness
    h.ledger.insert_task(TaskRecord(task_id='atomic', request_id='atomic', input_mode='text', command_text='Owned fixture'))
    h.db.execute_write("""CREATE TRIGGER p05_fail_terminal BEFORE UPDATE OF final_state ON tasks
                         BEGIN SELECT RAISE(ABORT, 'fixture rejection'); END""")
    with pytest.raises(Exception, match='fixture rejection'):
        h.ledger.finalize_task('atomic', final_state='SUCCEEDED', completed_at='fixture',
                               stop_reason=None, error_code=None, entries=[])
    assert ActivityQuery(h.db).task_by_id('atomic')['final_state'] is None
    assert ActivityQuery(h.db).cleanup_report_for_task('atomic') is None
    assert ActivityQuery(h.db).resources_for_task('atomic') == []


def test_missing_history_row_is_not_successfully_persisted(harness):
    h = harness
    cap = h.supervisor.create_task('unrecorded')
    h.supervisor.start_task(cap.task_id)
    h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    assert cap.state == TaskState.FAILED and cap.terminal_persisted is False
    assert ActivityQuery(h.db).task_by_id(cap.task_id) is None
    assert cap.cleanup_pending


@pytest.mark.parametrize('route', [RouteMode.FAST, RouteMode.SMART, RouteMode.SCREEN])
def test_failed_routes_use_same_rollback_owner_and_persist_residuals(harness, route, tmp_path):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    src, dst = tmp_path / 'source', tmp_path / 'destination'
    src.write_text('user conflict')
    dst.write_text('owned moved file')
    cap.undo_stack.append({'action': 'move_file', 'source': str(src), 'destination': str(dst)})
    register(h, lambda args: ToolResult.failure('outcome_probe', 'Fixture failed'))
    result = orchestrator(h, route).execute(req, cap)
    assert result.final_state == 'FAILED' and result.has_residual
    assert result.rollback_performed and result.rollback_success is False
    assert src.read_text() == 'user conflict' and dst.read_text() == 'owned moved file'
    stored(h, cap, result)


def test_direct_multi_step_result_preserves_cleanup_failure(harness):
    h = harness
    cap = h.supervisor.create_task('direct-multi')
    h.ledger.insert_task(TaskRecord(task_id=cap.task_id, request_id=cap.request_id, input_mode='text', command_text='Owned fixture'))
    h.supervisor.start_task(cap.task_id)
    cap.job_object.fail = 'query'
    register(h, lambda args: ToolResult(ok=True, tool='outcome_probe', factual_message='Fixture read.', verified=True))
    result = MultiStepOrchestrator(registry=h.registry, supervisor=h.supervisor, ledger=h.ledger).execute_plan(cap, plan(RouteMode.SMART), 'Fixture')
    assert result.final_state == cap.state == TaskState.FAILED
    assert result.has_residual and result.terminal_persisted and result.completion_verified
    assert result.cleanup_evidence == cap.outcome_details()['cleanup_evidence']
    assert 'successfully' not in result.factual_summary
    assert ActivityQuery(h.db).task_by_id(cap.task_id)['final_state'] == 'FAILED'
    cap.job_object.fail = None


def test_nonterminal_cleanup_projection_never_claims_stopped(harness, monkeypatch):
    h = harness
    cap = h.supervisor.create_task('pending-cleanup')
    h.supervisor.start_task(cap.task_id)
    cap.cancellation_token.cancel()
    h.supervisor.transition(cap.task_id, TaskState.STOPPING)
    h.supervisor.transition(cap.task_id, TaskState.ROLLING_BACK)
    waits = []
    # Inert clock seam verifies the configured bound without orphaning a thread.
    monkeypatch.setattr(cap.terminal_ready, 'wait', lambda timeout: waits.append(timeout) or False)
    result = h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    assert waits == [5.0] and result.state == TaskState.ROLLING_BACK
    assert result.outcome_details()['completion_verified'] is False
    assert result.terminal_summary() == 'Task cleanup is still pending.'


def test_ledger_owner_mismatch_is_rejected(harness):
    h = harness
    with pytest.raises(ValueError, match='different ledger'):
        h.supervisor.bind_execution(SimpleNamespace())


def test_repeated_unavailable_finalization_does_not_grow_evidence(harness, monkeypatch):
    h = harness
    cap = h.supervisor.create_task('unavailable-repeat')
    h.supervisor.start_task(cap.task_id)
    monkeypatch.setattr(h.ledger, 'finalize_task', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('fixture')))
    h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    evidence = list(cap.cleanup_evidence)
    timestamp = cap.completed_at
    for _ in range(3):
        h.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        assert cap.cleanup_evidence == evidence
        assert cap.completed_at == timestamp and cap.state == TaskState.FAILED


def test_pending_multi_step_projection_returns_actual_nonterminal_state(harness, monkeypatch):
    from pluma.core.multi_step import MultiStepExecutionResult
    h = harness
    cap = h.supervisor.create_task('pending-route')
    h.supervisor.start_task(cap.task_id)
    cap.cancellation_token.cancel()
    h.supervisor.transition(cap.task_id, TaskState.STOPPING)
    h.supervisor.transition(cap.task_id, TaskState.ROLLING_BACK)
    orch = orchestrator(h, RouteMode.SMART)
    result = orch._finalize_multi_step_result(cap, request(), RouteResult(route=RouteMode.SMART, reason='Fixture'),
        MultiStepExecutionResult(task_id=cap.task_id, final_state=TaskState.ROLLING_BACK), 0)
    result = orch._project_result(cap, result)
    assert result.final_state == 'ROLLING_BACK' and not result.success
    assert result.completion_verified is False and result.terminal_persisted is None
    assert result.user_message == 'Task cleanup is still pending.'


def test_stop_finishing_between_history_insert_and_start_is_projected(harness, monkeypatch):
    h = harness
    req = request()
    cap = h.supervisor.create_task(req.request_id)
    original = h.ledger.insert_task
    def insert(record):
        original(record)
        h.supervisor.stop_task(cap.task_id)
    monkeypatch.setattr(h.ledger, 'insert_task', insert)
    result = orchestrator(h, RouteMode.FAST).execute(req, cap)
    assert result.final_state == 'STOPPED' and not result.success
    stored(h, cap, result)
