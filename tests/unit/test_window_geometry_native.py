"""Native geometry and conflict undo, operating only owned hidden windows."""
import json

import pytest

from pluma.adapters import window_geometry as native
from pluma.core.cancellation import CancellationToken
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_memory_tools import approved
from tests.unit.test_process_control_native import owned_target
from tests.unit.test_runtime_shutdown import runtime, task


def window_target(root, process):
    marker = json.loads((root / 'ready.json').read_text(encoding='utf-8'))
    assert marker['pid'] == process['pid'] and marker['hwnd'] > 0
    return dict(process, hwnd=marker['hwnd'])


def arguments(tool, target, before):
    return dict(target, **({'x': before['x'] + 17, 'y': before['y'] + 23} if tool == 'move_window'
                          else {'width': before['width'] + 57, 'height': before['height'] + 43}))


@pytest.mark.parametrize('tool', ['move_window', 'resize_window'])
def test_native_geometry_worker_readback_and_durable_manual_undo(runtime, monkeypatch, tmp_path, tool):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        before = native.observe(target)
        cap = task(runtime, 'owned-window-geometry')
        result = runtime.tool_registry.execute(tool, arguments(tool, target, before['geometry']), cap, runtime.ledger)
        assert result.ok and result.verified, result
        state = cap.undo_stack[-1]
        assert state['identity'] == before['identity'] and state['before'] == before['geometry']
        assert native.observe(target)['geometry'] == state['after']
        if tool == 'move_window':
            assert all(state['before'][key] == state['after'][key] for key in ('width', 'height'))
        else:
            assert all(state['before'][key] == state['after'][key] for key in ('x', 'y'))
        rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
        record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
        assert len(rows) == 1 and rows[0]['verified'] and json.loads(record['undo_json']) == state
        assert 'PLUMAOwnedProcessFixture' not in json.dumps(rows) + record['undo_json']
        assert result.private_context == {} and cap.worker_controller is not None
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        undo = runtime.tool_registry.execute('undo_last', {}, task(runtime, 'owned-window-undo'), runtime.ledger)
        assert undo.ok and undo.verified, undo
        assert native.observe(target) == before
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('tool', ['move_window', 'resize_window'])
def test_native_geometry_inverse_preserves_newer_owner_geometry(runtime, monkeypatch, tmp_path, tool):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        before = native.observe(target)
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, arguments(tool, target, before['geometry']), cap, runtime.ledger)
        assert result.ok
        original = cap.undo_stack[-1]
        newer = native.capture(arguments(tool, target, original['after']), tool)
        native.apply(newer)
        observed = native.observe(target)
        assert not RollbackRecipes().apply('window_geometry', original).ok
        assert native.observe(target) == observed
        # Mark the original task completed; its retained conflict record is not
        # a cleanup instruction against the still-running fixture window.
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


@pytest.mark.parametrize('mismatch', ['pid', 'creation_time'])
def test_native_window_mismatch_fails_before_mutation_journal(runtime, monkeypatch, tmp_path, mismatch):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        observed = native.observe(target)
        args = arguments('move_window', target, observed['geometry'])
        args[mismatch] += 1
        cap = task(runtime)
        result = runtime.tool_registry.execute('move_window', args, cap, runtime.ledger)
        assert not result.ok and not result.verified and result.error_code == 'UNDO_PRESTATE_FAILED'
        assert not cap.undo_stack and native.observe(target) == observed


def test_owner_geometry_change_between_capture_and_dispatch_is_preserved(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        initial = native.observe(target)['geometry']
        original = native.capture(arguments('move_window', target, initial), 'move_window')
        newer = native.capture(dict(target, x=initial['x'] + 51, y=initial['y'] + 61), 'move_window')
        native.apply(newer)
        with pytest.raises(ValueError, match='changed after capture'):
            native.apply(original)
        assert native.observe(target)['geometry'] == newer['after']


@pytest.mark.parametrize('tool,args', [
    ('move_window', {'hwnd': 0, 'pid': 1, 'creation_time': 1, 'x': 1, 'y': 2}),
    ('move_window', {'hwnd': 1, 'pid': 1, 'creation_time': 1, 'x': True, 'y': 2}),
    ('move_window', {'hwnd': 1, 'pid': 1, 'creation_time': 1, 'x': 1, 'y': 2, 'title': 'ignored'}),
    ('resize_window', {'hwnd': 1, 'pid': 1, 'creation_time': 1, 'width': 0, 'height': 2}),
    ('resize_window', {'hwnd': 1, 'pid': 1, 'creation_time': 1, 'width': 1, 'height': '2'}),
    ('resize_window', {'hwnd': 1, 'pid': 1, 'creation_time': 1, 'width': 32768, 'height': 2}),
])
def test_geometry_schema_precedes_policy_and_worker(runtime, monkeypatch, tool, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(tool, args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


def test_cancelled_geometry_does_not_change_target(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        before = native.observe(target)
        state = native.capture(arguments('move_window', target, before['geometry']), 'move_window')
        token = CancellationToken()
        token.cancel()
        with pytest.raises(Exception):
            native.apply(state, token)
        assert native.observe(target) == before


def geometry_diagnostic(args, context):
    from pluma.tools.base import ToolResult
    try:
        state = context.undo_stack[-1]['pre_state']
        native.apply(state, context.cancellation_token)
        return ToolResult.success(state['tool'], data={key: state[key] for key in ('hwnd', 'pid', 'creation_time', 'coordinate_space', 'after')},
            verified=True, adapter_used='native_window_api', factual_message='Owned diagnostic geometry verified.').model_copy(
                update={'private_context': {'window_geometry': state}})
    except Exception as error:
        return ToolResult.failure('move_window', type(error).__name__ + ': ' + str(error)).model_copy(
            update={'data': {'observed': native.observe(state)['geometry'], 'expected': state['after']}})


def test_geometry_worker_diagnostic_retains_native_success_assertion(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        original = runtime.tool_registry.lookup('move_window')
        runtime.tool_registry.register(original.model_copy(update={'executor': geometry_diagnostic}), overwrite=True)
        before = native.observe(target)['geometry']
        result = runtime.tool_registry.execute('move_window', arguments('move_window', target, before), task(runtime), runtime.ledger)
        assert result.ok and result.verified, (result.error, result.data)


def test_denied_geometry_never_dispatches_or_changes_window(runtime, monkeypatch, tmp_path):
    from pluma.policy.engine import PolicyEngine
    from pluma.policy.rules import PolicyRules
    approved(runtime, monkeypatch)
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={'move_window': 'DENY'}))
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        before = native.observe(target)
        cap = task(runtime)
        result = runtime.tool_registry.execute('move_window', arguments('move_window', target, before['geometry']), cap, runtime.ledger)
        assert not result.ok and result.error_code == 'POLICY_DENIED'
        assert cap.worker_controller is None and not cap.undo_stack and native.observe(target) == before


@pytest.mark.parametrize('tool', ['move_window', 'resize_window'])
def test_automatic_geometry_inverse_restores_and_consumes_exact_record(runtime, monkeypatch, tmp_path, tool):
    approved(runtime, monkeypatch)
    root = tmp_path / 'target'
    with owned_target(runtime, root) as (process, handle, fixture):
        target = window_target(root, process)
        before = native.observe(target)
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, arguments(tool, target, before['geometry']), cap, runtime.ledger)
        assert result.ok and result.verified
        rolled_back = runtime.rollback_engine.rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack)
        assert rolled_back.all_ok and rolled_back.steps_succeeded == 1 and not rolled_back.has_residual
        assert native.observe(target) == before and not cap.undo_stack
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
