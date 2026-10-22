"""Native SQLite tools: exact-call policy, journaling, readback and conflict undo."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from pluma.core import job_object
from pluma.memory.activity import ActivityQuery
from pluma.memory import tool_store
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_runtime_shutdown import NATIVE_JOB, runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file


def approved(runtime, monkeypatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    decisions = []
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: decisions.append(request) or ConfirmationResponse(approved=True))
    return decisions


def test_preference_native_write_read_undo_and_reopened_storage(runtime, monkeypatch):
    decisions = approved(runtime, monkeypatch)
    cap = task(runtime, 'save-public-preference')
    result = runtime.tool_registry.execute('save_preference', {'key': 'editor.theme', 'value': 'dark'}, cap, runtime.ledger)
    assert result.ok and result.verified and len(decisions) == 1
    assert result.private_context == {} and 'private_context' not in json.loads(result.model_dump_json())
    proof = cap.undo_stack[-1]
    assert proof['action'] == 'memory_write' and proof['before'] is None
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme')[0] == 'dark'
    read = runtime.tool_registry.execute('get_preference', {'key': 'editor.theme'}, cap, runtime.ledger)
    assert read.ok and read.verified and read.data == {'key': 'editor.theme', 'found': True, 'value': 'dark'}
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(rows) == 2 and all(row['verified'] for row in rows)
    assert runtime.rollback_engine.rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack).all_ok
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)
    worker = cap.worker_controller
    assert runtime.close(3).complete and worker.verify_cleanup()
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)


def test_memory_undo_refuses_newer_value_and_retains_both_evidence_and_edit(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    cap = task(runtime)
    saved = runtime.tool_registry.execute('save_preference', {'key': 'editor.theme', 'value': 'dark'}, cap, runtime.ledger)
    assert saved.ok
    proof = dict(cap.undo_stack[-1])
    second = tool_store.capture(str(runtime.paths.db_path), 'preference', 'editor.theme', 'owner-edit')
    tool_store.write(second)
    assert not RollbackRecipes().apply('memory_write', proof).ok
    assert cap.undo_stack[-1] == proof
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme')[0] == 'owner-edit'


def test_memory_capture_compare_and_swap_refuses_intervening_edit(runtime):
    path = str(runtime.paths.db_path)
    stale = tool_store.capture(path, 'preference', 'editor.theme', 'stale')
    winner = tool_store.capture(path, 'preference', 'editor.theme', 'winner')
    tool_store.write(winner)
    with pytest.raises(ValueError):
        tool_store.write(stale)
    assert tool_store.read(path, 'preference', 'editor.theme')[0] == 'winner'


@pytest.mark.parametrize('args', [
    {'key': 'password', 'value': 'private-memory-fixture'},
    {'key': 'editor.theme', 'value': {'token': 'private-memory-fixture'}},
    {'key': 'editor.theme', 'value': 'password=private-memory-fixture'},
    {'key': 'editor.theme', 'value': 'x' * 20000},
    {'key': 'editor.theme', 'value': True, 'storage_path': 'other.db'},
])
def test_private_or_unbounded_memory_is_rejected_before_policy_and_not_echoed(runtime, args):
    cap = task(runtime)
    with pytest.raises(ToolArgumentError) as caught:
        runtime.tool_registry.execute('save_preference', args, cap, runtime.ledger)
    assert 'private-memory-fixture' not in str(caught.value)
    assert cap.worker_controller is None and not cap.undo_stack
    assert ActivityQuery(runtime.db).actions_for_task(cap.task_id) == []


def test_save_without_exact_approval_never_captures_or_mutates(runtime):
    cap = task(runtime)
    result = runtime.tool_registry.execute('save_preference', {'key': 'editor.theme', 'value': 'dark'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED'
    assert cap.worker_controller is None and not cap.undo_stack
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)


def test_routine_native_save_and_same_task_run_with_distinct_action_indices(runtime, monkeypatch, tmp_path):
    decisions = approved(runtime, monkeypatch)
    path = tmp_path / 'owned.txt'
    path.write_text('owned routine fixture', encoding='utf-8')
    cap = task(runtime, 'owned-routine')
    steps = [
        {'tool': 'file_info', 'arguments': {'path': str(path)}, 'purpose': 'Inspect owned file'},
        {'tool': 'get_preference', 'arguments': {'key': 'editor.theme'}, 'purpose': 'Read preference'},
    ]
    saved = runtime.tool_registry.execute('create_routine', {'name': 'morning', 'steps': steps}, cap, runtime.ledger)
    assert saved.ok and saved.verified
    result = runtime.tool_registry.execute('run_routine', {'name': 'morning'}, cap, runtime.ledger)
    assert result.ok and result.verified and result.data['completed_steps'] == 2
    assert not cap.routine_active and cap.tool_call_count == 4
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert {r['tool'] for r in rows} == {'create_routine', 'run_routine', 'file_info', 'get_preference'}
    assert len({r['step_index'] for r in rows}) == 4
    assert {r['task_id'] for r in rows} == {cap.task_id}
    assert len(decisions) == 2
    assert cap.worker_controller.worker_identity['task_id'] == cap.task_id


@pytest.mark.parametrize('steps', [
    [{'tool': 'invented_tool', 'arguments': {}, 'purpose': 'Invalid'}],
    [{'tool': 'file_info', 'arguments': {'path': 'relative'}, 'purpose': 'Invalid'}],
    [{'tool': 'run_routine', 'arguments': {'name': 'loop'}, 'purpose': 'Nested'}],
    [{'tool': 'file_info', 'arguments': {}, 'target_ref': 'stale', 'purpose': 'Stale'}],
])
def test_routine_definition_validated_before_any_write(runtime, steps):
    cap = task(runtime)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('create_routine', {'name': 'invalid', 'steps': steps}, cap, runtime.ledger)
    assert cap.worker_controller is None


def test_routine_revalidates_corrupt_saved_definition_and_lifetime_limit(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    cap = task(runtime)
    state = tool_store.capture(str(runtime.paths.db_path), 'routine', 'imported', [
        {'tool': 'invented_tool', 'arguments': {}, 'purpose': 'Invalid'}])
    tool_store.write(state)
    result = runtime.tool_registry.execute('run_routine', {'name': 'imported'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'ROUTINE_FAILED'
    assert len(ActivityQuery(runtime.db).actions_for_task(cap.task_id)) == 1
    assert not cap.routine_active
    cap.tool_call_count = 20
    blocked = runtime.tool_registry.execute('get_preference', {'key': 'editor.theme'}, cap, runtime.ledger)
    assert not blocked.ok and blocked.error_code == 'TOOL_CALL_LIMIT'


def test_routine_denied_child_stops_before_later_steps(runtime, monkeypatch, tmp_path):
    decisions = approved(runtime, monkeypatch)
    cap = task(runtime)
    own_file = tmp_path / 'owned.txt'
    own_file.write_text('owned', encoding='utf-8')
    steps = [
        {'tool': 'save_preference', 'arguments': {'key': 'editor.theme', 'value': 'dark'}, 'purpose': 'Save preference'},
        {'tool': 'file_info', 'arguments': {'path': str(own_file)}, 'purpose': 'Must not run'},
    ]
    assert runtime.tool_registry.execute('create_routine', {'name': 'denied', 'steps': steps}, cap, runtime.ledger).ok
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: decisions.append(request) or ConfirmationResponse(approved=request.tool_name == 'run_routine'))
    result = runtime.tool_registry.execute('run_routine', {'name': 'denied'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'ROUTINE_STEP_FAILED'
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)
    assert all(r['tool'] != 'file_info' for r in ActivityQuery(runtime.db).actions_for_task(cap.task_id))
    assert not cap.routine_active


def test_stop_during_routine_keeps_same_owned_tree_and_starts_no_next_step(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    cap = task(runtime)
    steps = [
        {'tool': 'get_preference', 'arguments': {'key': 'editor.theme'}, 'purpose': 'Owned blocking fixture'},
        {'tool': 'file_info', 'arguments': {'path': str(tmp_path / 'must-not-read')}, 'purpose': 'Must not run'},
    ]
    assert runtime.tool_registry.execute('create_routine', {'name': 'stoppable', 'steps': steps}, cap, runtime.ledger).ok
    monkeypatch.setattr(runtime.tool_registry.lookup('get_preference'), 'executor', OwnedProbe(str(tmp_path)))
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'run_routine', {'name': 'stoppable'}, cap, runtime.ledger)
        try:
            await_file(tmp_path / 'entered', running)
            runtime.supervisor.request_stop(wait_s=.1)
            result = running.result(3)
            assert not result.ok and not result.verified
            assert runtime.supervisor.join_stop_operations(3)
            assert runtime.tool_registry.work_gate.wait_idle(3)
            assert cap.worker_controller is None or cap.worker_controller.verify_cleanup()
            assert not (tmp_path / 'late').exists() and not cap.routine_active
            assert all(r['tool'] != 'file_info' for r in ActivityQuery(runtime.db).actions_for_task(cap.task_id))
        finally:
            runtime.supervisor.stop_all_active_tasks()


def test_routine_stop_records_distinct_action_identity(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    cap = task(runtime)
    steps = [{'tool': 'stop_current', 'arguments': {}, 'purpose': 'Stop all tasks'}]
    assert runtime.tool_registry.execute('create_routine', {'name': 'stop_all', 'steps': steps}, cap, runtime.ledger).ok
    result = runtime.tool_registry.execute('run_routine', {'name': 'stop_all'}, cap, runtime.ledger)
    assert not result.ok and cap.stop_latch_set
    assert runtime.tool_registry.work_gate.wait_idle(3)
    assert runtime.supervisor.join_stop_operations(3)
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert {r['tool'] for r in rows} == {'create_routine', 'run_routine', 'stop_current'}
    assert len({r['step_index'] for r in rows}) == len(rows)


def test_json_schema_errors_are_private_and_missing_validator_fails_closed(monkeypatch):
    import builtins
    from pluma.tools.base import ToolSpec, ToolResult, RiskClass, VerifyResult
    from pluma.tools.registry import ToolRegistry
    spec = ToolSpec(name='schema_probe', description='Private schema fixture', risk_class=RiskClass.READ,
        timeout_s=1, args_schema={'type': 'object', 'properties': {'value': {'type': 'integer'}}, 'additionalProperties': False},
        executor=lambda args: ToolResult.success('schema_probe'),
        verifier=lambda result: VerifyResult(ok=True, method='fixture', detail='Inert fixture'))
    with pytest.raises(ToolArgumentError) as caught:
        ToolRegistry._validate_args(spec, {'value': 'password=private-schema-fixture'})
    assert 'private-schema-fixture' not in str(caught.value)
    original = builtins.__import__
    def importing(name, *args, **kwargs):
        if name == 'jsonschema':
            raise ImportError('Injected unavailable validator')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', importing)
    with pytest.raises(ToolArgumentError, match='validator is unavailable'):
        ToolRegistry._validate_args(spec, {'value': 'must-not-pass'})


def test_failed_smart_routine_never_replans_or_repeats_verified_prefix(runtime, monkeypatch, tmp_path):
    from types import SimpleNamespace
    from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
    from pluma.core.task_supervisor import TaskState
    approved(runtime, monkeypatch)
    owner = task(runtime, 'save-partial-routine')
    definition = [
        {'tool': 'save_preference', 'arguments': {'key': 'editor.theme', 'value': 'dark'}, 'purpose': 'Verified prefix'},
        {'tool': 'file_info', 'arguments': {'path': str(tmp_path / 'absent-owned-file')}, 'purpose': 'Fail after prefix'},
    ]
    assert runtime.tool_registry.execute('create_routine', {'name': 'partial', 'steps': definition}, owner, runtime.ledger).ok
    runtime.supervisor.finalize_task(owner.task_id, TaskState.SUCCEEDED)
    cap = task(runtime, 'run-partial-routine')
    plan = Plan(route=RouteMode.SMART, mode=PlanMode.MULTI_STEP, steps=[
        ToolCall(tool='run_routine', arguments={'name': 'partial'}, purpose='Run once')])
    replans = []
    execution = runtime.orchestrator._multi_step
    execution.planner = SimpleNamespace(plan=lambda **kwargs: replans.append('replan') or plan)
    result = execution.execute_plan(cap, plan, 'Run partial owned routine')
    assert result.final_state == TaskState.FAILED and result.replan_count == 0 and not replans
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert sum(row['tool'] == 'save_preference' for row in rows) == 1
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)
