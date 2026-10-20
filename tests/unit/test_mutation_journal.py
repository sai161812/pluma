"""P11: retain evidence for an owned file effect before a tool returns."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core import job_object
from pluma.core.request import PlumaRequest
from pluma.core.task_supervisor import TaskState
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.memory.db import DbConnection
from pluma.rollback.engine import RollbackEngine
from pluma.policy.engine import PolicyEngine
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import WorkerRequest
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened, task
from tests.unit.test_worker_cancellation import await_file, owned_noop


class EmptyArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}


def prestate(args, *, root):
    return {'action': 'rename_file', 'original_path': str(Path(root) / 'before'),
            'new_path': str(Path(root) / 'after')}


@dataclass
class PartialRename:
    root: str
    finish: str = 'block'

    def __call__(self, args, context):
        root = Path(self.root)
        (root / 'before').rename(root / 'after')
        (root / 'entered').touch()
        if self.finish == 'block':
            time.sleep(30)
            (root / 'late').touch()
        if self.finish == 'fail':
            return ToolResult.failure('journal_probe', 'Injected failure after owned mutation.', 'PARTIAL_EFFECT')
        return ToolResult.success('journal_probe', factual_message='Owned fixture renamed.',
                                  verified=True, adapter_used='native_api')


def worker_undo_pop(args, context):
    context.undo_stack.pop()
    return ToolResult.success('undo_last', factual_message='Inert worker undo fixture returned.')


def setup(runtime, monkeypatch, root, finish='block', timeout=5):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    (root / 'before').write_bytes(b'owned journal fixture')
    runtime.tool_registry.register(ToolSpec(name='journal_probe', description='Owned partial file mutation fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=timeout, process_isolated=True,
        executor=PartialRename(str(root), finish), undo_builder=partial(prestate, root=str(root)),
        verifier=lambda result: VerifyResult(ok=result.ok, method='api', detail='Owned fixture readback.')))
    plan = Plan(route=RouteMode.FAST, steps=[ToolCall(tool='journal_probe', arguments={}, purpose='Owned mutation')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=RouteMode.FAST, reason='P11 owned journal fixture', plan=plan))


@pytest.mark.parametrize('stop', [True, False])
def test_partial_effect_has_prestate_before_stop_or_timeout(runtime, monkeypatch, tmp_path, stop):
    setup(runtime, monkeypatch, tmp_path, timeout=2 if stop else 1)
    req = PlumaRequest.from_text('Owned partial mutation fixture')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    status, _ = controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'journal_probe', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)
    assert status == 'ok'
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'entered', running)
            # Capture the observations before STOP; drain the owned worker even
            # if the assertions below expose the old missing-journal defect.
            before_stop = list(cap.undo_stack)
            available = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
            if stop:
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert before_stop and available, 'Partial effect had no durable pre-state before interruption.'
    assert not result.success and controller.verify_cleanup() is True
    assert result.final_state == ('STOPPED_WITH_RESIDUAL' if stop else 'FAILED')
    assert result.has_residual and cap.undo_stack
    assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
    assert not (tmp_path / 'before').exists() and not (tmp_path / 'late').exists()
    assert cap.undo_stack[0]['action'] == 'pending_mutation'
    assert cap.undo_stack[0]['pre_state'] == prestate({}, root=str(tmp_path))
    assert runtime.close(3).complete
    reopened(runtime, cap)
    with DbConnection(str(runtime.paths.db_path)) as db:
        records = ActivityQuery(db).available_undo_records_for_task(cap.task_id)
        assert len(records) == 1 and records[0]['rollback_attempted'] and not records[0]['rollback_ok']
        assert json.loads(records[0]['undo_json'])['pre_state'] == prestate({}, root=str(tmp_path))


def test_explicit_failure_after_effect_retains_pending_evidence(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='fail')
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned partial failure fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    assert result.final_state == 'FAILED' and not result.success and result.has_residual
    assert result.steps[0].result.error_code == 'PARTIAL_EFFECT'
    actions = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    records = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    assert len(actions) == len(records) == 1 and not actions[0]['verified']
    assert json.loads(records[0]['undo_json'])['action'] == 'pending_mutation'
    assert records[0]['rollback_attempted'] and not records[0]['rollback_ok']
    assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
    assert runtime.close(3).complete
    reopened(runtime, cap)


def test_rejected_preparation_is_not_a_usable_pending_inverse(tmp_path):
    from pluma.rollback.recipes import RollbackRecipes
    before, after = tmp_path / 'before', tmp_path / 'after'
    after.write_bytes(b'preserve unresolved fixture')
    outcome = RollbackRecipes().apply('pending_mutation', {
        'action': 'pending_mutation', 'tool': 'journal_probe', 'operation_id': 'fixture',
        'pre_state': {'action': 'rename_file', 'original_path': str(before), 'new_path': str(after)}})
    assert not outcome.ok and outcome.error == 'MUTATION_OUTCOME_UNKNOWN'
    assert after.read_bytes() == b'preserve unresolved fixture' and not before.exists()


def test_verified_success_upgrades_one_action_and_real_inverse(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned successful mutation fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    query = ActivityQuery(runtime.db)
    assert result.success and result.final_state == 'SUCCEEDED'
    actions = query.actions_for_task(cap.task_id)
    records = query.available_undo_records_for_task(cap.task_id)
    assert len(actions) == len(records) == 1 and actions[0]['verified']
    expected = prestate({}, root=str(tmp_path))
    assert json.loads(records[0]['undo_json']) == expected and cap.undo_stack == [expected]
    outcome = RollbackEngine(runtime.ledger).rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack)
    assert outcome.all_ok and outcome.steps_succeeded == 1 and not outcome.has_residual
    assert (tmp_path / 'before').read_bytes() == b'owned journal fixture' and not (tmp_path / 'after').exists()
    assert not cap.undo_stack and not query.available_undo_records_for_task(cap.task_id)
    assert runtime.close(3).complete
    reopened(runtime, cap)


@pytest.mark.parametrize('stage', ['action', 'undo', 'readback'])
def test_journal_preparation_failure_refuses_mutation(runtime, monkeypatch, tmp_path, stage):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    def fail(*args, **kwargs):
        raise OSError('password=private-journal-fixture')
    if stage == 'action': monkeypatch.setattr(runtime.ledger, 'insert_action', fail)
    if stage == 'undo': monkeypatch.setattr(runtime.ledger, 'insert_undo_record', fail)
    if stage == 'readback':
        original = runtime.ledger.prepare_mutation
        def prepare(*args):
            original(*args)
            raise OSError('password=private-journal-fixture')
        monkeypatch.setattr(runtime.ledger, 'prepare_mutation', prepare)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned refused mutation fixture'))
    tool = result.steps[0].result
    cap = runtime.supervisor.get_task(result.task_id)
    assert not result.success and result.final_state == 'FAILED'
    assert tool.error_code == 'MUTATION_JOURNAL_FAILED' and not tool.ok and not tool.verified
    assert 'private-journal-fixture' not in tool.model_dump_json()
    assert (tmp_path / 'before').read_bytes() == b'owned journal fixture'
    assert not (tmp_path / 'after').exists() and not (tmp_path / 'entered').exists()
    assert not runtime.tool_registry._worker_controllers and not cap.undo_stack


@pytest.mark.parametrize('after_commit', [False, True])
def test_lost_completion_ack_never_reports_audited_success(runtime, monkeypatch, tmp_path, after_commit):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    finish = runtime.ledger.finish_mutation
    def lost(*args, **kwargs):
        if after_commit:
            finish(*args, **kwargs)
        raise OSError('token=private-journal-fixture')
    monkeypatch.setattr(runtime.ledger, 'finish_mutation', lost)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned history failure fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    assert not result.success and result.final_state == 'FAILED'
    assert result.steps[0].result.error_code == 'LEDGER_WRITE_FAILED'
    assert 'private-journal-fixture' not in result.steps[0].result.model_dump_json()
    if after_commit:
        assert not cap.undo_stack and not result.has_residual
        assert (tmp_path / 'before').read_bytes() == b'owned journal fixture'
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    else:
        assert cap.undo_stack and result.has_residual
        assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
        record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
        assert json.loads(record['undo_json'])['action'] == 'pending_mutation'
    assert runtime.close(3).complete
    reopened(runtime, cap)


def test_atomic_completion_keeps_prepared_action_if_undo_update_fails(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    runtime.db.execute_write("""CREATE TRIGGER journal_completion_failure BEFORE UPDATE ON undo_records
        BEGIN SELECT RAISE(ABORT, 'Owned completion fixture failure'); END""")
    try:
        result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned atomic history fixture'))
        assert not result.success and result.steps[0].result.error_code == 'LEDGER_WRITE_FAILED'
        actions = ActivityQuery(runtime.db).actions_for_task(result.task_id)
        assert len(actions) == 1 and not actions[0]['verified']
        assert json.loads(actions[0]['error_json'])['code'] == 'MUTATION_OUTCOME_PENDING'
        record = ActivityQuery(runtime.db).available_undo_records_for_task(result.task_id)[0]
        assert json.loads(record['undo_json'])['action'] == 'pending_mutation'
        assert (tmp_path / 'after').read_bytes() == b'owned journal fixture'
    finally:
        runtime.db.execute_write('DROP TRIGGER journal_completion_failure')


def test_failed_verifier_retains_effect_and_does_not_emit_success_copy(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    spec = runtime.tool_registry.lookup('journal_probe')
    monkeypatch.setattr(spec, 'verifier', lambda result: VerifyResult(ok=False, method='api', detail='Injected contradiction.'))
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned contradictory verification fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    tool = result.steps[0].result
    assert not result.success and tool.error_code == 'POSTCONDITION_FAILED'
    assert not tool.verified and 'renamed' not in tool.factual_message.lower()
    assert result.has_residual and cap.undo_stack[0]['action'] == 'pending_mutation'


def test_sensitive_prestate_is_redacted_before_first_effect_history(runtime, monkeypatch, tmp_path):
    setup(runtime, monkeypatch, tmp_path, finish='fail')
    spec = runtime.tool_registry.lookup('journal_probe')
    def capture(args):
        return dict(prestate(args, root=str(tmp_path)), password='private-journal-fixture')
    monkeypatch.setattr(spec, 'undo_builder', capture)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned private prestate fixture'))
    cap = runtime.supervisor.get_task(result.task_id)
    query = ActivityQuery(runtime.db)
    records = query.available_undo_records_for_task(cap.task_id)
    assert records and 'private-journal-fixture' not in json.dumps(query.actions_for_task(cap.task_id) + records)
    assert json.loads(records[0]['undo_json'])['pre_state']['password'] == '[REDACTED]'
    assert cap.undo_stack[0]['pre_state']['password'] == 'private-journal-fixture'


@pytest.mark.parametrize('stage', ['prepare', 'finish'])
def test_smart_history_failure_never_replans_or_runs_next_step(runtime, monkeypatch, tmp_path, stage):
    setup(runtime, monkeypatch, tmp_path, finish='success')
    plan = Plan(route=RouteMode.SMART, mode=PlanMode.MULTI_STEP, steps=[
        ToolCall(tool='journal_probe', arguments={}, purpose='Owned mutation'),
        ToolCall(tool='journal_probe', arguments={}, purpose='Must not execute')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=RouteMode.SMART, reason='Owned journal fixture', plan=plan))
    calls = []
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: calls.append('planner') or plan)
    def fail(*args, **kwargs):
        raise OSError('Owned history failure')
    monkeypatch.setattr(runtime.ledger, 'prepare_mutation' if stage == 'prepare' else 'finish_mutation', fail)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Owned SMART journal failure fixture'))
    assert not result.success and result.final_state == 'FAILED' and len(result.steps) == 1
    assert calls == ['planner']  # initial plan only, never a replan
    assert result.steps[0].result.error_code == ('MUTATION_JOURNAL_FAILED' if stage == 'prepare' else 'LEDGER_WRITE_FAILED')


def test_failed_final_verifier_cannot_consume_worker_undo_snapshot(runtime, monkeypatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    cap = task(runtime, 'p11-worker-undo-verification')
    original = {'action': 'unrecorded_prestate', 'previous': 'owned fixture'}
    cap.undo_stack.append(original)
    cap.worker_controller = runtime.tool_registry.get_worker(cap.task_id)
    cap._tool_registry = runtime.tool_registry
    approvals = []
    def approve(request):
        approvals.append(request)
        return ConfirmationResponse(approved=True)
    runtime.tool_registry._policy_engine = PolicyEngine(
        confirmation_contract=CallbackConfirmationContract(approve))
    spec = runtime.tool_registry.lookup('undo_last')
    monkeypatch.setattr(spec, 'executor', worker_undo_pop)
    monkeypatch.setattr(spec, 'verifier', lambda result: VerifyResult(ok=False, method='state', detail='Injected contradiction.'))
    result = runtime.tool_registry.execute('undo_last', {}, cap, ledger=runtime.ledger)
    assert not result.ok and not result.verified and result.error_code == 'POSTCONDITION_FAILED'
    assert cap.undo_stack == [original]
    assert len(approvals) == 1 and approvals[0].task_id == cap.task_id
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert not row['verified'] and 'POSTCONDITION_FAILED' in row['error_json']
