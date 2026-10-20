"""P11 process observations: native Windows handles/Jobs and isolated history."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import os
from types import SimpleNamespace

import pytest

from pluma.adapters import processes as native
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.ownership import get_process_creation_time
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools import processes
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop

NAMES = ['list_processes', 'process_info', 'process_usage']


def target():
    return {'pid': os.getpid(), 'creation_time': get_process_creation_time(os.getpid())}


def route(runtime, name, args, mode=RouteMode.SMART):
    plan = Plan(route=mode, steps=[ToolCall(tool=name, arguments=args, purpose='Read process state')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=mode, reason='P11 process fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)


@pytest.mark.parametrize('name,args', [
    ('list_processes', {'max_entries': 0}), ('list_processes', {'max_entries': 501}),
    ('list_processes', {'max_entries': True}), ('list_processes', {'max_entries': '5'}),
    ('list_processes', {'command': 'ignored'}),
] + [(name, args) for name in ['process_info', 'process_usage'] for args in [
    {}, {'pid': 1}, {'pid': 0, 'creation_time': 1}, {'pid': True, 'creation_time': 1},
    {'pid': '1', 'creation_time': 1}, {'pid': 1, 'creation_time': 0},
    {'pid': 1, 'creation_time': '1'}, {'pid': 1, 'creation_time': 1, 'shell': 'ignored'},
]])
def test_schema_precedes_policy_and_worker(runtime, name, args):
    class NoPolicy:
        def evaluate(self, **kwargs):
            pytest.fail('Invalid arguments reached policy')
    runtime.tool_registry._policy_engine = NoPolicy()
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(name, args)
    assert not runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_registered_reads_history_and_worker_exit(runtime, monkeypatch, name, input_mode):
    import psutil
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    args = {'max_entries': 500} if name == 'list_processes' else target()
    route(runtime, name, args)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Inspect process fixture'))
    assert result.success and result.final_state == 'SUCCEEDED'
    cap = runtime.supervisor.get_task(result.task_id)
    tool = result.steps[0].result
    assert tool.ok and tool.verified and tool.adapter_used == 'native_api'
    processes.DATA_SCHEMAS[name].model_validate(tool.data)
    if name == 'list_processes':
        entries = tool.data['entries']
        assert len(entries) <= 500
        assert tool.data['truncated'] == (tool.data['observed_pid_count'] > len(entries))
        entry = next(e for e in entries if e['pid'] == os.getpid())
        assert entry['creation_time'] == target()['creation_time'] and entry['available']
        assert entry['name'] == psutil.Process().name()
    elif name == 'process_info':
        assert tool.data['name'] == psutil.Process().name()
        assert tool.data['parent_pid'] == os.getppid() and tool.data['thread_count'] >= 1
    else:
        assert tool.data['cpu_percent'] >= 0 and tool.data['sample_seconds'] >= 0.04
        assert tool.data['rss_bytes'] > 0
    assert get_process_creation_time(os.getpid()) == target()['creation_time']
    action = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert action['tool'] == name and action['risk'] == 'READ' and action['verified']
    assert 'cmdline' not in json.dumps(action) and 'environ' not in json.dumps(action)
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id) and not cap.undo_stack
    worker = next(e for e in cap.cleanup_evidence if e.kind == 'worker' and 'pid' in e.identity)
    assert worker.verified and worker.identity['task_id'] == cap.task_id
    assert worker.identity['creation_time'] > 0 and worker.identity['ownership'] == 'PLUMA_CREATED'
    assert cap.worker_controller is cap.job_object is None
    assert runtime.close(3).complete
    assert reopened(runtime, cap)['input_mode'] == input_mode.value


@pytest.mark.parametrize('name', ['process_info', 'process_usage'])
@pytest.mark.parametrize('mismatch', [True, False])
def test_native_absent_or_mismatched_identity_is_not_success(runtime, monkeypatch, name, mismatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    args = target() if mismatch else {'pid': 0xFFFFFFFF, 'creation_time': 1}
    if mismatch:
        args['creation_time'] += 1
    route(runtime, name, args)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect stale process fixture'))
    tool = result.steps[0].result
    assert not result.success and result.final_state == 'FAILED'
    assert tool.error_code == 'PROCESS_IDENTITY_CHANGED' and not tool.verified and not tool.data
    assert get_process_creation_time(os.getpid()) == target()['creation_time']


@pytest.mark.parametrize('name', NAMES)
def test_policy_denial_has_no_worker_and_factual_action(runtime, name):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={name: 'DENY'}))
    route(runtime, name, {} if name == 'list_processes' else target())
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect denied process fixture'))
    assert not result.success and result.steps[0].result.error_code == 'POLICY_DENIED'
    assert not runtime.tool_registry._worker_controllers
    row = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert row['approval_state'] == 'DENY' and not row['verified']
    assert json.loads(row['result_json']) == {'executed': False}


@pytest.mark.parametrize('error,code', [
    (PermissionError('password=private-fixture'), 'PROCESS_ACCESS_DENIED'),
    (ProcessLookupError('token=private-fixture'), 'PROCESS_IDENTITY_CHANGED'),
    (OSError('secret=private-fixture'), 'PROCESS_READ_FAILED'),
    (NotImplementedError('private-fixture'), 'PROCESS_UNSUPPORTED'),
])
def test_faults_are_fixed_copy_without_metadata(monkeypatch, error, code):
    def fail(*args):
        raise error
    monkeypatch.setattr(native, 'inspect_processes', fail)
    result = processes.execute_inspection(target(), tool='process_info')
    assert not result.ok and not result.verified and not result.data and result.error_code == code
    assert 'private-fixture' not in result.model_dump_json()


def test_list_marks_inaccessible_entries_without_inventing_metadata(monkeypatch):
    import psutil
    monkeypatch.setattr(psutil, 'pids', lambda: [1, 2, 3])
    @contextmanager
    def denied(pid, creation_time=None):
        raise PermissionError
        yield
    monkeypatch.setattr(native, '_process', denied)
    result = processes.execute_inspection({'max_entries': 2}, tool='list_processes')
    assert result.ok and result.verified and result.data['truncated']
    assert result.data['observed_pid_count'] == 3
    assert all(not e['available'] and e['creation_time'] is e['name'] is None
               and e['unavailable_reason'] == 'access_denied' for e in result.data['entries'])


def test_original_native_handle_exit_during_read_discards_pid_observation(monkeypatch):
    import _winapi
    original = _winapi.WaitForSingleObject
    count = []
    def exited(handle, timeout):
        count.append(handle)
        return original(handle, timeout) if len(count) == 1 else _winapi.WAIT_OBJECT_0
    monkeypatch.setattr(_winapi, 'WaitForSingleObject', exited)
    result = processes.execute_inspection(target(), tool='process_info')
    assert len(count) == 2 and not result.ok and not result.data
    assert result.error_code == 'PROCESS_IDENTITY_CHANGED'


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('stop', [True, False])
def test_blocked_owned_reads_stop_or_timeout_without_late_effect(runtime, monkeypatch, tmp_path, name, stop):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    spec = runtime.tool_registry.lookup(name)
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    args = {} if name == 'list_processes' else target()
    route(runtime, name, args)
    req = PlumaRequest.from_text('Blocked process observation fixture')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    status, _ = controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, name, {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)
    assert status == 'ok'
    identity = dict(controller.worker_identity)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'entered', running)
            assert controller.worker_identity == identity
            proc = controller._proc
            if stop:
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert result.final_state == ('STOPPED' if stop else 'FAILED') and not result.success
    assert result.steps[0].result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert cap.cancellation_token.reason == (StopReason.USER_STOP if stop else StopReason.TASK_TIMEOUT)
    assert not proc.is_alive() and controller.verify_cleanup() is True
    assert not (tmp_path / 'late').exists() and not cap.undo_stack
    assert runtime.close(3).complete
    reopened(runtime, cap)


def test_required_worker_cannot_silently_fall_back_to_thread(runtime, monkeypatch):
    spec = runtime.tool_registry.lookup('process_info')
    monkeypatch.setattr(spec, 'executor', lambda args: pytest.fail('Unpicklable tool executed'))
    route(runtime, 'process_info', target())
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect fixture'))
    assert not result.success and result.steps[0].result.error_code == 'PROCESS_ISOLATION_FAILED'
    assert not runtime.tool_registry._worker_controllers
    row = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert not row['verified'] and json.loads(row['result_json']) == {'executed': False}


@pytest.mark.parametrize('route_mode', list(RouteMode))
def test_process_schemas_are_available_only_to_appropriate_routes(runtime, route_mode):
    schemas = ToolSubsetSelector(runtime.tool_registry).select_schemas(route_mode)
    names = {s['name'] for s in schemas}
    assert set(NAMES).issubset(names) == (route_mode in (RouteMode.SMART, RouteMode.DEEP))
    for schema in schemas:
        if schema['name'] in NAMES:
            assert schema['risk_class'] == 'READ' and not schema['args_schema']['additionalProperties']
            assert 'process_isolated' not in schema


@pytest.mark.parametrize('change', ['unverified', 'adapter', 'proof', 'extra', 'nan', 'identity'])
def test_verifier_rejects_unproved_or_malformed_observations(change):
    result = processes.execute_inspection(target(), tool='process_usage')
    assert result.ok
    data = dict(result.data)
    updates = {}
    if change == 'unverified': updates['verified'] = False
    if change == 'adapter': updates['adapter_used'] = 'mock'
    if change == 'proof': updates['verify_detail'] = None
    if change == 'extra': data['cmdline'] = 'must not be accepted'
    if change == 'nan': data['cpu_percent'] = float('nan')
    if change == 'identity': data['creation_time'] = 0
    result = result.model_copy(update={'data': data, **updates})
    assert not processes.verify_inspection(result).ok
