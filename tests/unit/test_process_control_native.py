"""Explicit process exit and irreversible intents, using only owned fixtures."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from pluma.core.cancellation import StopReason
from pluma.core.job_object import owned_process_creation_time
from pluma.core.task_supervisor import TaskState, ResourceOwnership
from pluma.memory.activity import ActivityQuery
from pluma.tools import processes
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task, NATIVE_JOB


@contextmanager
def owned_target(runtime, root, mode='close'):
    import _winapi
    from types import SimpleNamespace
    root.mkdir()
    marker = root / 'ready.json'
    cap = task(runtime, 'owned-process-target')
    job = NATIVE_JOB()
    handle = thread = None
    try:
        # The Windows venv redirector starts a second python.exe. Launch the
        # stdlib-only fixture with base Python so the retained handle identifies
        # the process that actually owns its window, and assert that relationship.
        executable = str(Path(sys.base_prefix) / 'python.exe')
        command = subprocess.list2cmdline([executable, '-m', 'tests.fixtures.process_control_target', str(marker), mode])
        handle, thread, pid, tid = _winapi.CreateProcess(executable, command, None, None, False,
            subprocess.CREATE_NO_WINDOW | 4, None, str(Path.cwd()), subprocess.STARTUPINFO())
        creation = owned_process_creation_time(SimpleNamespace(sentinel=handle))
        assert creation > 0
        metadata = {'task_id': cap.task_id, 'pid': pid, 'creation_time': creation,
                    'command_class': 'p11_owned_process_exit_fixture'}
        resource = cap.register_owned_resource('subprocess', ResourceOwnership.PLUMA_CREATED, str(pid), metadata)
        job.assign_process(pid)
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.ResumeThread.argtypes, kernel.ResumeThread.restype = [w.HANDLE], w.DWORD
        assert kernel.ResumeThread(thread) != 0xFFFFFFFF
        _winapi.CloseHandle(thread)
        thread = None
        deadline = time.monotonic() + 6
        ready = None
        while time.monotonic() < deadline:
            assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
            try:
                ready = json.loads(marker.read_text(encoding='utf-8'))
                break
            except (FileNotFoundError, PermissionError):
                pass  # atomic publication/native sharing can still be in flight
            time.sleep(.01)
        assert ready is not None, 'Owned hidden fixture did not become ready.'
        assert ready['pid'] == pid
        yield {'pid': pid, 'creation_time': creation}, handle, cap
    finally:
        job.terminate()
        if handle is not None:
            assert _winapi.WaitForSingleObject(handle, 1000) == _winapi.WAIT_OBJECT_0
            _winapi.CloseHandle(handle)
        if thread is not None:
            _winapi.CloseHandle(thread)
        assert job.active_process_count() == 0
        job.close()
        if 'resource' in locals():
            from datetime import datetime, timezone
            resource.released_at = datetime.now(timezone.utc)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


@pytest.mark.parametrize('tool', ['graceful_close_process', 'terminate_process'])
def test_exact_native_process_exit_is_journaled_and_never_offered_as_undo(runtime, monkeypatch, tmp_path, tool):
    import _winapi
    decisions = approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target', 'close' if tool == 'graceful_close_process' else 'headless') as (target, handle, fixture):
        with owned_target(runtime, tmp_path / 'unrelated', 'headless') as (unrelated, other_handle, other_fixture):
            args = dict(target, **({'allow_unsaved_data_loss': True} if tool == 'terminate_process' else {}))
            cap = task(runtime, 'explicit-native-exit')
            result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
            assert result.ok and result.verified, result
            assert result.data['effect_state'] == 'committed' and result.data['non_undoable'] is True
            assert result.undo_record is None and result.private_context == {}
            assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0
            assert _winapi.WaitForSingleObject(other_handle, 0) == _winapi.WAIT_TIMEOUT
            assert len(decisions) == 1 and decisions[0].arguments == args
            assert 'cannot be undone' in decisions[0].prompt_message.lower()
            assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id) == []
            rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
            assert len(rows) == 1 and rows[0]['verified']
            journal = runtime.db.execute_read_one('SELECT ur.available,ur.undo_json FROM undo_records ur JOIN actions a ON a.id=ur.action_id WHERE a.task_id=?', (cap.task_id,))
            evidence = json.loads(journal['undo_json'])
            assert journal['available'] == 0 and evidence['non_undoable'] is True
            assert evidence['effect_state'] == 'committed' and evidence == cap.undo_stack[-1]
            runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


@pytest.mark.parametrize('tool', ['graceful_close_process', 'terminate_process'])
def test_denied_process_control_never_opens_worker_or_touches_target(runtime, monkeypatch, tmp_path, tool):
    import _winapi
    approved(runtime, monkeypatch)
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(lambda request: ConfirmationResponse(approved=False))
    with owned_target(runtime, tmp_path / 'target') as (target, handle, fixture):
        cap = task(runtime)
        args = dict(target, **({'allow_unsaved_data_loss': True} if tool == 'terminate_process' else {}))
        result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
        assert not result.ok and result.error_code == 'POLICY_DENIED'
        assert cap.worker_controller is None and cap.undo_stack == []
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


@pytest.mark.parametrize('tool', ['graceful_close_process', 'terminate_process'])
def test_creation_mismatch_refuses_before_durable_dispatch_intent(runtime, monkeypatch, tmp_path, tool):
    import _winapi
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, handle, fixture):
        cap = task(runtime)
        args = dict(target, creation_time=target['creation_time'] + 1)
        if tool == 'terminate_process':
            args['allow_unsaved_data_loss'] = True
        result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
        assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
        assert cap.undo_stack == [] and _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


@pytest.mark.parametrize('args', [
    {}, {'pid': 1, 'creation_time': 1}, {'pid': 1, 'creation_time': 1, 'allow_unsaved_data_loss': False},
    {'pid': 1, 'creation_time': 1, 'allow_unsaved_data_loss': 1},
    {'pid': True, 'creation_time': 1, 'allow_unsaved_data_loss': True},
    {'pid': 1, 'creation_time': '1', 'allow_unsaved_data_loss': True},
    {'pid': 1, 'creation_time': 1, 'allow_unsaved_data_loss': True, 'command': 'ignored'},
])
def test_force_schema_before_policy(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('terminate_process', args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


def test_resident_process_is_refused_without_effect(runtime, monkeypatch):
    from pluma.core.ownership import get_process_creation_time
    approved(runtime, monkeypatch)
    cap = task(runtime)
    result = runtime.tool_registry.execute('terminate_process', {'pid': os.getpid(),
        'creation_time': get_process_creation_time(os.getpid()), 'allow_unsaved_data_loss': True}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED' and cap.undo_stack == []


def test_graceful_refusal_has_no_force_fallback_and_retains_non_undoable_uncertainty(runtime, monkeypatch, tmp_path):
    import _winapi
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target', 'refuse') as (target, handle, fixture):
        cap = task(runtime)
        result = runtime.tool_registry.execute('graceful_close_process', target, cap, runtime.ledger)
        assert not result.ok and not result.verified and result.error_code == 'PROCESS_EXIT_UNVERIFIED'
        assert result.data == {'non_undoable': True, 'effect_state': 'unknown'}
        assert cap.undo_stack[-1]['non_undoable'] and cap.undo_stack[-1]['effect_state'] == 'unknown'
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
        assert any(item.kind == 'irreversible' and not item.verified for item in cap.cleanup_evidence)
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


def test_intent_is_durable_before_close_and_stop_preserves_unrelated_target(runtime, monkeypatch, tmp_path):
    import _winapi
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target', 'refuse') as (target, handle, fixture):
        cap = task(runtime)
        with ThreadPoolExecutor(1) as pool:
            running = pool.submit(runtime.tool_registry.execute, 'graceful_close_process', target, cap, runtime.ledger)
            deadline = time.monotonic() + 6
            journal = None
            while time.monotonic() < deadline:
                journal = runtime.db.execute_read_one('SELECT ur.available,ur.undo_json FROM undo_records ur JOIN actions a ON a.id=ur.action_id WHERE a.task_id=?', (cap.task_id,))
                if journal:
                    break
                if running.done():
                    pytest.fail(str(running.result()))
                time.sleep(.01)
            assert journal and journal['available'] == 0 and json.loads(journal['undo_json'])['non_undoable']
            # Journal visibility alone does not prove dispatch: STOP before
            # admission correctly removes an unexecuted intent. This case tests
            # STOP after the real owned window received its close request.
            close_requested = tmp_path / 'target' / 'ready.close-requested'
            deadline = time.monotonic() + 3
            while not close_requested.exists() and time.monotonic() < deadline:
                if running.done():
                    pytest.fail(str(running.result()))
                time.sleep(.01)
            assert close_requested.exists(), 'Owned window did not acknowledge WM_CLOSE.'
            cap.cancellation_token.cancel(StopReason.USER_STOP)
            result = running.result(3)
        assert not result.ok and cap.undo_stack[-1]['non_undoable']
        runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


def test_exit_verifier_refuses_unproven_success():
    from pluma.tools.base import ToolResult
    result = ToolResult.success('terminate_process', data={'pid': 1, 'creation_time': 1,
        'state': 'exited', 'exit_code': 1, 'windows_signaled': 0, 'non_undoable': True})
    assert not processes.verify_process_control(result).ok


def test_native_graceful_adapter_reports_original_handle_exit(runtime, monkeypatch, tmp_path):
    import _winapi
    from types import SimpleNamespace
    from pluma.adapters.process_control import capture_intent, execute_control
    from pluma.core.cancellation import CancellationToken
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, handle, fixture):
        user = c.WinDLL('user32', use_last_error=True)
        user.IsWindow.argtypes, user.IsWindow.restype = [w.HWND], w.BOOL
        user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        user.GetWindowThreadProcessId.restype = w.DWORD
        hwnd = json.loads((tmp_path / 'target' / 'ready.json').read_text(encoding='utf-8'))['hwnd']
        assert user.IsWindow(hwnd), 'Owned fixture HWND is not present on the caller desktop.'
        observed = w.DWORD()
        assert user.GetWindowThreadProcessId(hwnd, c.byref(observed)) and observed.value == target['pid']
        intent = capture_intent(target, tool='graceful_close_process')
        context = SimpleNamespace(cancellation_token=CancellationToken(), undo_stack=[{
            'action': 'pending_mutation', 'tool': 'graceful_close_process', 'pre_state': intent}])
        data, proof = execute_control('graceful_close_process', target, context)
        assert data['state'] == 'exited' and data['windows_signaled'] > 0
        assert proof['original_handle_signaled'] and _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0


@pytest.mark.parametrize('missing_ledger', [False, True])
def test_irreversible_journal_failure_never_dispatches(runtime, monkeypatch, tmp_path, missing_ledger):
    import _winapi
    approved(runtime, monkeypatch)
    if not missing_ledger:
        def fail(*args, **kwargs):
            raise OSError('Injected intent persistence failure')
        monkeypatch.setattr(runtime.ledger, 'prepare_mutation', fail)
    with owned_target(runtime, tmp_path / 'target', 'headless') as (target, handle, fixture):
        cap = task(runtime)
        result = runtime.tool_registry.execute('terminate_process', dict(target, allow_unsaved_data_loss=True),
            cap, None if missing_ledger else runtime.ledger)
        assert not result.ok and not result.verified
        assert result.error_code == ('COMMIT_JOURNAL_REQUIRED' if missing_ledger else 'MUTATION_JOURNAL_FAILED')
        assert cap.undo_stack == [] and _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


def test_supervisor_identity_is_internal_and_never_an_argument(runtime, monkeypatch, tmp_path):
    import _winapi
    from types import SimpleNamespace
    from pluma.adapters.process_control import capture_intent
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target', 'headless') as (target, handle, fixture):
        with pytest.raises(ValueError, match='supervision processes'):
            capture_intent(target, SimpleNamespace(supervisor_pid=target['pid']), tool='terminate_process')
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        with pytest.raises(ToolArgumentError):
            runtime.tool_registry.execute('terminate_process', dict(target, allow_unsaved_data_loss=True,
                supervisor_pid=0), task(runtime), runtime.ledger)
