"""P11 policy/intent boundary: owned files, SQLite, inert approval handlers."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading

import pytest

from pluma.core import job_object
from pluma.core.cancellation import TaskCancelledError
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyDecision, PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools.base import RiskClass, ToolSpec, ToolResult, VerifyResult
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_runtime_shutdown import runtime, task, NATIVE_JOB, reopened


@pytest.mark.parametrize('risk', [RiskClass.MEDIUM, RiskClass.HIGH])
def test_unknown_intent_requires_explicit_exact_call_approval(risk):
    result = PolicyEngine().evaluate('probe', {}, default_risk=risk, task_id='owned')
    assert result.decision == PolicyDecision.REQUIRE_CONFIRMATION and not result.allowed


@pytest.mark.parametrize('risk', [RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.ADMIN, RiskClass.DENY])
@pytest.mark.parametrize('override', ['READ', 'LOW'])
def test_configuration_cannot_lower_registered_safety_floor(risk, override):
    engine = PolicyEngine(rules=PolicyRules(overrides={'probe': override}))
    result = engine.evaluate('probe', {}, default_risk=risk, task_id='owned')
    assert result.risk_class == risk and not result.allowed


@pytest.mark.parametrize('fault', ['deny', 'truthy', 'missing', 'throw', 'mutate'])
def test_malformed_or_changed_approval_fails_closed_without_mutating_arguments(fault):
    arguments = {'target': {'path': 'owned-fixture'}}
    def callback(request):
        if fault == 'mutate': request.arguments['target']['path'] = 'other'
        if fault == 'throw': raise RuntimeError('password=private-fixture-secret')
        if fault == 'missing': return None
        return ConfirmationResponse(approved='yes' if fault == 'truthy' else fault == 'mutate',
                                    reason='token=private-fixture-secret')
    result = PolicyEngine(confirmation_contract=CallbackConfirmationContract(callback)).evaluate(
        'probe', arguments, default_risk=RiskClass.MEDIUM, task_id='owned')
    assert result.decision == PolicyDecision.DENY
    assert arguments == {'target': {'path': 'owned-fixture'}}
    assert 'private-fixture-secret' not in result.reason


def test_approval_is_requested_for_each_call_and_no_session_blanket_is_applied():
    seen = []
    def callback(request):
        seen.append((request.task_id, request.tool_name, request.arguments))
        return ConfirmationResponse(approved=len(seen) == 1, remember_for_session=True)
    engine = PolicyEngine(confirmation_contract=CallbackConfirmationContract(callback))
    assert engine.evaluate('move_file', {'source': 'a', 'destination': 'b'},
        RiskClass.MEDIUM, 'first').allowed
    assert not engine.evaluate('move_file', {'source': 'a', 'destination': 'c'},
        RiskClass.MEDIUM, 'second').allowed
    assert seen == [('first', 'move_file', {'source': 'a', 'destination': 'b'}),
                    ('second', 'move_file', {'source': 'a', 'destination': 'c'})]


def test_high_risk_safe_delete_confirmation_names_recycle_bin_effect_and_exact_target():
    seen = []
    engine = PolicyEngine(confirmation_contract=CallbackConfirmationContract(
        lambda request: seen.append(request) or ConfirmationResponse(approved=True)))
    path = r'C:\PLUMA-P11-fixture\owned.txt'
    result = engine.evaluate('safe_delete', {'path': path}, RiskClass.HIGH, 'owned-delete-fixture')
    assert result.decision == PolicyDecision.ALLOW and len(seen) == 1
    request = seen[0]
    assert request.prompt_message == (
        'Move this exact item to the Windows Recycle Bin? It may be restored from there. '
        'PLUMA will not permanently delete it.')
    assert request.target_summary == 'Target: ' + path
    assert request.arguments == {'path': path} and not result.requires_confirmation


def test_medium_without_approval_never_captures_prestate_or_mutates_and_logs_denial(runtime, monkeypatch, tmp_path):
    source, destination = tmp_path / 'source', tmp_path / 'destination'
    source.write_bytes(b'unchanged')
    spec = runtime.tool_registry.lookup('move_file')
    monkeypatch.setattr(spec, 'undo_builder', lambda args: pytest.fail('Denied operation reached pre-state'))
    cap = task(runtime)
    result = runtime.tool_registry.execute('move_file', {'source': str(source), 'destination': str(destination)}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED'
    assert source.read_bytes() == b'unchanged' and not destination.exists() and not cap.undo_stack
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert row['risk'] == 'MEDIUM' and row['approval_state'] == 'REQUIRE_CONFIRMATION'
    assert not row['verified'] and json.loads(row['result_json']) == {'executed': False}


def test_scoped_approval_real_move_undo_and_reopened_history(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    seen = []
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: seen.append(request) or ConfirmationResponse(approved=True))
    source, destination = tmp_path / 'before', tmp_path / 'after'
    source.write_bytes(b'owned original')
    cap = task(runtime)
    result = runtime.tool_registry.execute('move_file', {'source': str(source), 'destination': str(destination)}, cap, runtime.ledger)
    assert result.ok and result.verified and not source.exists() and destination.read_bytes() == b'owned original'
    assert len(seen) == 1 and seen[0].task_id == cap.task_id and seen[0].risk_class == RiskClass.MEDIUM
    assert seen[0].arguments['source'] == str(source) and seen[0].arguments['destination'] == str(destination)
    query = ActivityQuery(runtime.db)
    row = query.actions_for_task(cap.task_id)[0]
    assert row['approval_state'] == 'ALLOW' and row['risk'] == 'MEDIUM' and row['verified']
    assert len(query.available_undo_records_for_task(cap.task_id)) == 1
    runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert cap.state.value == 'STOPPED' and source.read_bytes() == b'owned original' and not destination.exists()
    assert not query.available_undo_records_for_task(cap.task_id) and not cap.undo_stack
    assert runtime.close(3).complete
    reopened(runtime, cap)


def probe(runtime, executor, undo=None, timeout=1):
    runtime.tool_registry.register(ToolSpec(name='policy_probe', description='Owned policy fixture',
        args_schema={'type': 'object', 'additionalProperties': False}, risk_class=RiskClass.MEDIUM,
        timeout_s=timeout, executor=executor, undo_builder=undo,
        verifier=lambda result: VerifyResult(ok=True, method='state', detail='Fixture readback')))


def test_schema_precedes_approval_and_failed_prestate_prevents_execution(runtime):
    approvals, executed = [], []
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: approvals.append(request) or ConfirmationResponse(approved=True))
    def fail(args):
        raise OSError('token=private-fixture-secret')
    probe(runtime, lambda args: executed.append(True), undo=fail)
    cap = task(runtime)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('policy_probe', {'approved': True}, cap, runtime.ledger)
    assert not approvals
    result = runtime.tool_registry.execute('policy_probe', {}, cap, runtime.ledger)
    assert result.error_code == 'UNDO_PRESTATE_FAILED' and not result.ok and not executed
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert not row['verified'] and 'private-fixture-secret' not in json.dumps(row)


@pytest.mark.parametrize('stop', [False, True], ids=['timeout', 'stop'])
def test_pending_approval_is_owned_late_approval_cannot_execute_and_storage_stays_open(runtime, stop):
    entered, release = threading.Event(), threading.Event()
    executed = []
    def callback(request):
        entered.set()
        assert release.wait(5)
        return ConfirmationResponse(approved=True)
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(callback)
    probe(runtime, lambda args: executed.append(True) or ToolResult.success('policy_probe'), timeout=2 if stop else 0.05)
    cap = task(runtime)
    try:
        with ThreadPoolExecutor(1) as pool:
            running = pool.submit(runtime.tool_registry.execute, 'policy_probe', {}, cap, runtime.ledger)
            assert entered.wait(2)
            if stop:
                cap.cancellation_token.cancel()
                with pytest.raises(TaskCancelledError): running.result(2)
            else:
                result = running.result(2)
                assert result.error_code == 'POLICY_TIMEOUT' and not result.ok
            assert not executed and runtime.tool_registry.work_gate.pending_futures()
            assert all(row['command_class'] == 'policy' for row in runtime.tool_registry.work_gate.pending_futures())
            assert not runtime.close(0.05).complete and runtime.db.is_open
    finally:
        release.set()
    assert runtime.close(3).complete and not executed
    reopened(runtime, cap)


def test_restricted_argument_values_are_not_written_to_policy_logs(caplog):
    with caplog.at_level('WARNING'):
        result = PolicyEngine().evaluate('probe', {'script': 'bcdedit token=private-fixture-secret'},
                                          RiskClass.HIGH, 'owned')
    assert result.decision == PolicyDecision.DENY and 'private-fixture-secret' not in caplog.text


def test_read_policy_allows_verified_memory_read_and_logs(runtime, monkeypatch):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    cap = task(runtime)
    result = runtime.tool_registry.execute('get_preference', {'key': 'policy.read.fixture'}, cap, runtime.ledger)
    assert result.ok and result.verified
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert row['tool'] == 'get_preference' and row['risk'] == 'READ'
    assert row['approval_state'] == 'ALLOW' and row['verified']


def test_low_policy_allows_verified_reversible_file_action_and_logs(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    cap = task(runtime)
    folder = tmp_path / 'policy-low-folder'
    result = runtime.tool_registry.execute('create_folder', {'path': str(folder)}, cap, runtime.ledger)
    assert result.ok and result.verified and folder.is_dir()
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    undo = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    assert row['tool'] == 'create_folder' and row['risk'] == 'LOW'
    assert row['approval_state'] == 'ALLOW' and row['verified'] and len(undo) == 1


def test_explicit_deny_is_logged_and_executor_never_runs(runtime):
    calls = []
    runtime.tool_registry.register(ToolSpec(name='policy_explicit_deny_probe', description='Deny fixture',
        args_schema={'type': 'object', 'additionalProperties': False}, risk_class=RiskClass.LOW,
        timeout_s=1, executor=lambda args: calls.append(True) or ToolResult.success(
            'policy_explicit_deny_probe', factual_message='Inert fixture.'),
        verifier=lambda result: VerifyResult(ok=True, method='fixture', detail='Inert readback.')))
    runtime.tool_registry._policy_engine = PolicyEngine(
        rules=PolicyRules(overrides={'policy_explicit_deny_probe': 'DENY'}))
    cap = task(runtime)
    result = runtime.tool_registry.execute('policy_explicit_deny_probe', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not calls
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert row['approval_state'] == 'DENY' and not row['verified']
    assert json.loads(row['result_json']) == {'executed': False}


def test_secret_arguments_and_result_data_are_redacted_in_persisted_history(runtime):
    secret = 'private-fixture-secret-92741'
    runtime.tool_registry.register(ToolSpec(name='policy_redaction_probe', description='Redaction fixture',
        args_schema={'type': 'object', 'properties': {'password': {'type': 'string'}},
                     'required': ['password'], 'additionalProperties': False},
        risk_class=RiskClass.READ, timeout_s=1,
        executor=lambda args: ToolResult.success('policy_redaction_probe',
            data={'password': args['password']}, factual_message='Read fixture value.'),
        verifier=lambda result: VerifyResult(ok=True, method='fixture', detail='Inert readback.')))
    cap = task(runtime)
    result = runtime.tool_registry.execute('policy_redaction_probe', {'password': secret}, cap, runtime.ledger)
    assert result.ok and result.verified
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert secret not in json.dumps(row)
