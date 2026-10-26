"""Bounded native read-only app/window checks using owned hidden fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import app_windows as native
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
from pluma.core.ownership import subprocess_absent
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.rules import PolicyRules
from pluma.tools import app_observations as reads
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_memory_tools import approved
from tests.unit.test_process_control_native import owned_target
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop


@pytest.mark.parametrize('tool', ['list_apps', 'app_status', 'list_windows'])
@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_read_pipeline_preserves_duplicate_instances_and_user_state(runtime, monkeypatch, tmp_path, tool, input_mode):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'first') as (first, _, _), owned_target(runtime, tmp_path / 'second') as (second, _, _):
        args = first if tool == 'app_status' else {'visible_only': False,
            'filter': 'python' if tool == 'list_apps' else 'PLUMA owned hidden fixture', 'max_entries': 256}
        plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool=tool, arguments=args, purpose='Inspect owned fixture')])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.SMART, reason='Native app read fixture', plan=plan))
        runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Inspect owned fixture application'))
        assert result.success and result.final_state == 'SUCCEEDED', result
        observed = result.steps[0].result
        assert observed.ok and observed.verified and observed.adapter_used == 'native_api' and not observed.private_context
        if tool == 'app_status':
            assert observed.data['running'] and observed.data['creation_time'] == first['creation_time']
        else:
            packet = observed.data['window_observation'] if tool == 'list_apps' else observed.data
            rows = [row for row in packet['windows'] if row['available'] and row['pid'] in (first['pid'], second['pid'])]
            fixture_rows = [row for row in rows if row['title'] == 'PLUMA owned hidden fixture']
            assert len(fixture_rows) == 2 and len({row['hwnd'] for row in fixture_rows}) == 2
            assert {row['creation_time'] for row in rows} == {first['creation_time'], second['creation_time']}
            assert all(not row['visible'] and not row['minimized'] and not row['maximized'] for row in fixture_rows)
            if tool == 'list_apps':
                grouped = [row for row in observed.data['apps'] if row['pid'] in (first['pid'], second['pid'])]
                assert len(grouped) == 2 and len({row['name'] for row in grouped}) == 1
                assert {hwnd for group in grouped for hwnd in group['window_handles']} == {row['hwnd'] for row in rows}
        assert native.status(first)['running'] and native.status(second)['running']
        cap = runtime.supervisor.get_task(result.task_id)
        assert not cap.undo_stack and cap.worker_controller is cap.job_object is None
        rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
        assert len(rows) == 1 and rows[0]['tool'] == tool and rows[0]['verified']


@pytest.mark.parametrize('tool', ['list_apps', 'list_windows'])
def test_native_limits_and_actual_empty_scope_are_factual(runtime, monkeypatch, tmp_path, tool):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target'):
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, {'visible_only': False, 'max_scan_entries': 1}, cap, runtime.ledger)
        assert result.ok and result.verified, result
        packet = result.data['window_observation'] if tool == 'list_apps' else result.data
        assert packet['limited'] and packet['scanned_windows'] == 1
        empty = runtime.tool_registry.execute(tool, {'filter': 'pluma-no-such-owned-fixture-775e84'}, cap, runtime.ledger)
        assert empty.ok and empty.verified and empty.data['count'] == 0, empty


def test_recycled_or_absent_process_identity_is_not_reported_live(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, _, _):
        cap = task(runtime)
        result = runtime.tool_registry.execute('app_status', dict(target, creation_time=target['creation_time'] + 1), cap, runtime.ledger)
        assert result.ok and result.verified and result.data['state'] == 'gone_or_changed' and not result.data['running']
        assert native.status(target)['running']
    result = runtime.tool_registry.execute('app_status', target, cap, runtime.ledger)
    assert result.ok and result.verified and not result.data['running']


@pytest.mark.parametrize('tool,args', [('app_status', {'app_name': 'python'}), ('app_status', {'pid': True, 'creation_time': 1}),
    ('app_status', {'pid': 1}), ('list_apps', {'max_entries': True}), ('list_windows', {'visible_only': 'true'}),
    ('list_windows', {'max_scan_entries': 2049}), ('list_apps', {'shell': 'tasklist'})])
def test_invalid_read_schemas_precede_policy_and_workers(runtime, tool, args):
    runtime.tool_registry._policy_engine = SimpleNamespace(evaluate=lambda **kwargs: pytest.fail('Invalid read reached policy'))
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute(tool, args)
    assert not runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('tool', ['list_apps', 'list_windows', 'app_status'])
def test_denied_read_has_no_executor(runtime, monkeypatch, tool):
    runtime.policy_engine.rules = PolicyRules(overrides={tool: 'DENY'})
    monkeypatch.setattr(runtime.tool_registry.lookup(tool), 'executor', lambda *args: pytest.fail('Denied read executed'))
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, {'pid': 1, 'creation_time': 1} if tool == 'app_status' else {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not cap.undo_stack


def test_enumeration_failure_cannot_be_a_verified_empty_list(monkeypatch):
    c, w, _ = native._api()
    def fail(*args): return False
    monkeypatch.setattr(native, '_api', lambda: (c, w, SimpleNamespace(EnumWindows=fail)))
    result = reads.execute_list({})
    assert not result.ok and not result.verified and not result.data


def test_unreadable_process_is_not_reported_as_not_running(monkeypatch):
    def fail(*args): raise PermissionError('password=private-fixture')
    monkeypatch.setattr(native, '_process', fail)
    result = reads.execute_status({'pid': 1, 'creation_time': 1})
    assert not result.ok and not result.data and 'private-fixture' not in result.model_dump_json()


def test_cancelled_window_inspection_never_enumerates(monkeypatch):
    token = CancellationToken()
    token.cancel(StopReason.USER_STOP)
    monkeypatch.setattr(native, '_api', lambda: pytest.fail('Cancelled enumeration began'))
    with pytest.raises(TaskCancelledError): native.enumerate_windows({}, SimpleNamespace(cancellation_token=token))


def test_stale_window_or_forged_private_proof_is_refused(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, _, _):
        result = reads.execute_list({'visible_only': False, 'filter': 'PLUMA owned hidden fixture'})
        assert result.ok and result.verified, result
        assert not reads.verify_list(result.model_copy(update={'private_context': {}})).ok
        entry = next(row for row in result.data['windows'] if row['available'] and row['pid'] == target['pid'])
        with pytest.raises(ProcessLookupError): native.observe_window(entry['hwnd'], target['creation_time'] + 1)
    assert not reads.verify_list(result).ok


def test_unreadable_window_is_explicit_unknown_not_a_dummy_application(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, _, _):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        c, w, user = native._api()
        def enumerate_one(callback, ignored):
            return callback(marker['hwnd'], 0)
        replacement = SimpleNamespace(EnumWindows=enumerate_one, GetWindowThreadProcessId=user.GetWindowThreadProcessId)
        monkeypatch.setattr(native, '_api', lambda: (c, w, replacement))
        def denied(*args): raise PermissionError('fixture denied')
        monkeypatch.setattr(native, 'observe_window', denied)
        result = reads.execute_list({'visible_only': False}, apps=True)
        assert result.ok and result.verified and result.data['count'] == 0
        assert result.data['unavailable_windows'] == 1 and not result.data['apps']
        entry = result.data['window_observation']['windows'][0]
        assert entry == {'available': False, 'hwnd': marker['hwnd'], 'pid': target['pid'], 'reason': 'access_denied'}
        assert 'unreadable or changed' in result.factual_message


def test_long_native_caption_is_bounded_and_undecidable_filter_refuses(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, _, _):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        c, w, user = native._api()
        user.SendMessageTimeoutW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, c.POINTER(c.c_size_t)]
        user.SendMessageTimeoutW.restype = w.LPARAM
        text = c.create_unicode_buffer('PLUMA_LONG_FIXTURE_' + 'x' * 2100 + 'ENDING_NEEDLE')
        returned = c.c_size_t()
        assert user.SendMessageTimeoutW(marker['hwnd'], 0x000c, 0, c.addressof(text), 2, 500, c.byref(returned))
        result = reads.execute_list({'visible_only': False, 'filter': 'PLUMA_LONG_FIXTURE_'})
        assert result.ok and result.verified, result
        entry = next(row for row in result.data['windows'] if row['pid'] == target['pid'])
        assert len(entry['title']) == 2048 and entry['title_truncated']
        result = reads.execute_list({'visible_only': False, 'filter': 'ENDING_NEEDLE'})
        assert not result.ok and not result.verified and not result.data


def test_window_availability_cannot_be_a_truthy_numeric_flag():
    with pytest.raises(ValueError):
        reads.UnavailableWindow.model_validate({'available': 0, 'hwnd': 1, 'pid': 1, 'reason': 'unavailable'})


def test_caption_access_failure_is_not_an_empty_title():
    import ctypes
    def denied(*args):
        ctypes.set_last_error(5)
        return 0
    user = SimpleNamespace(GetWindowTextLengthW=lambda *args: 10, GetWindowTextW=denied)
    with pytest.raises(PermissionError): native._title(ctypes, user, 1)


@pytest.mark.parametrize('tool', ['list_apps', 'list_windows', 'app_status'])
@pytest.mark.parametrize('stop', [True, False])
def test_blocked_read_worker_is_owned_and_stoppable(runtime, monkeypatch, tmp_path, tool, stop):
    approved(runtime, monkeypatch)
    spec = runtime.tool_registry.lookup(tool)
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    cap = task(runtime)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller, cap._tool_registry = controller, runtime.tool_registry
    status, _ = controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, tool, {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)
    assert status == 'ok'
    proc = controller._proc
    identity = dict(controller.worker_identity)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runtime.tool_registry.execute, tool,
            {'pid': 1, 'creation_time': 1} if tool == 'app_status' else {}, cap, runtime.ledger)
        try:
            await_file(tmp_path / 'entered', future)
            if stop: runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = future.result(3)
        finally:
            if not future.done(): runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.ok and result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert proc._closed and controller._proc is None
    assert subprocess_absent(identity['pid'], identity['creation_time']) is True
    assert controller.verify_cleanup() and not (tmp_path / 'late').exists()
