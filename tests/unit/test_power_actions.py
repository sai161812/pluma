"""System-action pipeline fixtures. Never lock/suspend/restart/shut down the host."""
from contextlib import contextmanager
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import power_actions as native
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.ownership import subprocess_absent
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.rules import PolicyRules
from pluma.tools import power_actions as tools
from pluma.tools.base import VerifyResult
from pluma.tools.base import RiskClass, ToolSpec
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop

KINDS = ['lock', 'sleep_request', 'restart_request', 'shutdown_request']


@contextmanager
def inert_system(kind, *, after=False, ignore=False):
    names = ('capture', 'initiate', 'session_state', 'sleep_times', 'event_baseline', 'shutdown_event', 'time')
    saved = {name: getattr(native, name) for name in names}
    state = {'after': after, 'calls': 0}
    def session(): return {'session_id': 7, 'connection_state': 0, 'locked': state['after']}
    def sleep(): return {'sleep_100ns': 30 if state['after'] else 10, 'wake_100ns': 40 if state['after'] else 20}
    def capture(tool):
        return session() if tool == 'lock' else sleep() if tool == 'sleep_request' else {'event_baseline': 5}
    def initiate(tool, args, operation, *, token=None):
        state['calls'] += 1
        if not ignore: state['after'] = True
    def event(tool, operation, baseline):
        return {'record_id': 6, 'event_id': 1074, 'operation_id': operation, 'kind': tool} if state['after'] else None
    native.capture, native.initiate, native.session_state, native.sleep_times = capture, initiate, session, sleep
    native.event_baseline, native.shutdown_event = lambda: 5, event
    if ignore:
        ticks = iter([0, 4])
        native.time = SimpleNamespace(monotonic=lambda: next(ticks), sleep=lambda *args: None)
    try:
        yield state
    finally:
        for name, value in saved.items(): setattr(native, name, value)


@dataclass
class FixtureCapture:
    tool: str
    def __call__(self, args, context):
        with inert_system(self.tool):
            return tools.capture_intent(args, context, tool=self.tool)


@dataclass
class FixtureExecute:
    tool: str
    storage_path: str
    ignore: bool = False
    def __call__(self, args, context):
        from pluma.memory.tool_store import connect
        with connect(self.storage_path) as db:
            record = db.execute('SELECT undo_json,available FROM undo_records ORDER BY action_id DESC LIMIT 1').fetchone()
            assert record is not None and record['available'] == 0
            assert json.loads(record['undo_json'])['pre_state']['non_undoable'] is True
        with inert_system(self.tool, ignore=self.ignore):
            result = tools.execute_power(args, context, tool=self.tool)
        return result.model_copy(update={'adapter_used': 'fixture_system', 'factual_message':
            'Fixture system transition observed; no OS action initiated.' if result.ok else 'Fixture system transition was not verified.'})


@dataclass
class FixtureVerifier:
    tool: str
    def __call__(self, result):
        with inert_system(self.tool, after=True):
            checked = tools.verify_power(result.model_copy(update={'adapter_used': 'native_api'}))
        return VerifyResult(ok=checked.ok, method='fixture_system_readback', detail='Inert system interface fixture only.')


def bind_fixture(runtime, monkeypatch, tool, *, ignore=False):
    spec = runtime.tool_registry.lookup(tool)
    monkeypatch.setattr(spec, 'undo_builder', FixtureCapture(tool))
    monkeypatch.setattr(spec, 'executor', FixtureExecute(tool, str(runtime.paths.db_path), ignore))
    monkeypatch.setattr(spec, 'verifier', FixtureVerifier(tool))
    return spec


@pytest.mark.parametrize('tool', KINDS)
@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_inert_confirmed_system_pipeline_has_intent_before_dispatch_and_no_undo(runtime, monkeypatch, tool, input_mode):
    decisions = approved(runtime, monkeypatch)
    bind_fixture(runtime, monkeypatch, tool)
    args = {'delay_seconds': 30} if tool in ('restart_request', 'shutdown_request') else {}
    plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool=tool, arguments=args, purpose='Inert confirmed system fixture')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.SMART, reason='Inert system fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Inert system-action fixture'))
    assert result.success and result.final_state == 'SUCCEEDED', result
    observed = result.steps[0].result
    assert observed.ok and observed.verified and observed.adapter_used == 'fixture_system'
    assert observed.undo_record is None and observed.data['non_undoable'] is True and observed.data['effect_state'] == 'committed'
    assert len(decisions) == 1 and decisions[0].risk_class.value == 'HIGH'
    assert decisions[0].arguments == args and ('cannot' in decisions[0].prompt_message or 'STOP' in decisions[0].prompt_message)
    if tool in ('restart_request', 'shutdown_request'):
        assert '30 seconds' in decisions[0].prompt_message and 'not be forcibly closed' in decisions[0].prompt_message
    cap = runtime.supervisor.get_task(result.task_id)
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    assert cap.undo_stack[-1]['non_undoable'] and cap.undo_stack[-1]['effect_state'] == 'committed'
    assert cap.worker_controller is cap.job_object is None
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(rows) == 1 and rows[0]['verified'] and rows[0]['risk'] == 'HIGH'


@pytest.mark.parametrize('tool', KINDS)
def test_system_call_return_without_effect_readback_stays_unknown(runtime, monkeypatch, tool):
    approved(runtime, monkeypatch)
    bind_fixture(runtime, monkeypatch, tool, ignore=True)
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, {}, cap, runtime.ledger)
    assert not result.ok and not result.verified and result.error_code == 'SYSTEM_EFFECT_UNVERIFIED'
    assert result.data['effect_state'] == 'unknown' and result.data['non_undoable'] is True
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('tool', KINDS)
def test_system_denial_has_no_capture_or_dispatch(runtime, monkeypatch, tool):
    runtime.policy_engine.rules = PolicyRules(overrides={tool: 'DENY'})
    spec = runtime.tool_registry.lookup(tool)
    monkeypatch.setattr(spec, 'undo_builder', lambda *args: pytest.fail('Denied system capture'))
    monkeypatch.setattr(spec, 'executor', lambda *args: pytest.fail('Denied system dispatch'))
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not cap.undo_stack


@pytest.mark.parametrize('tool,args', [('lock', {'unlock': True}), ('sleep_request', {'hibernate': True}),
    ('restart_request', {'delay_seconds': 0}), ('shutdown_request', {'delay_seconds': True}),
    ('restart_request', {'delay_seconds': 301}), ('shutdown_request', {'force': True}), ('shutdown_request', {'machine': 'remote'})])
def test_system_schema_refuses_force_remote_and_unbounded_inputs_before_policy(runtime, tool, args):
    runtime.tool_registry._policy_engine = SimpleNamespace(evaluate=lambda **kwargs: pytest.fail('Invalid system schema reached policy'))
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute(tool, args)
    assert not runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('tool', KINDS)
def test_system_risk_cannot_be_downgraded_and_confirmation_is_exact(runtime, monkeypatch, tool):
    from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
    decisions = []
    runtime.policy_engine.rules = PolicyRules(overrides={tool: 'LOW'})
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: decisions.append(request) or ConfirmationResponse(approved=False))
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, {}, cap, runtime.ledger)
    assert not result.ok and len(decisions) == 1 and decisions[0].risk_class.value == 'HIGH' and not cap.undo_stack


@pytest.mark.parametrize('tool', KINDS)
def test_system_without_policy_cannot_capture_or_dispatch(runtime, monkeypatch, tool):
    approved(runtime, monkeypatch)
    bind_fixture(runtime, monkeypatch, tool)
    runtime.tool_registry._policy_engine = None
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_REQUIRED' and not cap.undo_stack


@pytest.mark.parametrize('risk', [RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.ADMIN, RiskClass.DENY, RiskClass.RESTRICTED])
def test_missing_policy_blocks_all_risks_requiring_a_decision_before_capture(runtime, risk):
    runtime.tool_registry._policy_engine = None
    runtime.tool_registry.register(ToolSpec(name='inert_policy_boundary', description='Inert unavailable-policy boundary',
        args_schema=tools.EmptyArgs, risk_class=risk, timeout_s=1, process_isolated=True,
        undo_builder=lambda *args: pytest.fail('Policy-free capture'),
        executor=lambda *args: pytest.fail('Policy-free dispatch'),
        verifier=lambda *args: pytest.fail('Policy-free verification')))
    cap = task(runtime)
    result = runtime.tool_registry.execute('inert_policy_boundary', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_REQUIRED' and not cap.undo_stack
    assert not runtime.tool_registry._worker_controllers


def test_native_system_precondition_reads_do_not_initiate_any_action(monkeypatch):
    monkeypatch.setattr(native, 'initiate', lambda *args: pytest.fail('Read-only probe initiated power'))
    tools.LockState.model_validate(native.session_state())
    tools.SleepState.model_validate(native.sleep_times())
    baseline = native.event_baseline()
    assert type(baseline) is int and baseline >= 0
    assert native.shutdown_event('restart_request', '459160b5-ddaa-4a16-b729-6556a0036511', baseline) is None


@pytest.mark.parametrize('tool', KINDS)
def test_native_initiation_flags_are_local_non_forced_and_closed(monkeypatch, tool):
    import ctypes
    from ctypes import wintypes
    from contextlib import nullcontext
    calls = []
    class Call:
        def __init__(self, name): self.name = name
        def __call__(self, *args): calls.append((self.name, args)); return 1
    dll = SimpleNamespace(LockWorkStation=Call('lock'), SetSuspendState=Call('sleep'), InitiateSystemShutdownExW=Call('shutdown'))
    fake_c = SimpleNamespace(WinDLL=lambda *args, **kwargs: dll, c_ubyte=ctypes.c_ubyte)
    monkeypatch.setattr(native, '_api', lambda: (fake_c, wintypes))
    monkeypatch.setattr(native, '_shutdown_privilege', lambda: nullcontext())
    native.initiate(tool, {'delay_seconds': 30}, '459160b5-ddaa-4a16-b729-6556a0036511')
    assert len(calls) == 1
    if tool == 'sleep_request': assert calls[0] == ('sleep', (False, False, False))
    elif tool == 'lock': assert calls[0] == ('lock', ())
    else:
        _, args = calls[0]
        assert args[0] is None and args[2] == 30 and args[3] is False and args[4] == (tool == 'restart_request')
        assert args[5] == 0x80040000 and tool in args[1]


@pytest.mark.parametrize('fail', [False, True])
def test_shutdown_privilege_is_restored_and_token_closed(monkeypatch, fail):
    import win32api
    import win32security as security
    state = {'enabled': 0, 'closed': False}
    token = SimpleNamespace(Close=lambda: state.update(closed=True))
    monkeypatch.setattr(security, 'OpenProcessToken', lambda *args: token)
    monkeypatch.setattr(security, 'LookupPrivilegeValue', lambda *args: 42)
    monkeypatch.setattr(security, 'GetTokenInformation', lambda *args: [(42, state['enabled'])])
    def adjust(token, disable, values):
        previous = [(42, state['enabled'])]
        state['enabled'] = dict(values).get(42, state['enabled'])
        return previous
    monkeypatch.setattr(security, 'AdjustTokenPrivileges', adjust)
    monkeypatch.setattr(win32api, 'GetLastError', lambda: 0)
    try:
        with native._shutdown_privilege():
            assert state['enabled'] == security.SE_PRIVILEGE_ENABLED
            if fail: raise OSError('inert operation failure')
    except OSError:
        assert fail
    assert state['enabled'] == 0 and state['closed']


@pytest.mark.parametrize('tool', ['sleep_request', 'restart_request', 'shutdown_request'])
def test_stop_during_privilege_preparation_prevents_native_commit(monkeypatch, tool):
    import ctypes
    from ctypes import wintypes
    from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
    token = CancellationToken()
    restored = []
    @contextmanager
    def preparation():
        token.cancel(StopReason.USER_STOP)
        try: yield
        finally: restored.append(True)
    class Call:
        def __call__(self, *args): pytest.fail('Native commit began after STOP')
    dll = SimpleNamespace(SetSuspendState=Call(), InitiateSystemShutdownExW=Call())
    fake_c = SimpleNamespace(WinDLL=lambda *args, **kwargs: dll, c_ubyte=ctypes.c_ubyte)
    monkeypatch.setattr(native, '_api', lambda: (fake_c, wintypes))
    monkeypatch.setattr(native, '_shutdown_privilege', preparation)
    with pytest.raises(TaskCancelledError):
        native.initiate(tool, {'delay_seconds': 30}, '459160b5-ddaa-4a16-b729-6556a0036511', token=token)
    assert restored == [True]


@pytest.mark.parametrize('tool', KINDS)
@pytest.mark.parametrize('stop', [True, False])
def test_blocked_system_worker_is_owned_and_keeps_nonundoable_uncertainty(runtime, monkeypatch, tmp_path, tool, stop):
    approved(runtime, monkeypatch)
    spec = bind_fixture(runtime, monkeypatch, tool)
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
        future = pool.submit(runtime.tool_registry.execute, tool, {}, cap, runtime.ledger)
        try:
            await_file(tmp_path / 'entered', future)
            if stop: runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = future.result(3)
        finally:
            if not future.done(): runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.ok and not result.verified
    assert proc._closed and controller._proc is None
    assert subprocess_absent(identity['pid'], identity['creation_time']) is True
    assert controller.verify_cleanup() and not (tmp_path / 'late').exists()
    assert cap.undo_stack[-1]['non_undoable'] and cap.undo_stack[-1]['effect_state'] == 'unknown'
