"""Native bounded search fixtures; candidates never imply an execution target."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest

from pluma.adapters import file_search
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core.cancellation import CancellationToken, StopReason
from pluma.core.ownership import subprocess_absent
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.rules import PolicyRules
from pluma.tools import files
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file, owned_noop
from pluma.tools.registry import WorkerRequest


@pytest.mark.parametrize('input_mode', [InputMode.TEXT, InputMode.VOICE])
def test_native_search_pipeline_keeps_duplicate_candidates_without_action(runtime, monkeypatch, tmp_path, input_mode):
    approved(runtime, monkeypatch)
    for name in ('first', 'second'):
        directory = tmp_path / name
        directory.mkdir()
        (directory / 'lecture.pdf').write_bytes(b'owned PDF candidate')
    args = {'directory': str(tmp_path), 'pattern': '*.pdf', 'kind': 'file'}
    plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool='find_file', arguments=args, purpose='Find owned candidates')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.SMART, reason='Owned search fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Find fixture PDF candidates'))
    assert result.success and result.final_state == 'SUCCEEDED', result
    observed = result.steps[0].result
    assert observed.verified and observed.data['count'] == 2 and not observed.data['unambiguous']
    assert not observed.data['limited'] and not observed.private_context
    for candidate in observed.data['matches']:
        assert Path(candidate['path']).read_bytes() == b'owned PDF candidate'
        assert candidate['identity']['file_id'] and candidate['kind'] == 'file'
    cap = runtime.supervisor.get_task(result.task_id)
    assert not cap.undo_stack
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(rows) == 1 and rows[0]['tool'] == 'find_file' and rows[0]['verified']
    assert json.loads(rows[0]['result_json'])['count'] == 2
    assert cap.worker_controller is cap.job_object is None


def test_native_type_time_and_case_insensitive_basename_filters(tmp_path):
    older, newer = tmp_path / 'Old.TXT', tmp_path / 'New.txt'
    older.write_text('before')
    newer.write_text('after')
    os.utime(older, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    os.utime(newer, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
    (tmp_path / 'Folder.txt').mkdir()
    result = files.execute_find_file({'directory': str(tmp_path), 'pattern': '*.txt', 'kind': 'file',
        'modified_after_ns': 1_650_000_000_000_000_000, 'modified_before_ns': 1_750_000_000_000_000_000,
        'created_after_ns': newer.stat().st_birthtime_ns, 'created_before_ns': newer.stat().st_birthtime_ns + 1})
    assert result.ok and result.verified and result.data['unambiguous'], result
    assert [row['name'] for row in result.data['matches']] == ['New.txt']
    directory = files.execute_find_file({'directory': str(tmp_path), 'pattern': '*.TXT', 'kind': 'directory'})
    assert directory.ok and directory.verified and directory.data['matches'][0]['kind'] == 'directory'


@pytest.mark.parametrize('limit', [{'max_results': 1}, {'max_scan_entries': 1}])
def test_limited_search_never_claims_unique_or_complete(tmp_path, limit):
    (tmp_path / 'one.txt').write_text('one')
    (tmp_path / 'two.txt').write_text('two')
    result = files.execute_find_file({'directory': str(tmp_path), 'pattern': '*.txt', **limit})
    assert result.ok and result.verified and result.data['limited'], result
    assert result.data['count'] == 1 and not result.data['unambiguous']


def test_depth_zero_and_no_matches_are_factual(tmp_path):
    child = tmp_path / 'child'
    child.mkdir()
    (child / 'nested.txt').write_text('owned')
    result = files.execute_find_file({'directory': str(tmp_path), 'pattern': '*.txt', 'max_depth': 0})
    assert result.ok and result.verified and not result.data['matches']
    assert not result.data['limited'] and not result.data['unambiguous']
    result = files.execute_find_file({'directory': str(tmp_path), 'pattern': '*.txt', 'max_depth': 1})
    assert result.ok and result.verified and result.data['unambiguous']


@pytest.mark.parametrize('extra', [dict(directory='.'), dict(directory=r'C:\owned\..\other'),
    dict(pattern=r'..\*.txt'), dict(pattern='file:stream'), dict(max_results=True), dict(max_scan_entries=4097),
    dict(created_after_ns=5, created_before_ns=4), dict(modified_after_ns='yesterday'), dict(shell='anything')])
def test_invalid_search_schema_precedes_policy_and_worker(runtime, tmp_path, extra):
    runtime.tool_registry._policy_engine = SimpleNamespace(evaluate=lambda **kwargs: pytest.fail('Invalid search reached policy'))
    args = {'directory': str(tmp_path), 'pattern': '*.txt', **extra}
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('find_file', args)
    assert not runtime.tool_registry._worker_controllers


def test_search_denial_precedes_enumeration(runtime, monkeypatch, tmp_path):
    runtime.policy_engine.rules = PolicyRules(overrides={'find_file': 'DENY'})
    monkeypatch.setattr(runtime.tool_registry.lookup('find_file'), 'executor', lambda *args: pytest.fail('Denied enumeration'))
    cap = task(runtime)
    result = runtime.tool_registry.execute('find_file', {'directory': str(tmp_path), 'pattern': '*'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not cap.undo_stack


@pytest.mark.parametrize('change', ['candidate', 'root', 'new_match', 'proof', 'data'])
def test_independent_search_readback_refuses_replacement_and_forged_evidence(tmp_path, change):
    root = tmp_path / 'root'
    root.mkdir()
    candidate = root / 'one.txt'
    candidate.write_text('owned')
    result = files.execute_find_file({'directory': str(root), 'pattern': '*.txt'})
    assert result.ok and result.verified
    if change == 'candidate':
        candidate.rename(tmp_path / 'retained-original')
        candidate.write_text('replacement')
    if change == 'root':
        root.rename(tmp_path / 'retained-root')
        root.mkdir()
        (root / 'one.txt').write_text('owned')
    if change == 'new_match': (root / 'two.txt').write_text('newer')
    if change == 'proof': result = result.model_copy(update={'private_context': {}})
    if change == 'data': result = result.model_copy(update={'data': dict(result.data, unambiguous=False)})
    assert not files.verify_find_file(result).ok


def test_cancelled_native_search_does_not_open_root(monkeypatch, tmp_path):
    from pluma.core.cancellation import TaskCancelledError
    token = CancellationToken()
    token.cancel(StopReason.USER_STOP)
    monkeypatch.setattr(file_search.identity, '_open', lambda *args, **kwargs: pytest.fail('Cancelled root opened'))
    with pytest.raises(TaskCancelledError):
        file_search.search(files.FindFileArgs(directory=str(tmp_path), pattern='*').model_dump(), token)


def test_missing_root_is_not_a_verified_empty_search(tmp_path):
    result = files.execute_find_file({'directory': str(tmp_path / 'missing'), 'pattern': '*'})
    assert not result.ok and not result.verified and not result.data


def test_search_schema_visible_only_on_file_capable_routes(runtime):
    selector = ToolSubsetSelector(runtime.tool_registry)
    assert 'find_file' in {item['name'] for item in selector.select_schemas(RouteMode.SMART, command='find a file')}
    assert 'find_file' not in {item['name'] for item in selector.select_schemas(RouteMode.SCREEN)}


@pytest.mark.parametrize('nested', [False, True])
def test_real_junction_search_is_refused_without_following_it(tmp_path, nested):
    import subprocess
    target, link = tmp_path / 'target', tmp_path / 'junction'
    target.mkdir()
    (target / 'private.txt').write_text('owned unchanged')
    process = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(target)],
        capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0 and link.is_junction()
    root = link if nested else tmp_path
    result = files.execute_find_file({'directory': str(root), 'pattern': '*.txt'})
    assert not result.ok and not result.verified and not result.data
    assert (target / 'private.txt').read_text() == 'owned unchanged' and link.is_junction()


@pytest.mark.parametrize('stop', [True, False])
def test_blocked_search_worker_is_owned_and_bounded(runtime, monkeypatch, tmp_path, stop):
    approved(runtime, monkeypatch)
    spec = runtime.tool_registry.lookup('find_file')
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, 'timeout_s', 2 if stop else 1)
    cap = task(runtime)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    status, _ = controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'find_file', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)
    assert status == 'ok'
    proc = controller._proc
    identity = dict(controller.worker_identity)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'find_file', {
            'directory': str(tmp_path), 'pattern': '*'}, cap, runtime.ledger)
        try:
            await_file(tmp_path / 'entered', running)
            if stop:
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = running.result(3)
        finally:
            if not running.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
    assert not result.ok and result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert proc._closed and controller._proc is None
    assert subprocess_absent(identity['pid'], identity['creation_time']) is True
    assert controller.verify_cleanup() is True
    assert not cap.undo_stack and not (tmp_path / 'late').exists()
