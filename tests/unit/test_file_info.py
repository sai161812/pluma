"""P11 file_info: owned Windows files, native workers/Jobs/SQLite, no desktop."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
from types import SimpleNamespace

import pytest

from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.stop_protocol import StopReply, StopOutcome
from pluma.memory.activity import ActivityQuery
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.tools import files
from pluma.tools.base import ToolResult
from pluma.tools.registry import ToolArgumentError, UnknownToolError
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop
from pluma.tools.registry import WorkerRequest


@pytest.mark.parametrize('arguments', [
    {}, {'path': ''}, {'path': ' '}, {'path': 3}, {'path': True}, {'path': None},
    {'path': 'relative.txt'}, {'path': r'C:relative.txt'}, {'path': r'\rooted.txt'},
    {'path': r'C:\fixture\*.txt'}, {'path': r'C:\fixture\?.txt'},
    {'path': r'C:\fixture\..\other'}, {'path': r'C:\fixture\file:stream'},
    {'path': r'C:\fixture\name.'}, {'path': r'C:\fixture\name '},
    {'path': r'\\.\pipe\fixture'}, {'path': '//./C:/fixture'},
    {'path': r'\\?\C:\fixture'}, {'path': r'C:\NUL'}, {'path': r'C:\NUL\child'},
    {'path': 'C:\\fixture\\null\0file'}, {'path': r'C:\fixture', 'command': 'ignored'},
])
def test_ambiguous_or_invalid_schema_precedes_policy_and_io(runtime, arguments):
    class NoPolicy:
        def evaluate(self, **kwargs):
            pytest.fail('Invalid call reached policy')
    runtime.tool_registry._policy_engine = NoPolicy()
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('file_info', arguments)
    assert not runtime.tool_registry._worker_controllers


def test_unknown_tool_cannot_dispatch_file_info(runtime):
    with pytest.raises(UnknownToolError):
        runtime.tool_registry.execute('file_info_unknown', {'path': r'C:\fixture'})
    assert not runtime.tool_registry._worker_controllers


def route(runtime, arguments, route_mode=RouteMode.FAST):
    plan = Plan(route=route_mode, steps=[ToolCall(tool='file_info', arguments=arguments, purpose='Read metadata')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=route_mode, reason='P11 typed fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)


@pytest.mark.parametrize('kind', ['file', 'directory'])
@pytest.mark.parametrize('mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_metadata_policy_history_and_verified_shutdown(runtime, monkeypatch, tmp_path, kind, mode):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    target = tmp_path / 'Unicode 雪 and spaces'
    if kind == 'file':
        target.write_bytes(b'private fixture content is never returned')
    else:
        target.mkdir()
        (target / 'child.txt').write_bytes(b'not enumerated')
    before = target.stat()
    route(runtime, {'path': str(target)})
    request = PlumaRequest(input_mode=mode, text='Inspect fixture metadata')
    cap = runtime.supervisor.create_task(request.request_id)
    native_job = cap.job_object
    result = runtime.orchestrator.execute(request, cap)
    assert result.success and result.final_state == 'SUCCEEDED'
    tool = result.steps[0].result
    assert tool.ok and tool.verified and tool.adapter_used == 'native_api'
    assert tool.data == {'path': str(target), 'kind': kind,
        'size_bytes': before.st_size if kind == 'file' else None,
        'modified_ns': before.st_mtime_ns, 'device': before.st_dev, 'file_id': before.st_ino}
    after = target.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    if kind == 'file':
        assert target.read_bytes() == b'private fixture content is never returned'
    else:
        assert list(target.iterdir()) == [target / 'child.txt']
    query = ActivityQuery(runtime.db)
    action = query.actions_for_task(cap.task_id)[0]
    assert action['tool'] == 'file_info' and action['risk'] == 'READ' and action['verified']
    assert 'private fixture content' not in json.dumps(action) and 'child.txt' not in json.dumps(tool.data)
    assert not query.available_undo_records_for_task(cap.task_id) and cap.undo_stack == []
    evidence = next(e for e in cap.cleanup_evidence if e.kind == 'worker' and 'pid' in e.identity)
    assert evidence.verified and evidence.identity['task_id'] == cap.task_id
    assert evidence.identity['creation_time'] > 0 and evidence.identity['ownership'] == 'PLUMA_CREATED'
    assert native_job.is_closed and cap.worker_controller is cap.job_object is None
    assert runtime.close(3).complete
    row = reopened(runtime, cap)
    assert row['input_mode'] == mode.value


def test_policy_denial_happens_before_worker_or_native_read(runtime, tmp_path):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={'file_info': 'DENY'}))
    target = tmp_path / 'absent'
    result = runtime.tool_registry.execute('file_info', {'path': str(target)})
    assert not result.ok and not result.verified and result.error_code == 'POLICY_DENIED'
    assert not runtime.tool_registry._worker_controllers and not target.exists()


def test_native_missing_target_is_factual_failure(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    target = tmp_path / 'absent'
    route(runtime, {'path': str(target)})
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect missing fixture'))
    assert not result.success and result.final_state == 'FAILED'
    tool = result.steps[0].result
    assert not tool.verified and tool.error_code == 'FILE_INFO_NOT_FOUND' and not tool.data
    row = ActivityQuery(runtime.db).actions_for_task(result.task_id)[0]
    assert not row['verified'] and 'FILE_INFO_NOT_FOUND' in row['error_json']
    assert not target.exists()


@pytest.mark.parametrize('error,code', [
    (PermissionError('token=private-fixture-value'), 'FILE_INFO_ACCESS_DENIED'),
    (OSError('password=private-fixture-value'), 'FILE_INFO_READ_FAILED'),
])
def test_native_read_errors_have_fixed_copy_and_no_fake_metadata(monkeypatch, tmp_path, error, code):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(files, '_read_file_info', fail)
    result = files.execute_file_info({'path': str(tmp_path / 'file')})
    assert not result.ok and not result.verified and result.error_code == code and not result.data
    assert 'private-fixture-value' not in result.model_dump_json()


def test_changed_metadata_is_refused_and_fixture_content_preserved(monkeypatch, tmp_path):
    target = tmp_path / 'file'
    target.write_bytes(b'first')
    original = files._read_file_info
    reads = []
    def read(*args, **kwargs):
        result = original(*args, **kwargs)
        reads.append(True)
        if len(reads) == 1:
            target.write_bytes(b'newer fixture content')
        return result
    monkeypatch.setattr(files, '_read_file_info', read)
    result = files.execute_file_info({'path': str(target)})
    assert not result.ok and not result.verified and result.error_code == 'FILE_INFO_CHANGED'
    assert not result.data and target.read_bytes() == b'newer fixture content'


@pytest.mark.parametrize('nested', [False, True])
def test_actual_windows_junction_and_ancestor_are_refused(runtime, monkeypatch, tmp_path, nested):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    target, link = tmp_path / 'target', tmp_path / 'junction'
    target.mkdir()
    (target / 'file.txt').write_bytes(b'unchanged')
    process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
        capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0 and link.is_junction()
    route(runtime, {'path': str(link / 'file.txt' if nested else link)})
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect junction fixture'))
    assert not result.success and result.steps[0].result.error_code == 'FILE_INFO_UNSUPPORTED'
    assert not result.steps[0].result.verified and not result.steps[0].result.data
    assert (target / 'file.txt').read_bytes() == b'unchanged' and link.is_junction()


@pytest.mark.parametrize('change', ['unverified', 'adapter', 'kind', 'size', 'extra'])
def test_verifier_rejects_unproved_or_malformed_results(tmp_path, change):
    data = {'path': str(tmp_path), 'kind': 'directory', 'size_bytes': None,
            'modified_ns': 1, 'device': 1, 'file_id': 1}
    if change == 'kind': data['kind'] = 'invented'
    if change == 'size': data['size_bytes'] = 3
    if change == 'extra': data['contents'] = 'must not be accepted'
    result = ToolResult.success('file_info', data=data, verified=change != 'unverified',
                                adapter_used='unknown' if change == 'adapter' else 'native_api')
    assert not files.verify_file_info(result).ok


@pytest.mark.parametrize('route_mode', [RouteMode.FAST, RouteMode.SMART])
@pytest.mark.parametrize('stop', [False, True], ids=['timeout', 'stop'])
def test_blocked_metadata_worker_is_owned_and_bounded(runtime, monkeypatch, tmp_path, stop, route_mode):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    # Inject blocked native work in the registered READ tool, preserving the
    # real process-isolation policy, capsule, controller, Jobs and timeout path.
    spec = runtime.tool_registry.lookup('file_info')
    monkeypatch.setattr(spec, "executor", OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, "timeout_s", 10 if stop else 1)
    route(runtime, {'path': str(tmp_path)}, route_mode)
    req = PlumaRequest.from_text('Blocked metadata fixture')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
    # This case measures a blocked response deadline, separately from cold
    # spawn/import. Warm the same task-owned worker with a bounded inert read.
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    status, _ = controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'worker_probe', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)
    assert status == 'ok'
    warmed_identity = dict(controller.worker_identity)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.orchestrator.execute, req, cap)
        try:
            await_file(tmp_path / 'entered', running)
            controller = cap.worker_controller
            proc = controller._proc
            assert controller.worker_identity == warmed_identity
            assert controller.worker_identity['task_id'] == cap.task_id
            if stop:
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.success and not proc.is_alive() and controller.verify_cleanup() is True
    assert result.final_state == ('STOPPED' if stop else 'FAILED')
    if not stop:
        assert 'user request' not in (result.error or '').lower()
    assert result.steps[0].result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert cap.cancellation_token.reason == (StopReason.USER_STOP if stop else StopReason.TASK_TIMEOUT)
    row = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    assert row['stop_reason'] == cap.cancellation_token.reason.value and row['final_state'] == result.final_state
    receipt = StopReply.model_validate_json(json.dumps(runtime.resident_core.handle_ipc_command(
        {'command': 'stop_task', 'task_id': cap.task_id})))
    item = receipt.tasks[0]
    assert item.final_state == result.final_state == cap.state.value
    assert item.terminal_persisted is result.terminal_persisted is True
    assert [entry.model_dump() for entry in item.cleanup_evidence] == result.cleanup_evidence
    assert item.outcome == (StopOutcome.STOPPED if stop else StopOutcome.ERROR)
    assert receipt.stopped_count == int(stop)
    assert not (tmp_path / 'late').exists() and cap.undo_stack == []
    assert runtime.close(3).complete
    reopened(runtime, cap)


@pytest.mark.parametrize('first', [StopReason.USER_STOP, StopReason.TASK_TIMEOUT])
def test_timeout_user_stop_race_preserves_first_cause_and_terminal_history(runtime, first):
    cap = task(runtime, 'p11-first-cause')
    cap.cancellation_token.cancel(first)
    later = StopReason.USER_STOP if first == StopReason.TASK_TIMEOUT else StopReason.TASK_TIMEOUT
    runtime.supervisor.fail_task_with_rollback(cap.task_id)
    runtime.supervisor.stop_task(cap.task_id, reason=later, grace_s=0)
    assert cap.cancellation_token.reason == first
    assert cap.state.value == ('FAILED' if first == StopReason.TASK_TIMEOUT else 'STOPPED')
    row = ActivityQuery(runtime.db).task_by_id(cap.task_id)
    assert row['stop_reason'] == first.value and row['final_state'] == cap.state.value
    assert cap.terminal_persisted is True and cap.terminal_ready.is_set()


@pytest.mark.parametrize('route_mode', list(RouteMode))
def test_file_info_schema_is_discoverable_only_in_file_capable_routes(runtime, route_mode):
    schemas = ToolSubsetSelector(runtime.tool_registry).select_schemas(route_mode, command='Inspect file metadata')
    names = [schema['name'] for schema in schemas]
    assert ('file_info' in names) is (route_mode in (RouteMode.SMART, RouteMode.DEEP))
    if 'file_info' in names:
        schema = next(schema for schema in schemas if schema['name'] == 'file_info')
        assert schema['risk_class'] == 'READ'
        assert schema['args_schema']['required'] == ['path']
        assert schema['args_schema']['additionalProperties'] is False


def test_denied_file_request_has_factual_history_without_exposing_target(runtime, tmp_path):
    runtime.tool_registry._policy_engine = PolicyEngine(rules=PolicyRules(overrides={'file_info': 'DENY'}))
    target = tmp_path / 'password=private-fixture-target'
    route(runtime, {'path': str(target)})
    result = runtime.orchestrator.execute(PlumaRequest.from_text('Inspect denied fixture'))
    assert not result.success and result.final_state == 'FAILED'
    assert result.steps[0].result.error_code == 'POLICY_DENIED'
    cap = runtime.supervisor.get_task(result.task_id)
    assert cap.worker_controller is None and not runtime.tool_registry._worker_controllers
    query = ActivityQuery(runtime.db)
    row = query.task_by_id(cap.task_id)
    assert row['final_state'] == 'FAILED' and cap.terminal_persisted is True
    actions = query.actions_for_task(cap.task_id)
    assert len(actions) == 1 and not actions[0]['verified']
    assert json.loads(actions[0]['result_json']) == {'executed': False}
    assert actions[0]['approval_state'] == 'DENY'
    assert 'private-fixture-target' not in json.dumps(actions)
    assert 'private-fixture-target' not in json.dumps(row) and not target.exists()
    assert not query.available_undo_records_for_task(cap.task_id)
