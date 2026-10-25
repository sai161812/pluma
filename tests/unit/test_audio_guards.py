"""P11 audio identity/conflict checks. Physical settings are never changed."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from pluma.adapters import audio as native
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools import audio
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_runtime_shutdown import runtime
from tests.unit.test_memory_tools import approved, task


def volume(**updates):
    return dict({'endpoint_id': 'fixture:default', 'volume': 35, 'scalar': .35,
                 'muted': False, 'is_mock': True}, **updates)


def pending(tool, state):
    return SimpleNamespace(undo_stack=[{'action': 'pending_mutation', 'tool': tool, 'pre_state': state}])


@pytest.mark.parametrize('tool,args', [('set_volume', {'level': 42}), ('mute', {}), ('unmute', {})])
@pytest.mark.parametrize('change', ['endpoint_id', 'scalar', 'muted'])
def test_captured_audio_edits_refuse_before_mutation(monkeypatch, tool, args, change):
    before = volume()
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: dict(before))
    record = getattr(audio, 'undo_builder_' + tool)(args)
    changed = dict(before)
    changed[change] = {'endpoint_id': 'other-device', 'scalar': .36, 'muted': True}[change]
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: changed)
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: pytest.fail('Changed prestate dispatched'))
    result = getattr(audio, 'execute_' + tool)(args, pending(tool, record))
    assert not result.ok and result.error_code == 'AUDIO_PRESTATE_CONFLICT'


@pytest.mark.parametrize('tool,args', [('set_volume', {'level': 42}), ('mute', {}), ('unmute', {})])
def test_fixture_audio_mutation_manual_undo_has_durable_identity(runtime, monkeypatch, tool, args):
    approved(runtime, monkeypatch)
    monkeypatch.setenv('PLUMA_EMULATE_AUDIO', '1')
    audio._save_mock_audio(level=35, mute=tool == 'unmute')
    before = audio._get_audio_endpoint_volume()
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, args, task_context=cap, ledger=runtime.ledger)
    assert result.ok and result.verified, result
    record = result.undo_record
    assert record['before'] == before and record['action'] == tool and record['guard_version'] == 1
    assert record['after'] == audio._get_audio_endpoint_volume()
    assert not result.private_context
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    inverse_cap = task(runtime)
    inverse = runtime.tool_registry.execute('undo_last', {}, task_context=inverse_cap, ledger=runtime.ledger)
    assert inverse.ok and inverse.verified, inverse
    assert audio._get_audio_endpoint_volume() == before
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('change', ['endpoint_id', 'scalar', 'muted', 'is_mock'])
def test_audio_inverse_preserves_newer_device_or_state(monkeypatch, change):
    before, after = volume(), volume(volume=42, scalar=.42)
    record = dict(audio._volume_record('set_volume', {'level': 42}, before), after=after)
    edited = dict(after)
    edited[change] = {'endpoint_id': 'replacement', 'scalar': .5, 'muted': True, 'is_mock': False}[change]
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: edited)
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: pytest.fail('Conflict inverse dispatched'))
    inverse = RollbackRecipes().apply('set_volume', record)
    assert not inverse.ok and inverse.error == 'ROLLBACK_CONFLICT'


def test_audio_verifier_rechecks_current_state_and_requires_private_receipt(monkeypatch):
    monkeypatch.setenv('PLUMA_EMULATE_AUDIO', '1')
    audio._save_mock_audio(level=35, mute=False)
    result = audio.execute_set_volume({'level': 42})
    assert result.ok and audio.verify_set_volume(result).ok
    assert not audio.verify_set_volume(result.model_copy(update={'private_context': {}})).ok
    audio._save_mock_audio(level=50)
    assert not audio.verify_set_volume(result).ok


def test_owned_audio_inverse_is_drained(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    monkeypatch.setenv('PLUMA_EMULATE_AUDIO', '1')
    audio._save_mock_audio(level=35, mute=False)
    before = audio._get_audio_endpoint_volume()
    cap = task(runtime)
    result = runtime.tool_registry.execute('set_volume', {'level': 42}, task_context=cap, ledger=runtime.ledger)
    assert result.ok and result.verified, result
    rolled = runtime.rollback_engine.rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack)
    assert rolled.all_ok, rolled
    assert audio._get_audio_endpoint_volume() == before and not cap.inverse_workers
    checks = [entry for entry in cap.cleanup_evidence if entry.identity.get('command_class') == 'rollback_worker']
    assert checks and all(entry.verified for entry in checks)


class Device:
    def __init__(self, identifier, flow, state=1):
        self.identifier, self.flow, self.state = identifier, flow, state

    def GetId(self): return self.identifier
    def GetState(self): return self.state
    def QueryInterface(self, *args): return self
    def GetDataFlow(self): return self.flow


class DefaultFixture:
    def __init__(self):
        self.devices = {name: Device(name, flow) for flow in (0, 1) for name in (f'before-{flow}', f'after-{flow}')}
        self.current = {(flow, role): f'before-{flow}' for flow in (0, 1) for role in (0, 1, 2)}
        self.calls = []

    def GetDefaultAudioEndpoint(self, flow, role): return self.devices[self.current[flow, role]]
    def GetDevice(self, identifier): return self.devices[identifier]
    def SetDefaultEndpoint(self, identifier, role):
        self.calls.append((identifier, role))
        self.current[self.devices[identifier].flow, role] = identifier


@pytest.fixture
def defaults(monkeypatch):
    import comtypes
    fixture = DefaultFixture()
    monkeypatch.setattr(native, '_enumerator', lambda: fixture)
    monkeypatch.setattr(comtypes, 'CoCreateInstance', lambda *args: fixture)
    return fixture


@pytest.mark.parametrize('flow', ['render', 'capture'])
@pytest.mark.parametrize('role', ['console', 'multimedia', 'communications'])
def test_default_switch_and_inverse_touch_only_explicit_role(defaults, flow, role):
    flow_id = {'render': 0, 'capture': 1}[flow]
    args = {'endpoint_id': f'after-{flow_id}', 'flow': flow, 'role': role}
    initial = deepcopy(defaults.current)
    record = audio.undo_builder_default(args)
    result = audio.execute_default(args, pending('set_default_audio_device', record))
    assert result.ok and result.verified and audio.verify_default(result).ok, result
    assert len(defaults.calls) == 1
    role_id = {'console': 0, 'multimedia': 1, 'communications': 2}[role]
    assert {key: value for key, value in defaults.current.items() if key != (flow_id, role_id)} == {
        key: value for key, value in initial.items() if key != (flow_id, role_id)}
    inverse = RollbackRecipes().apply('set_default_audio_device', result.undo_record)
    assert inverse.ok and defaults.current == initial


@pytest.mark.parametrize('change', ['wrong_flow', 'inactive', 'missing', 'changed_default'])
def test_default_refuses_changed_or_unavailable_target(defaults, change):
    args = {'endpoint_id': 'after-0', 'flow': 'render', 'role': 'multimedia'}
    record = audio.undo_builder_default(args)
    if change == 'wrong_flow': defaults.devices['after-0'].flow = 1
    if change == 'inactive': defaults.devices['after-0'].state = 2
    if change == 'missing': del defaults.devices['after-0']
    if change == 'changed_default': defaults.current[0, 1] = 'after-0'
    result = audio.execute_default(args, pending('set_default_audio_device', record))
    assert not result.ok and not result.verified and not defaults.calls


def test_default_undo_conflict_and_failed_readback_do_not_succeed(defaults):
    args = {'endpoint_id': 'after-0', 'flow': 'render', 'role': 'multimedia'}
    record = audio.undo_builder_default(args)
    result = audio.execute_default(args, pending('set_default_audio_device', record))
    assert result.ok and len(defaults.calls) == 1
    defaults.current[0, 1] = 'before-0'
    assert not audio.verify_default(result).ok
    inverse = RollbackRecipes().apply('set_default_audio_device', result.undo_record)
    assert not inverse.ok and len(defaults.calls) == 1


@pytest.mark.parametrize('bad', [dict(endpoint_id='x'), dict(endpoint_id='x', flow='both', role='multimedia'),
    dict(endpoint_id='x', flow='render', role='all'), dict(endpoint_id='x', flow='render', role='console', shell='x')])
def test_default_schema_refuses_implicit_or_broad_roles_before_policy(runtime, bad):
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('set_default_audio_device', bad)
    assert not runtime.tool_registry._worker_controllers


def test_native_default_current_endpoint_pipeline_has_no_physical_switch(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    monkeypatch.delenv('PLUMA_EMULATE_AUDIO', raising=False)
    before = native.read_default('render', 'multimedia')
    cap = task(runtime)
    result = runtime.tool_registry.execute('set_default_audio_device', before, task_context=cap, ledger=runtime.ledger)
    assert result.ok and result.verified, result
    assert native.read_default('render', 'multimedia') == before
    assert result.undo_record['before'] == result.undo_record['after'] == before
    inverse = runtime.rollback_engine.rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack)
    assert inverse.all_ok and native.read_default('render', 'multimedia') == before


def test_default_denial_has_no_capture_or_executor(runtime, monkeypatch):
    from pluma.policy.rules import PolicyRules
    runtime.policy_engine.rules = PolicyRules(overrides={'set_default_audio_device': 'DENY'})
    spec = runtime.tool_registry.lookup('set_default_audio_device')
    monkeypatch.setattr(spec, 'undo_builder', lambda *args: pytest.fail('Denied capture'))
    monkeypatch.setattr(spec, 'executor', lambda *args: pytest.fail('Denied execution'))
    cap = task(runtime)
    result = runtime.tool_registry.execute('set_default_audio_device', {
        'endpoint_id': 'fixture', 'flow': 'render', 'role': 'console'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not cap.undo_stack


def test_default_false_setter_return_is_not_success(defaults, monkeypatch):
    args = {'endpoint_id': 'after-0', 'flow': 'render', 'role': 'multimedia'}
    record = audio.undo_builder_default(args)
    monkeypatch.setattr(defaults, 'SetDefaultEndpoint', lambda *args: None)
    result = audio.execute_default(args, pending('set_default_audio_device', record))
    assert not result.ok and defaults.current[0, 1] == 'before-0'


@pytest.mark.parametrize('change', ['target', 'before_endpoint', 'before_mute', 'after_scalar'])
def test_incoherent_audio_receipt_is_refused_before_inverse(monkeypatch, change):
    record = dict(audio._volume_record('set_volume', {'level': 42}, volume()), after=volume(volume=42, scalar=.42))
    if change == 'target': record['target'] = {'level': 70}
    if change == 'before_endpoint': record['before']['endpoint_id'] = 'other'
    if change == 'before_mute': record['before']['muted'] = True
    if change == 'after_scalar': record['after']['scalar'] = .43
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: record['after'])
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: pytest.fail('Malformed receipt dispatched'))
    assert not RollbackRecipes().apply('set_volume', record).ok


def test_audio_restore_preserves_unrounded_scalar(monkeypatch):
    before, after = volume(scalar=.351, is_mock=False), volume(volume=42, scalar=.42, is_mock=False)
    record = dict(audio._volume_record('set_volume', {'level': 42}, before), after=after)
    observations = iter([after, before])
    monkeypatch.setattr(audio, '_get_audio_endpoint_volume', lambda: next(observations))
    calls = []
    monkeypatch.setattr(audio, '_set_audio_endpoint_volume', lambda **kwargs: calls.append(kwargs) or True)
    assert RollbackRecipes().apply('set_volume', record).ok
    assert calls == [{'mute': False, 'expected_endpoint': before['endpoint_id'],
                      'expected_state': after, 'scalar_target': .351}]
