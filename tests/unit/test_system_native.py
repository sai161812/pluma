"""P11 native system/network READ contracts and truthful failure paths."""
import psutil
import pytest
from concurrent.futures import ThreadPoolExecutor
import json
import time
from types import SimpleNamespace

from pluma.adapters import system_status as native
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools import system
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop

NAMES = ['get_system_status', 'system_status', 'network_status']


def test_cpu_read_failure_never_becomes_verified_zero(monkeypatch):
    def fail(*a, **kw):
        raise OSError('private-system-fixture')
    monkeypatch.setattr(psutil, 'cpu_percent', fail)
    result = system.execute_get_system_status({})
    assert not result.ok and not result.verified
    assert 'private-system-fixture' not in str(result)


def test_required_network_tool_is_registered(runtime):
    assert runtime.tool_registry.contains('network_status')
    schemas = ToolSubsetSelector(runtime.tool_registry).select_schemas(RouteMode.SMART, command='network status')
    assert 'network_status' in {schema['name'] for schema in schemas}


def resource_packet(**updates):
    return dict({'os': 'Windows fixture', 'python_version': '3.12', 'disk_root': 'C:\\',
                 'disk_free_bytes': 1024**3, 'disk_total_bytes': 2 * 1024**3,
                 'ram_available_bytes': 2 * 1024**3, 'ram_total_bytes': 4 * 1024**3,
                 'cpu_percent': 12.5, 'cpu_sample_seconds': .101}, **updates)


@pytest.mark.parametrize('updates', [
    {'cpu_percent': float('nan')}, {'cpu_percent': float('inf')}, {'cpu_percent': True},
    {'cpu_percent': 101}, {'cpu_percent': -1}, {'cpu_sample_seconds': 0},
    {'disk_total_bytes': 0}, {'disk_free_bytes': 3 * 1024**3},
    {'ram_total_bytes': 1}, {'ram_available_bytes': -1}, {'disk_root': 'relative'},
    {'ram_total_bytes': True}, {'os': ''},
])
def test_invalid_resource_observations_are_refused(updates):
    with pytest.raises(ValueError):
        native.decode_system_status(resource_packet(**updates))


@pytest.mark.parametrize('key,value', [('cpu_percent', 0.0), ('ram_free_gb', 0.0),
                                     ('disk_free_gb', 0.0), ('memory_load_percent', 0.0)])
def test_resource_verifier_rejects_inconsistent_derived_data(key, value):
    data = native.decode_system_status(resource_packet())
    data[key] = value
    assert not system.verify_system_status(ToolResult.success('get_system_status', data=data)).ok


def test_cpu_sample_is_blocking_and_native_zero_can_be_observed(monkeypatch):
    intervals = []
    def read(*, interval):
        intervals.append(interval)
        time.sleep(interval)
        return 0.0
    monkeypatch.setattr(psutil, 'cpu_percent', read)
    result = system.execute_get_system_status({})
    assert result.ok and result.verified and result.data['cpu_percent'] == 0.0
    assert intervals == [.1]
    assert result.data['disk_root'].lower() == native._system_drive().lower()
    assert '\u2014' not in result.factual_message


@pytest.mark.parametrize('method,execute', [('virtual_memory', system.execute_get_system_status),
    ('disk_usage', system.execute_get_system_status), ('net_if_stats', system.execute_network_status)])
def test_native_read_errors_are_fixed_failures(monkeypatch, method, execute):
    def fail(*a, **kw):
        raise OSError('password=private-system-fixture')
    monkeypatch.setattr(psutil, method, fail)
    result = execute({})
    assert not result.ok and not result.verified
    assert 'private-system-fixture' not in str(result)


@pytest.mark.parametrize('execute', [system.execute_get_system_status, system.execute_system_status,
                                     system.execute_network_status])
def test_non_windows_read_cannot_emulate_success(monkeypatch, execute):
    monkeypatch.setenv('PLUMA_TEST_MODE', '1')
    with monkeypatch.context() as m:
        m.setattr(native.sys, 'platform', 'linux')
        result = execute({})
        assert not result.ok and result.error_code == 'UNSUPPORTED_PLATFORM'


@pytest.mark.parametrize('name', NAMES)
def test_required_worker_serialization_never_falls_back(runtime, monkeypatch, name):
    calls = []
    def execute(args):
        calls.append('executed')
        return ToolResult.success(name, factual_message='Inert serialization fixture returned.')
    spec = runtime.tool_registry.lookup(name)
    monkeypatch.setattr(spec, 'executor', execute)
    result = runtime.tool_registry.execute(name, {})
    assert not result.ok and result.error_code == 'PROCESS_ISOLATION_FAILED'
    assert not calls and not runtime.tool_registry._worker_controllers


def test_interface_snapshot_is_bounded_and_never_infers_internet(monkeypatch):
    monkeypatch.setattr(psutil, 'net_if_stats', lambda: {
        f'fixture-{i:02}': SimpleNamespace(isup=bool(i % 2), speed=0 if i == 0 else 100, mtu=1500)
        for i in range(30)})
    result = system.execute_network_status({'max_entries': 1})
    assert result.ok and result.verified and result.data['truncated']
    assert result.data['observed_count'] == 30 and len(result.data['interfaces']) == 1
    assert result.data['interfaces'][0]['name'] == 'fixture-00'
    assert result.data['interfaces'][0]['link_speed_mbps'] is None
    assert result.data['internet_connectivity'] is None
    assert not any(key in str(result.data) for key in ('address', 'password', 'SSID'))


@pytest.mark.parametrize('stats', [{}, {'fixture': SimpleNamespace(isup=True, speed=100, mtu=1500)}])
def test_empty_and_up_interface_do_not_claim_internet(monkeypatch, stats):
    monkeypatch.setattr(psutil, 'net_if_stats', lambda: stats)
    result = system.execute_network_status({})
    assert result.ok and result.verified and result.data['internet_connectivity'] is None
    assert result.data['truncated'] is False


@pytest.mark.parametrize('speed,mtu,up', [(-1, 1500, True), (float('nan'), 1500, True),
                                      (100, -1, True), (100, 1500, 'yes')])
def test_invalid_interface_fields_cannot_report_success(monkeypatch, speed, mtu, up):
    monkeypatch.setattr(psutil, 'net_if_stats', lambda: {
        'fixture': SimpleNamespace(isup=up, speed=speed, mtu=mtu)})
    result = system.execute_network_status({})
    assert not result.ok and not result.verified


@pytest.mark.parametrize('mutation', ['duplicate', 'truncation', 'internet', 'count'])
def test_network_verifier_rejects_inconsistent_snapshots(mutation):
    data = {'interfaces': [{'name': 'fixture', 'is_up': True, 'mtu': 1500, 'link_speed_mbps': 100.0}],
            'observed_count': 1, 'max_entries': 32, 'truncated': False, 'internet_connectivity': None}
    if mutation == 'duplicate':
        data['interfaces'] *= 2
        data['observed_count'] = 2
    if mutation == 'truncation': data['truncated'] = True
    if mutation == 'internet': data['internet_connectivity'] = True
    if mutation == 'count': data['observed_count'] = 0
    assert not system.verify_network_status(ToolResult.success('network_status', data=data)).ok


@pytest.mark.parametrize('name,args', [(name, {'unexpected': True}) for name in NAMES] + [
    ('network_status', {'max_entries': True}), ('network_status', {'max_entries': '3'}),
    ('network_status', {'max_entries': 0}), ('network_status', {'max_entries': 129})])
def test_invalid_schema_precedes_policy_and_worker(runtime, name, args):
    class NeverPolicy:
        def evaluate(self, **kwargs):
            pytest.fail('Invalid system schema reached policy')
    runtime.tool_registry._policy_engine = NeverPolicy()
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(name, args)
    assert not runtime.tool_registry._worker_controllers


def fixture_route(runtime, name):
    if name == 'get_system_status':
        return
    plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool=name, arguments={}, purpose='Read native status')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=RouteMode.SMART, reason='P11 status fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kw: plan)


@pytest.mark.parametrize('name', NAMES)
def test_policy_denial_has_history_and_no_worker(runtime, name):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={name: 'DENY'}))
    fixture_route(runtime, name)
    result = runtime.orchestrator.execute(PlumaRequest.from_text('system status'))
    assert not result.success and result.steps[0].result.error_code == 'POLICY_DENIED'
    assert not runtime.tool_registry._worker_controllers
    action = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert not action['verified'] and action['approval_state'] == 'DENY'


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_read_has_real_worker_exit_and_reopened_history(runtime, monkeypatch, name, input_mode):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    fixture_route(runtime, name)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='system status'))
    assert result.success and result.final_state == 'SUCCEEDED'
    assert result.route == (RouteMode.FAST if name == 'get_system_status' else RouteMode.SMART)
    cap = runtime.supervisor.get_task(result.task_id)
    tool = result.steps[0].result
    assert tool.tool == name and tool.adapter_used == 'native_api'
    assert (system.verify_network_status(tool) if name == 'network_status' else system.verify_system_status(tool)).ok
    action = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert action['tool'] == name and action['risk'] == 'READ' and action['verified']
    assert json.loads(action['result_json']) == tool.data
    assert not cap.undo_stack and not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    worker = next(e for e in cap.cleanup_evidence if e.kind == 'worker' and 'pid' in e.identity)
    assert worker.verified and worker.identity['creation_time'] > 0 and worker.identity['task_id'] == cap.task_id
    assert cap.worker_controller is cap.job_object is None
    assert runtime.close(3).complete
    assert reopened(runtime, cap)['input_mode'] == input_mode.value


@pytest.mark.parametrize('name', NAMES)
@pytest.mark.parametrize('stop', [True, False])
def test_blocked_read_obeys_stop_and_deadline(runtime, monkeypatch, tmp_path, name, stop):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    spec = runtime.tool_registry.lookup(name)
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path), cooperative=False, descendant=False))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    fixture_route(runtime, name)
    req = PlumaRequest.from_text('system status')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    assert controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, name, {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)[0] == 'ok'
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'entered', running)
            if stop: runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done(): runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.success and result.final_state == ('STOPPED' if stop else 'FAILED')
    assert cap.cancellation_token.reason == (StopReason.USER_STOP if stop else StopReason.TASK_TIMEOUT)
    assert controller.verify_cleanup() and not (tmp_path / 'late').exists()
    assert runtime.close(3).complete
    reopened(runtime, cap)
