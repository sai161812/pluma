"""Native window placement on an owned window on a never-visible desktop."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import window_state as native
from pluma.core.task_supervisor import TaskState
from pluma.core.cancellation import CancellationToken
from pluma.memory.activity import ActivityQuery
from pluma.rollback import owned
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools import windows, system
from pluma.tools.registry import ToolArgumentError
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.brain.schemas import Plan, ToolCall, RouteMode
from tests.unit.test_memory_tools import approved
from tests.unit.test_process_control_native import owned_target
from tests.unit.test_runtime_shutdown import runtime, task


@contextmanager
def desktop(name):
    import ctypes as c
    from ctypes import wintypes as w
    user, kernel = c.WinDLL('user32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentThreadId.restype = w.DWORD
    user.GetThreadDesktop.argtypes, user.GetThreadDesktop.restype = [w.DWORD], w.HANDLE
    user.OpenDesktopW.argtypes, user.OpenDesktopW.restype = [w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD], w.HANDLE
    user.SetThreadDesktop.argtypes, user.SetThreadDesktop.restype = [w.HANDLE], w.BOOL
    user.CloseDesktop.argtypes, user.CloseDesktop.restype = [w.HANDLE], w.BOOL
    previous = user.GetThreadDesktop(kernel.GetCurrentThreadId())
    handle = user.OpenDesktopW(name, 0, False, 0x01ff)
    if not handle:
        raise c.WinError()
    try:
        if not user.SetThreadDesktop(handle):
            raise c.WinError()
        yield
    finally:
        restored = user.SetThreadDesktop(previous)
        closed = user.CloseDesktop(handle)
        assert restored and closed


ORIGINAL_INVERSE = owned.execute_inverse


@dataclass
class InDesktop:
    name: str
    operation: str
    tool: str = ''

    def __call__(self, value, context=None):
        with desktop(self.name):
            if self.operation == 'capture': return windows.capture_state(value, context, tool=self.tool)
            if self.operation == 'execute': return windows.execute_state(value, context, tool=self.tool)
            if self.operation == 'verify': return windows.verify_state(value)
            if self.operation == 'undo': return system.execute_undo_last(value, context)
            if self.operation == 'verify_undo': return system.verify_undo_last(value)
            if self.operation == 'inverse': return ORIGINAL_INVERSE(value, context)
            raise AssertionError('Unknown test fixture operation.')


def bind(runtime, monkeypatch, name):
    approved(runtime, monkeypatch)
    for tool in native.TOOLS:
        spec = runtime.tool_registry.lookup(tool)
        monkeypatch.setattr(spec, 'undo_builder', InDesktop(name, 'capture', tool))
        monkeypatch.setattr(spec, 'executor', InDesktop(name, 'execute', tool))
        monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'verify'))
    spec = runtime.tool_registry.lookup('undo_last')
    monkeypatch.setattr(spec, 'executor', InDesktop(name, 'undo'))
    monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'verify_undo'))
    monkeypatch.setattr(owned, 'execute_inverse', InDesktop(name, 'inverse'))


@pytest.mark.parametrize('tool', list(native.TOOLS))
@pytest.mark.parametrize('inverse', ['manual', 'automatic'])
def test_native_state_readback_and_safe_inverse(runtime, monkeypatch, tmp_path, tool, inverse):
    with owned_target(runtime, tmp_path / 'target', 'state') as (target, handle, fixture):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        target = dict(target, hwnd=marker['hwnd'])
        bind(runtime, monkeypatch, marker['desktop'])
        with desktop(marker['desktop']):
            # Restore must demonstrate an actual transition, rather than a no-op.
            if tool == 'restore_window': native.apply(native.capture(target, 'maximize_window'))
            before = native.observe(target)
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, target, cap, runtime.ledger)
        assert result.ok and result.verified, result
        state = cap.undo_stack[-1]
        assert state['before'] == before and state['after']['placement']['show'] == native.TOOLS[tool]
        assert result.private_context == {} and state['action'] == 'window_state'
        with desktop(marker['desktop']): assert native.verify(state)
        record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
        assert json.loads(record['undo_json']) == state
        if inverse == 'manual':
            runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
            undo = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
            assert undo.ok and undo.verified, undo
        else:
            runtime.supervisor.request_stop(cap.task_id)
            assert cap.terminal_ready.wait(5), 'Owned STOP cleanup did not finish.'
            assert cap.state == TaskState.STOPPED, cap.stop_error
            assert not cap.inverse_workers
        with desktop(marker['desktop']): assert native.observe(target) == before
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('tool', list(native.TOOLS))
def test_newer_placement_conflict_is_preserved(runtime, monkeypatch, tmp_path, tool):
    with owned_target(runtime, tmp_path / 'target', 'state') as (target, handle, fixture):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        target = dict(target, hwnd=marker['hwnd'])
        bind(runtime, monkeypatch, marker['desktop'])
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, target, cap, runtime.ledger)
        assert result.ok, result
        with desktop(marker['desktop']):
            other = 'maximize_window' if tool != 'maximize_window' else 'minimize_window'
            native.apply(native.capture(target, other))
            newer = native.observe(target)
            assert not RollbackRecipes().apply('window_state', cap.undo_stack[-1]).ok
            assert native.observe(target) == newer
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


@pytest.mark.parametrize('args', [{'title': 'ambiguous'}, {'hwnd': 1}, {'hwnd': True, 'pid': 1, 'creation_time': 1},
    {'hwnd': 1, 'pid': '1', 'creation_time': 1}, {'hwnd': 0, 'pid': 1, 'creation_time': 1}])
def test_window_schema_refuses_before_policy_or_worker(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('minimize_window', args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


def test_stale_identity_and_stop_never_change_window(runtime, monkeypatch, tmp_path):
    with owned_target(runtime, tmp_path / 'target', 'state') as (target, handle, fixture):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        target = dict(target, hwnd=marker['hwnd'])
        bind(runtime, monkeypatch, marker['desktop'])
        with desktop(marker['desktop']): before = native.observe(target)
        cap = task(runtime)
        result = runtime.tool_registry.execute('minimize_window', dict(target, creation_time=target['creation_time']+1), cap, runtime.ledger)
        assert not result.ok and not cap.undo_stack
        with desktop(marker['desktop']):
            assert native.observe(target) == before
            token = CancellationToken(); token.cancel()
            with pytest.raises(Exception): native.apply(native.capture(target, 'minimize_window'), token)
            assert native.observe(target) == before


@pytest.mark.parametrize('mode', ['text', 'voice'])
def test_text_voice_window_state_pipeline(runtime, monkeypatch, tmp_path, mode):
    with owned_target(runtime, tmp_path / 'target', 'state') as (target, handle, fixture):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        target = dict(target, hwnd=marker['hwnd'])
        bind(runtime, monkeypatch, marker['desktop'])
        route = RouteResult(route=RouteMode.FAST, reason='Owned window fixture',
            plan=Plan(route=RouteMode.FAST, steps=[ToolCall(tool='maximize_window', arguments=target, purpose='Owned window fixture')]))
        runtime.orchestrator._router = SimpleNamespace(route=lambda request: route)
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=mode, text='maximize this fixture window',
            original_transcript='maximize this fixture window' if mode == 'voice' else None))
        assert result.final_state == 'SUCCEEDED', result
        assert result.steps[0].result.verified
        assert ActivityQuery(runtime.db).task_by_id(result.task_id)['input_mode'] == mode
        with desktop(marker['desktop']): assert native.observe(target)['placement']['show'] == 3


def test_active_window_change_is_refused_and_newer_placement_preserved(runtime, tmp_path):
    with owned_target(runtime, tmp_path / 'target', 'state') as (target, handle, fixture):
        marker = json.loads((tmp_path / 'target/ready.json').read_text())
        target = dict(target, hwnd=marker['hwnd'])
        with desktop(marker['desktop']):
            state = native.capture(target, 'minimize_window')
            # A different/absent real foreground must not redirect this snapshot.
            import win32gui
            assert win32gui.GetForegroundWindow() != target['hwnd']
            with pytest.raises(ValueError, match='Active window changed'):
                native.apply(dict(state, active_target=True))
            assert native.observe(target) == state['before']


def test_window_change_without_journal_refuses_before_capture(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    monkeypatch.setattr(runtime.tool_registry.lookup('maximize_window'), 'undo_builder',
        lambda *args: pytest.fail('Capture should not run without durable intent.'))
    result = runtime.tool_registry.execute('maximize_window', {}, task(runtime), None)
    assert not result.ok and result.error_code == 'WINDOW_JOURNAL_REQUIRED'
