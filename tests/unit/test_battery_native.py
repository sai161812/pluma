"""P11 battery observations; actual native reads and injected status packets."""
import ctypes
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import power
from pluma.core import job_object
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.cancellation import StopReason
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools import system
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop


def fake_kernel(monkeypatch, *, ac=1, flag=1, percent=85, ok=True):
    def read(pointer):
        value = pointer._obj
        value.ACLineStatus = ac
        value.BatteryFlag = flag
        value.BatteryLifePercent = percent
        value.SystemStatusFlag = 0
        value.BatteryLifeTime = value.BatteryFullLifeTime = 0xffffffff
        return int(ok)
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(GetSystemPowerStatus=read))


def test_ac_connection_does_not_claim_charging(monkeypatch):
    fake_kernel(monkeypatch, ac=1, flag=1)
    result = system.execute_battery_status({})
    assert result.ok and result.verified
    assert result.data['ac_connected'] is True and result.data['charging'] is False
    assert 'not charging' in result.factual_message.lower()


def test_unknown_native_bytes_remain_unknown(monkeypatch):
    fake_kernel(monkeypatch, ac=255, flag=255, percent=255)
    result = system.execute_battery_status({})
    assert result.ok and result.verified
    assert all(result.data[k] is None for k in ('ac_connected', 'has_battery', 'percent', 'charging'))


def test_failed_native_read_cannot_be_verified(monkeypatch):
    fake_kernel(monkeypatch, ok=False)
    result = system.execute_battery_status({})
    assert not result.ok and not result.verified


def packet(**updates):
    return dict({'ac_line': 0, 'battery_flags': 1, 'percent': 85, 'battery_saver': 0,
                 'remaining_seconds': 7200, 'full_seconds': 9000}, **updates)


@pytest.mark.parametrize('raw,expected', [
    (packet(battery_flags=9), {'charging': True, 'has_battery': True}),
    (packet(ac_line=1), {'charging': False, 'remaining_seconds': None, 'full_seconds': None}),
    (packet(battery_flags=128, percent=255), {'has_battery': False, 'percent': None, 'charging': False}),
    (packet(ac_line=255), {'ac_connected': None, 'charging': False}),
    (packet(battery_flags=255, percent=255), {'has_battery': None, 'percent': None, 'charging': None}),
    (packet(remaining_seconds=0xffffffff, full_seconds=0xffffffff), {'remaining_seconds': None, 'full_seconds': None}),
    (packet(battery_saver=1), {'battery_saver': True}),
    (packet(battery_saver=255), {'battery_saver': None}),
    (packet(percent=0, remaining_seconds=0), {'percent': 0, 'remaining_seconds': 0}),
])
def test_documented_flags_and_sentinels(raw, expected):
    observed = power.decode_power_status(raw)
    assert all(observed[key] == value for key, value in expected.items())
    assert observed['native_status'] == raw


@pytest.mark.parametrize('updates', [
    {'ac_line': -1}, {'ac_line': 2}, {'percent': 101}, {'percent': -1},
    {'battery_flags': 136}, {'battery_flags': 16}, {'battery_flags': True},
    {'remaining_seconds': -1}, {'full_seconds': 2**32}, {'percent': '85'},
])
def test_invalid_native_values_are_refused(updates):
    with pytest.raises(ValueError):
        power.decode_power_status(packet(**updates))


@pytest.mark.parametrize('key,value', [('charging', True), ('percent', 84), ('has_battery', False),
                                     ('ac_connected', True), ('remaining_seconds', 0)])
def test_verifier_rejects_observation_inconsistent_with_raw_native_fields(key, value):
    from pluma.tools.base import ToolResult
    data = power.decode_power_status(packet())
    data[key] = value
    result = ToolResult.success('battery_status', data=data)
    assert not system.verify_battery_status(result).ok


def test_non_windows_and_native_errors_never_emulate(monkeypatch):
    monkeypatch.setenv('PLUMA_TEST_MODE', '1')
    with monkeypatch.context() as m:
        m.setattr(power.sys, 'platform', 'linux')
        result = system.execute_battery_status({})
        assert not result.ok and result.error_code == 'UNSUPPORTED_PLATFORM'
    def fail():
        raise OSError('password=private-power-fixture')
    monkeypatch.setattr(power, 'read_battery_status', fail)
    result = system.execute_battery_status({})
    assert not result.ok and not result.verified
    assert 'private-power-fixture' not in str(result)


def test_invalid_schema_precedes_policy_and_worker(runtime):
    class NeverPolicy:
        def evaluate(self, **kw):
            pytest.fail('Battery schema reached policy')
    runtime.tool_registry._policy_engine = NeverPolicy()
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('battery_status', {'shell': 'forbidden'})
    assert not runtime.tool_registry._worker_controllers


def test_denied_battery_read_does_not_start_worker(runtime):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={'battery_status': 'DENY'}))
    result = runtime.orchestrator.execute(PlumaRequest.from_text('battery status'))
    assert not result.success and result.steps[0].result.error_code == 'POLICY_DENIED'
    assert not runtime.tool_registry._worker_controllers
    action = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert not action['verified'] and action['approval_state'] == 'DENY'


@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_battery_read_real_worker_history_and_cleanup(runtime, monkeypatch, input_mode):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='battery status'))
    assert result.success and result.final_state == 'SUCCEEDED'
    cap = runtime.supervisor.get_task(result.task_id)
    tool = result.steps[0].result
    assert tool.tool == 'battery_status' and tool.adapter_used == 'native_api'
    assert system.verify_battery_status(tool).ok
    system.BatteryData.model_validate(tool.data)
    action = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert action['tool'] == 'battery_status' and action['risk'] == 'READ' and action['verified']
    assert json.loads(action['result_json']) == tool.data
    assert not cap.undo_stack and not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    worker = next(e for e in cap.cleanup_evidence if e.kind == 'worker' and 'pid' in e.identity)
    assert worker.verified and worker.identity['creation_time'] > 0 and worker.identity['task_id'] == cap.task_id
    assert cap.worker_controller is cap.job_object is None
    assert runtime.close(3).complete
    assert reopened(runtime, cap)['input_mode'] == input_mode.value


@pytest.mark.parametrize('stop', [True, False])
def test_blocked_battery_worker_obeys_stop_and_deadline(runtime, monkeypatch, tmp_path, stop):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    spec = runtime.tool_registry.lookup('battery_status')
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path), cooperative=False, descendant=False))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    req = PlumaRequest.from_text('battery status')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    assert controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'battery_status', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)[0] == 'ok'
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'entered', running)
            if stop:
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.success and result.final_state == ('STOPPED' if stop else 'FAILED')
    assert cap.cancellation_token.reason == (StopReason.USER_STOP if stop else StopReason.TASK_TIMEOUT)
    assert controller.verify_cleanup() and not (tmp_path / 'late').exists()
    assert not cap.undo_stack
    assert runtime.close(3).complete
    reopened(runtime, cap)
