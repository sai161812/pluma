"""P11 Core Audio reads and fail-closed write observations. No physical writes."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import audio as native
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools import audio
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop

READS = ['get_volume', 'get_volume_status', 'list_audio_devices']
CHANGES = [('set_volume', audio.execute_set_volume, {'level': 42}),
           ('mute', audio.execute_mute, {}), ('unmute', audio.execute_unmute, {})]


def state(**updates):
    return dict({'endpoint_id': 'fixture-native-id', 'volume': 42, 'scalar': .42,
                 'muted': False, 'is_mock': False}, **updates)


def route(runtime, name, args):
    plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool=name, arguments=args, purpose='Read audio state')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=RouteMode.SMART, reason='P11 audio fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)


@pytest.mark.parametrize('name,args', [(name, {'shell': 'ignored'}) for name in READS] + [
    ('list_audio_devices', {'max_entries': True}), ('list_audio_devices', {'max_entries': '3'}),
    ('list_audio_devices', {'max_entries': 0}), ('list_audio_devices', {'max_entries': 129}),
    ('set_volume', {'level': True}), ('set_volume', {'level': '42'}),
    ('set_volume', {'level': -1}), ('set_volume', {'level': 101}),
])
def test_invalid_schema_precedes_policy_and_worker(runtime, name, args):
    class NoPolicy:
        def evaluate(self, **kwargs):
            pytest.fail('Invalid audio schema reached policy')
    runtime.tool_registry._policy_engine = NoPolicy()
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(name, args)
    assert not runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('name', READS)
@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_read_in_owned_worker_with_real_ledger_and_exit(runtime, monkeypatch, name, input_mode):
    monkeypatch.delenv('PLUMA_EMULATE_AUDIO', raising=False)
    monkeypatch.delenv('PLUMA_TEST_MODE', raising=False)
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    before = native.read_volume()
    route(runtime, name, {})
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Read audio fixture'))
    assert result.success and result.final_state == 'SUCCEEDED'
    cap = runtime.supervisor.get_task(result.task_id)
    tool = result.steps[0].result
    assert tool.ok and tool.verified and tool.adapter_used == 'native_api'
    if name == 'list_audio_devices':
        audio.AudioDevicesData.model_validate(tool.data)
        assert tool.data['devices'] and not tool.data['truncated']
        assert any(d['endpoint_id'] == before['endpoint_id'] and d['flow'] == 'render'
                   and d['state'] == 1 for d in tool.data['devices'])
        assert {d['flow'] for d in tool.data['devices']} <= {'render', 'capture'}
    else:
        audio.VolumeData.model_validate(tool.data)
        assert not tool.data['is_mock'] and tool.data['endpoint_id'] == before['endpoint_id']
        assert tool.data['volume'] == before['volume'] and tool.data['muted'] == before['muted']
    after = native.read_volume()
    assert after == before  # physical endpoint state is only read
    action = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert action['tool'] == name and action['risk'] == 'READ' and action['verified']
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id) and not cap.undo_stack
    worker = next(e for e in cap.cleanup_evidence if e.kind == 'worker' and 'pid' in e.identity)
    assert worker.verified and worker.identity['task_id'] == cap.task_id
    assert worker.identity['creation_time'] > 0 and worker.identity['ownership'] == 'PLUMA_CREATED'
    assert cap.worker_controller is cap.job_object is None
    assert runtime.close(3).complete
    assert reopened(runtime, cap)['input_mode'] == input_mode.value


@pytest.mark.parametrize('name', READS)
def test_denied_audio_read_has_no_worker_and_truthful_history(runtime, name):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={name: 'DENY'}))
    route(runtime, name, {})
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Read denied audio fixture'))
    assert not result.success and result.steps[0].result.error_code == 'POLICY_DENIED'
    assert not runtime.tool_registry._worker_controllers
    action = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert not action['verified'] and action['approval_state'] == 'DENY'
    assert json.loads(action['result_json']) == {'executed': False}


@pytest.mark.parametrize('name,execute,args', CHANGES)
def test_missing_prestate_refuses_before_setter(monkeypatch, name, execute, args):
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: None)
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: pytest.fail('No pre-state'))
    result = execute(args)
    assert not result.ok and not result.verified and result.error_code == 'AUDIO_READ_FAILED'


@pytest.mark.parametrize('name,execute,args', CHANGES)
@pytest.mark.parametrize('change', ['missing', 'endpoint', 'mode', 'wrong_state'])
def test_missing_or_contradictory_post_read_never_substitutes_request(monkeypatch, name, execute, args, change):
    previous = state(muted=name == 'unmute')
    post = state(muted=name == 'mute')
    if change == 'missing': post = None
    if change == 'endpoint': post['endpoint_id'] = 'replacement-endpoint'
    if change == 'mode': post['is_mock'] = True
    if change == 'wrong_state':
        if name == 'set_volume': post.update(volume=70, scalar=.70)
        else: post['muted'] = name != 'mute'
    observations = iter([previous, post])
    calls = []
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: next(observations))
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: calls.append(kwargs) or True)
    result = execute(args)
    assert len(calls) == 1 and calls[0]['expected_endpoint'] == previous['endpoint_id']
    assert not result.ok and not result.verified and result.error_code == 'AUDIO_READBACK_FAILED'
    assert not result.data


@pytest.mark.parametrize('name,execute,args', CHANGES)
def test_write_refusal_never_claims_success(monkeypatch, name, execute, args):
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', state)
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: False)
    result = execute(args)
    assert not result.ok and not result.verified and result.error_code == 'AUDIO_SET_FAILED'


@pytest.mark.parametrize('name', ['get_volume', 'get_volume_status'])
def test_missing_read_has_no_fabricated_zero_state(monkeypatch, name):
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: None)
    result = audio.execute_get_volume({}, tool=name)
    assert not result.ok and not result.data and result.error_code == 'AUDIO_READ_FAILED'


def test_native_backend_error_cannot_turn_test_mode_into_emulation(monkeypatch):
    monkeypatch.delenv('PLUMA_EMULATE_AUDIO', raising=False)
    monkeypatch.setenv('PLUMA_TEST_MODE', '1')
    def fail(*args):
        raise OSError('password=private-audio-fixture')
    monkeypatch.setattr(native, 'read_volume', fail)
    monkeypatch.setattr(native, 'set_volume', fail)
    assert audio._get_audio_endpoint_volume() is None
    assert not audio._set_audio_endpoint_volume(level=42)


def test_device_error_is_fixed_copy_without_fake_empty_enumeration(monkeypatch):
    def fail(*args):
        raise OSError('token=private-audio-fixture')
    monkeypatch.setattr(native, 'list_devices', fail)
    result = audio.execute_list_audio_devices({'max_entries': 64})
    assert not result.ok and not result.verified and not result.data
    assert result.error_code == 'AUDIO_DEVICES_READ_FAILED' and 'private-audio-fixture' not in result.model_dump_json()


@pytest.mark.parametrize('name', READS)
@pytest.mark.parametrize('stop', [True, False])
def test_blocked_audio_reader_is_owned_stoppable_and_bounded(runtime, monkeypatch, tmp_path, name, stop):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    spec = runtime.tool_registry.lookup(name)
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    route(runtime, name, {})
    req = PlumaRequest.from_text('Blocked audio observation fixture')
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


@pytest.mark.parametrize('change', ['unverified', 'adapter', 'proof', 'extra', 'nan', 'scalar'])
def test_volume_verifier_requires_coherent_observation(monkeypatch, change):
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', state)
    result = audio.execute_get_volume({})
    data = dict(result.data)
    updates = {}
    if change == 'unverified': updates['verified'] = False
    if change == 'adapter': updates['adapter_used'] = 'unknown'
    if change == 'proof': updates['verify_detail'] = None
    if change == 'extra': data['fake'] = True
    if change == 'nan': data['scalar'] = float('nan')
    if change == 'scalar': data['volume'] = 99
    assert not audio.verify_volume_observation(result.model_copy(update={'data': data, **updates})).ok


@pytest.mark.parametrize('route_mode', list(RouteMode))
def test_audio_catalog_schema_visibility(runtime, route_mode):
    names = {s['name'] for s in ToolSubsetSelector(runtime.tool_registry).select_schemas(route_mode)}
    assert {'get_volume', 'list_audio_devices'}.issubset(names) == (route_mode in (RouteMode.SMART, RouteMode.DEEP))


def test_explicit_emulation_is_identified_in_result_and_proof(monkeypatch):
    monkeypatch.setenv('PLUMA_EMULATE_AUDIO', '1')
    result = audio.execute_get_volume({})
    assert result.ok and result.data['is_mock'] and result.adapter_used == 'emulated'
    assert 'Fixture' in result.factual_message and 'Fixture' in result.verify_detail.detail
    monkeypatch.delenv('PLUMA_EMULATE_AUDIO')
    assert not audio.verify_volume_observation(result).ok


def test_native_setter_checks_endpoint_identity_before_any_write(monkeypatch):
    monkeypatch.delenv('PLUMA_EMULATE_AUDIO', raising=False)
    device = SimpleNamespace(GetId=lambda: 'replacement',
                             Activate=lambda *args: pytest.fail('Wrong endpoint activated'))
    monkeypatch.setattr(native, '_enumerator', lambda: SimpleNamespace(GetDefaultAudioEndpoint=lambda *args: device))
    assert not audio._set_audio_endpoint_volume(level=42, expected_endpoint='original')


def test_com_apartment_is_balanced_on_operation_failure(monkeypatch):
    import comtypes
    calls = []
    monkeypatch.setattr(comtypes, 'CoInitialize', lambda: calls.append('init'))
    monkeypatch.setattr(comtypes, 'CoUninitialize', lambda: calls.append('uninit'))
    def fail():
        calls.append('operation')
        raise OSError('fixture failure')
    with pytest.raises(OSError):
        native._with_com(fail)
    assert calls == ['init', 'operation', 'uninit']


@pytest.mark.parametrize('change', ['duplicate', 'count', 'truncated', 'state', 'flow', 'extra'])
def test_malformed_device_enumeration_fails_closed(monkeypatch, change):
    data = {'devices': [{'endpoint_id': 'fixture', 'name': None, 'state': 1, 'flow': 'render'}],
            'observed_device_count': 1, 'truncated': False}
    if change == 'duplicate': data['devices'] *= 2; data['observed_device_count'] = 2
    if change == 'count': data['observed_device_count'] = 0
    if change == 'truncated': data['truncated'] = True
    if change == 'state': data['devices'][0]['state'] = 3
    if change == 'flow': data['devices'][0]['flow'] = 'invented'
    if change == 'extra': data['devices'][0]['script'] = 'ignored'
    monkeypatch.setattr(native, 'list_devices', lambda *args: data)
    result = audio.execute_list_audio_devices({'max_entries': 64})
    assert not result.ok and not result.verified and not result.data
