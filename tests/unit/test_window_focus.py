"""Explicitly inert foreground fixtures; never native foreground acceptance."""
from contextlib import nullcontext
from copy import deepcopy

import pytest

from pluma.adapters import window_focus as native
from pluma.core.cancellation import CancellationToken
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools import window_focus as tools
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@pytest.fixture
def desk(monkeypatch):
    import win32gui
    from pluma.adapters import app_windows
    state = {'foreground': 1, 'windows': {
        1: {'identity': {'thread_id': 11}, 'placement': {'show': 1}, 'rectangle': [0, 0, 100, 100]},
        2: {'identity': {'thread_id': 22}, 'placement': {'show': 1}, 'rectangle': [200, 0, 300, 100]}}}
    monkeypatch.setattr(native, 'foreground', lambda: state['foreground'])
    monkeypatch.setattr(native, '_process', lambda *args: nullcontext())
    monkeypatch.setattr(native.placement, 'observe', lambda target: deepcopy(state['windows'][target['hwnd']]))
    monkeypatch.setattr(app_windows, 'observe_window', lambda hwnd: {'hwnd': hwnd, 'pid': hwnd+10, 'creation_time': hwnd+100})
    monkeypatch.setattr(win32gui, 'SetForegroundWindow', lambda hwnd: state.update(foreground=hwnd))
    return state


@pytest.mark.parametrize('tool', ['focus_window', 'focus_app'])
def test_inert_exact_focus_and_verified_inverse(desk, tool):
    args = {'hwnd': 2, 'pid': 12, 'creation_time': 102}
    state = native.capture(args, tool)
    receipt = native.apply(state)
    assert native.verify(receipt) and desk['foreground'] == 2
    assert all(receipt[key] == value for key, value in state.items())
    native.restore(receipt)
    assert native.verify(receipt, restored=True) and desk['foreground'] == 1


@pytest.mark.parametrize('changed', ['foreground', 'target_placement', 'previous_placement'])
def test_inert_focus_inverse_preserves_newer_owner_changes(desk, changed):
    receipt = native.apply(native.capture({'hwnd': 2, 'pid': 12, 'creation_time': 102}, 'focus_window'))
    if changed == 'foreground': desk['foreground'] = 3
    else: desk['windows'][2 if changed == 'target_placement' else 1]['rectangle'][0] += 1
    before = deepcopy(desk)
    assert not RollbackRecipes().apply('window_focus', receipt).ok
    assert desk == before


def test_windows_refusal_never_becomes_focus_success(desk, monkeypatch):
    import win32gui
    state = native.capture({'hwnd': 2, 'pid': 12, 'creation_time': 102}, 'focus_window')
    def denied(hwnd): raise PermissionError('Explicit inert Windows foreground denial')
    monkeypatch.setattr(win32gui, 'SetForegroundWindow', denied)
    with pytest.raises(PermissionError): native.apply(state)
    assert desk['foreground'] == 1 and desk['windows'][2] == state['before']


def test_changed_foreground_and_cancel_refuse_before_native_commit(desk):
    state = native.capture({'hwnd': 2, 'pid': 12, 'creation_time': 102}, 'focus_window')
    desk['foreground'] = 3
    with pytest.raises(ValueError): native.apply(state)
    desk['foreground'] = 1
    token = CancellationToken(); token.cancel()
    with pytest.raises(Exception): native.apply(state, token)
    assert desk['foreground'] == 1


@pytest.mark.parametrize('tool,args', [('focus_window', {}), ('focus_window', {'title': 'ambiguous'}),
    ('focus_window', {'hwnd': 1, 'pid': True, 'creation_time': 1}),
    ('focus_app', {}), ('focus_app', {'app_name': 'notepad', 'hwnd': 1}),
    ('focus_app', {'app_name': 'ambiguous window caption'})])
def test_focus_schema_precedes_policy_and_worker(runtime, monkeypatch, tool, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute(tool, args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('tool', ['focus_app', 'focus_window'])
def test_focus_requires_owned_journal_before_capture(runtime, monkeypatch, tool):
    approved(runtime, monkeypatch)
    result = runtime.tool_registry.execute(tool, {'hwnd': 1, 'pid': 1, 'creation_time': 1}, task(runtime), None)
    assert not result.ok and result.error_code == 'WINDOW_JOURNAL_REQUIRED'
    assert not runtime.tool_registry._worker_controllers
