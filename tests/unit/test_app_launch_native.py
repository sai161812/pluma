"""Native app instances on a never-visible desktop; no product test-mode bypass."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
import uuid
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from pluma.adapters import app_launch as native
from pluma.core.ownership import subprocess_absent
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback import owned
from pluma.tools import app_launch as tools, system
from pluma.tools.registry import ToolArgumentError
from pluma.brain.schemas import Plan, ToolCall, RouteMode
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_window_state_native import desktop


@contextmanager
def private_desktop():
    import ctypes as c
    from ctypes import wintypes as w
    user = c.WinDLL('user32', use_last_error=True)
    user.CreateDesktopW.argtypes, user.CreateDesktopW.restype = [w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p], w.HANDLE
    user.CloseDesktop.argtypes, user.CloseDesktop.restype = [w.HANDLE], w.BOOL
    name = 'PLUMALaunch-' + str(uuid.uuid4())
    handle = user.CreateDesktopW(name, None, None, 0, 0x01ff, None)
    assert handle
    try: yield name
    finally: assert user.CloseDesktop(handle)


ORIGINAL_INVERSE = owned.execute_inverse


@dataclass
class InDesktop:
    name: str
    operation: str
    def __call__(self, value, context=None):
        with desktop(self.name):
            if self.operation == 'execute': return tools.execute(value, context)
            if self.operation == 'verify': return tools.verify(value)
            if self.operation == 'undo':
                from unittest.mock import patch
                original = native.restore
                def diagnose(state):
                    try: return original(state)
                    except Exception as error:
                        Path(context.storage_path).with_suffix('.launch-error.json').write_text(json.dumps({
                            'type': type(error).__name__, 'error': str(error),
                            'before_windows': state.get('windows'),
                            'now_windows': native.windows(state['pid'], state['creation_time']),
                            'owned_classes': [__import__('win32gui').GetClassName(item['hwnd'])
                                for item in native.windows(state['pid'], state['creation_time'])],
                            'absent': subprocess_absent(state['pid'], state['creation_time'])}))
                        raise
                with patch.object(native, 'restore', diagnose): return system.execute_undo_last(value, context)
            if self.operation == 'verify_undo': return system.verify_undo_last(value)
            if self.operation == 'inverse': return ORIGINAL_INVERSE(value, context)
            raise AssertionError('Unknown native fixture operation.')


def bind(runtime, monkeypatch, tmp_path, name):
    approved(runtime, monkeypatch)
    executable = str(Path(sys.base_prefix) / 'python.exe')
    argv = [executable, '-m', 'tests.fixtures.process_control_target', str(tmp_path / 'ready.json'), 'launch']
    # This is a fixture replacement of the closed binding, not an environment
    # switch or planner-visible arbitrary executable/argument capability.
    def binding(args):
        with native.files._open(Path.cwd(), parent=True) as directory:
            identity = native.files._parent_identity(directory)
        return {'argv': argv, 'cwd': str(Path.cwd()), 'image_identity': native.files.snapshot(executable),
                'directory_identity': identity}
    monkeypatch.setattr(native, 'binding', binding)
    def startup():
        import win32process
        result = win32process.STARTUPINFO(); result.lpDesktop = name; return result
    monkeypatch.setattr(native, 'startup_info', startup)
    real_launch = native.launch
    def diagnostic_launch(state, context):
        try: return real_launch(state, context)
        except Exception as error:
            (tmp_path / 'diagnostic.txt').write_text(type(error).__name__ + ': ' + str(error))
            raise
    monkeypatch.setattr(native, 'launch', diagnostic_launch)
    spec = runtime.tool_registry.lookup('open_app')
    monkeypatch.setattr(spec, 'executor', InDesktop(name, 'execute'))
    monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'verify'))
    spec = runtime.tool_registry.lookup('undo_last')
    monkeypatch.setattr(spec, 'executor', InDesktop(name, 'undo'))
    monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'verify_undo'))
    monkeypatch.setattr(owned, 'execute_inverse', InDesktop(name, 'inverse'))


@pytest.mark.parametrize('completion', ['success_then_undo', 'stop'])
def test_native_launch_is_owned_before_resume_and_survives_only_success(runtime, monkeypatch, tmp_path, completion):
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        cap = task(runtime)
        state = None
        try:
            result = runtime.tool_registry.execute('open_app', {'app_name': 'charmap'}, cap, runtime.ledger)
            diagnostic = tmp_path / 'diagnostic.txt'
            assert result.ok and result.verified, (result, diagnostic.read_text() if diagnostic.exists() else '')
            state = cap.undo_stack[-1]
            assert result.private_context == {} and state['action'] == 'app_launch'
            resource = next(item for item in cap.owned_resources if item.metadata.get('persistent_launch_id') == state['launch_id'])
            assert resource.metadata['creation_time'] == state['creation_time']
            assert resource.metadata['persistent_job'].active_process_count() >= 1
            assert resource.metadata['persistent_job']._kill_on_close is True
            assert json.loads(ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]['undo_json']) == state
            if completion == 'success_then_undo':
                runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
                assert cap.state == TaskState.SUCCEEDED and resource.released_at is not None
                assert cap.job_object is None and resource.metadata['persistent_job'] is None
                assert not subprocess_absent(state['pid'], state['creation_time'])
                # The registered verifier already read back the exact image and
                # window before task finalization. The guarded undo below reads
                # the receipt again on its owned desktop-bound worker. Avoid
                # rebinding pytest's COM-used main thread, which may own a
                # message window after preceding tests in the same process.
                undo = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
                error_path = Path(runtime.paths.db_path).with_suffix('.launch-error.json')
                assert undo.ok and undo.verified, (undo, error_path.read_text() if error_path.exists() else '')
            else:
                runtime.supervisor.request_stop(cap.task_id)
                assert cap.terminal_ready.wait(8)
                assert cap.state == TaskState.STOPPED, cap.stop_error
            assert subprocess_absent(state['pid'], state['creation_time'])
            assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        finally:
            if state and not subprocess_absent(state['pid'], state['creation_time']):
                try:
                    with desktop(name): native.restore(state)
                except Exception:
                    # Test cleanup only: this exact PID/creation time was born
                    # in this fixture. Production undo never uses force fallback.
                    import _winapi
                    from pluma.adapters.process_control import _target, _api
                    with _target(state['pid'], state['creation_time'], force=True) as (handle, check):
                        check(); c, w, kernel = _api(); assert kernel.TerminateProcess(handle, 1)
                        assert _winapi.WaitForSingleObject(handle, 1000) == _winapi.WAIT_OBJECT_0


@pytest.mark.parametrize('args', [{'app_name': 'cmd'}, {'app_name': sys.executable},
    {'app_name': 'charmap', 'arguments': ['arbitrary']}, {'app_name': 'notepad', 'working_dir': 'C:\\Windows'},
    {'app_name': True}, {'app_name': 'charmap', 'run_as_admin': True}])
def test_launch_schema_precedes_policy_and_native_creation(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('open_app', args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


def test_native_system_binding_is_closed_and_does_not_launch():
    state = native.binding({'app_name': 'charmap'})
    assert state['argv'] == [str(native.windows_directory() / 'System32/charmap.exe')]
    assert state['image_identity']['kind'] == 'file'
    with pytest.raises(ValueError): native.binding({'app_name': 'unknown'})


def test_launch_without_journal_never_captures(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    monkeypatch.setattr(native, 'binding', lambda args: pytest.fail('No capture without an owned journal.'))
    result = runtime.tool_registry.execute('open_app', {'app_name': 'charmap'}, task(runtime), None)
    assert not result.ok and result.error_code == 'WINDOW_JOURNAL_REQUIRED'


def test_launcher_handoff_or_early_exit_never_claims_clean_rollback(runtime, monkeypatch, tmp_path):
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        original = native.binding
        def exiting(args):
            state = original(args)
            state['argv'] = [*state['argv'][:-1], 'exit']
            return state
        monkeypatch.setattr(native, 'binding', exiting)
        cap = task(runtime)
        result = runtime.tool_registry.execute('open_app', {'app_name': 'charmap'}, cap, runtime.ledger)
        assert not result.ok and any(item.code == 'APP_HANDOFF_OR_EXIT_UNVERIFIED'
            and not item.verified for item in cap.cleanup_evidence)
        runtime.supervisor.request_stop(cap.task_id)
        assert cap.terminal_ready.wait(5)
        assert cap.state == TaskState.STOPPED_WITH_RESIDUAL and cap.cleanup_pending


def test_failed_assignment_never_resumes_and_original_handle_is_drained(runtime, monkeypatch, tmp_path):
    from pluma.core import job_object
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        cap = task(runtime)
        original = job_object.WindowsJobObject
        class RefusedJob(original):
            def assign_process(self, process): raise RuntimeError('Explicit fixture containment refusal')
        monkeypatch.setattr(job_object, 'WindowsJobObject', RefusedJob)
        result = runtime.tool_registry.execute('open_app', {'app_name': 'charmap'}, cap, runtime.ledger)
        monkeypatch.setattr(job_object, 'WindowsJobObject', original)
        assert not result.ok and not (tmp_path / 'ready.json').exists()
        resource = next(item for item in cap.owned_resources if item.metadata.get('persistent_launch_id'))
        assert subprocess_absent(resource.metadata['pid'], resource.metadata['creation_time'])
        assert resource.metadata['persistent_job'] is None
        runtime.supervisor.fail_task_with_rollback(cap.task_id)
        assert cap.state == TaskState.FAILED and not cap.cleanup_pending


def test_unverified_promotion_is_retained_and_shutdown_drains_exact_job(runtime, monkeypatch, tmp_path):
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        cap = task(runtime)
        result = runtime.tool_registry.execute('open_app', {'app_name': 'charmap'}, cap, runtime.ledger)
        assert result.ok, result
        state = cap.undo_stack[-1]
        resource = next(item for item in cap.owned_resources if item.metadata.get('persistent_launch_id'))
        job = resource.metadata['persistent_job']
        def refused(): raise OSError('Explicit fixture promotion readback refusal')
        monkeypatch.setattr(job, 'allow_persistence', refused)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        assert cap.state == TaskState.FAILED and cap.cleanup_pending
        assert resource.metadata['persistent_job'] is job and not job.is_closed
        assert resource.released_at is None
        closed = runtime.close(5)
        assert closed.complete, closed
        assert job.is_closed and subprocess_absent(state['pid'], state['creation_time'])


def test_stop_reports_retained_receipt_owner_and_never_late_success(runtime, monkeypatch, tmp_path):
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        started, release = threading.Event(), threading.Event()
        execute = InDesktop(name, 'execute')
        def held(args, context):
            result = execute(args, context)
            assert result.ok, result
            started.set()
            assert release.wait(4)
            return result
        monkeypatch.setattr(runtime.tool_registry.lookup('open_app'), 'executor', held)
        cap = task(runtime)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.tool_registry.execute, 'open_app', {'app_name': 'charmap'}, cap, runtime.ledger)
            try:
                assert started.wait(4)
                runtime.supervisor.request_stop(cap.task_id, wait_s=0)
                assert cap.cancellation_token.is_cancelled
                assert cap.terminal_ready.wait(3)
                assert cap.state == TaskState.STOPPED_WITH_RESIDUAL and cap.cleanup_pending
                resource = next(item for item in cap.owned_resources if item.metadata.get('persistent_launch_id'))
                # Job termination is asynchronous. Read the same owned process
                # handle with a bounded wait instead of racing its kernel exit.
                assert subprocess_absent(resource.metadata['pid'], resource.metadata['creation_time'], wait_s=0.3)
            finally:
                release.set()
            result = future.result(5)
        assert not result.ok and cap.terminal_ready.wait(8)
        assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
        resource = next(item for item in cap.owned_resources if item.metadata.get('persistent_launch_id'))
        assert subprocess_absent(resource.metadata['pid'], resource.metadata['creation_time'], wait_s=0.3)
        retained = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        assert retained and json.loads(retained[0]['undo_json'])['action'] == 'pending_mutation'


@pytest.mark.parametrize('mode', ['text', 'voice'])
def test_launch_shares_text_voice_request_and_promotes_only_verified_success(runtime, monkeypatch, tmp_path, mode):
    with private_desktop() as name:
        bind(runtime, monkeypatch, tmp_path, name)
        plan = Plan(route=RouteMode.FAST, steps=[ToolCall(tool='open_app', arguments={'app_name': 'charmap'}, purpose='Owned launch fixture')])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.FAST, reason='Owned fixture', plan=plan))
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=mode, text='Open owned application fixture'))
        assert result.success and result.final_state == 'SUCCEEDED', result
        cap = runtime.supervisor.get_task(result.task_id)
        state = cap.undo_stack[-1]
        try:
            assert ActivityQuery(runtime.db).task_by_id(result.task_id)['input_mode'] == mode
            assert not subprocess_absent(state['pid'], state['creation_time'])
            undo = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
            assert undo.ok and undo.verified, undo
        finally:
            if not subprocess_absent(state['pid'], state['creation_time']):
                with desktop(name): native.restore(state)
