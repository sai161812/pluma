"""Plain-text copy/clear/undo on the native fixture clipboard only."""
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace

import pytest

from pluma.adapters.clipboard_native import observe, text_of
from pluma.core.task_supervisor import TaskState
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.memory.activity import ActivityQuery
from pluma.rollback import owned
from pluma.tools import clipboard as tools
from pluma.tools import system
from pluma.tools.registry import ToolArgumentError
from tests.fixtures.clipboard_station import station, seed
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task

BEFORE = 'Previous private copied note. \u03bb\U0001f980'
AFTER = 'Plain text to paste.\nUnicode \u2713'
ORIGINAL_INVERSE = owned.execute_inverse


@dataclass
class Capture:
    name: str
    tool: str
    def __call__(self, args, context):
        with station(self.name): return tools.capture(args, context, tool=self.tool)


@dataclass
class Execute:
    name: str
    tool: str
    database: str
    def __call__(self, args, context):
        with sqlite3.connect(self.database, timeout=1) as db:
            row = db.execute('SELECT ur.undo_json FROM undo_records ur JOIN actions a ON a.id=ur.action_id '
                'WHERE a.task_id=? ORDER BY a.id DESC LIMIT 1', (context.task_id,)).fetchone()
            assert row and BEFORE not in row[0] and AFTER not in row[0]
            pending = json.loads(row[0])
            assert pending['action'] == 'pending_mutation' and pending['pre_state']['volatile'] is True
            assert 'clipboard_private' not in pending['pre_state']
        with station(self.name): return tools.execute_mutation(args, context, tool=self.tool)


@dataclass
class Verify:
    name: str
    def __call__(self, result):
        with station(self.name): return tools.verify_mutation(result)


@dataclass
class Undo:
    name: str
    def __call__(self, args, context):
        with station(self.name): return system.execute_undo_last(args, context)


@dataclass
class VerifyUndo:
    name: str
    def __call__(self, result):
        with station(self.name): return system.verify_undo_last(result)


@dataclass
class Inverse:
    name: str
    def __call__(self, args, context):
        with station(self.name): return ORIGINAL_INVERSE(args, context)


def bind(runtime, monkeypatch, name):
    approved(runtime, monkeypatch)
    for tool in tools.MUTATION_NAMES:
        spec = runtime.tool_registry.lookup(tool)
        monkeypatch.setattr(spec, 'undo_builder', Capture(name, tool))
        monkeypatch.setattr(spec, 'executor', Execute(name, tool, str(runtime.paths.db_path)))
        monkeypatch.setattr(spec, 'verifier', Verify(name))
    spec = runtime.tool_registry.lookup('undo_last')
    monkeypatch.setattr(spec, 'executor', Undo(name))
    monkeypatch.setattr(spec, 'verifier', VerifyUndo(name))
    monkeypatch.setattr(owned, 'execute_inverse', Inverse(name))


def copy(runtime, tool='clipboard_set', text=AFTER, cap=None):
    cap = cap or task(runtime)
    args = {'text': text} if tool in tools.MUTATION_NAMES[:2] else {}
    result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
    assert result.ok and result.verified, result
    return cap, result


@pytest.mark.parametrize('tool', tools.MUTATION_NAMES)
@pytest.mark.parametrize('before', [None, BEFORE], ids=['empty-before', 'text-before'])
def test_native_plain_text_copy_clear_and_manual_undo(runtime, monkeypatch, tool, before):
    with station() as (name, owner):
        seed(owner, [] if before is None else [(13, before)])
        bind(runtime, monkeypatch, name)
        cap, result = copy(runtime, tool)
        expected = AFTER if tool in tools.MUTATION_NAMES[:2] else None
        assert text_of(observe()) == expected and result.private_context == {}
        state = cap.undo_stack[-1]
        assert state['action'] == 'clipboard_restore' and state['volatile'] is True
        assert set(state) == {'action', 'guard_version', 'volatile', 'undo_ref'}
        stored = json.dumps(ActivityQuery(runtime.db).actions_for_task(cap.task_id))
        raw = runtime.db.execute_read_one('SELECT undo_json FROM undo_records ORDER BY action_id DESC LIMIT 1')['undo_json']
        assert BEFORE not in stored + raw and AFTER not in stored + raw
        assert '[REDACTED]' in stored if tool in tools.MUTATION_NAMES[:2] else True
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        undone = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
        assert undone.ok and undone.verified, undone
        assert text_of(observe()) == before
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        assert not runtime.tool_registry._clipboard_undo_cache


def test_native_newer_clipboard_contents_are_preserved(runtime, monkeypatch):
    with station() as (name, owner):
        seed(owner, [(13, BEFORE)])
        bind(runtime, monkeypatch, name)
        cap, result = copy(runtime)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        seed(owner, [(13, 'Newer owner content')])
        current = observe()
        undone = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
        assert not undone.ok and not undone.verified and observe() == current
        assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


def test_expired_ram_undo_refuses_before_claim_and_preserves_clipboard(runtime, monkeypatch):
    with station() as (name, owner):
        seed(owner, [(13, BEFORE)])
        bind(runtime, monkeypatch, name)
        cap, result = copy(runtime)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        runtime.tool_registry._clipboard_undo_cache.clear()
        current = observe()
        undone = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
        assert not undone.ok and observe() == current
        assert runtime.db.execute_read_one('SELECT count(*) AS n FROM undo_claims')['n'] == 0


@pytest.mark.parametrize('automatic', [False, True])
def test_two_plain_text_writes_undo_in_order_with_verified_lineage(runtime, monkeypatch, automatic):
    with station() as (name, owner):
        seed(owner, [(13, BEFORE)])
        bind(runtime, monkeypatch, name)
        cap, result = copy(runtime, text='Middle private text')
        copy(runtime, text=AFTER, cap=cap)
        if automatic:
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        else:
            runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
            for _ in range(2):
                undone = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
                assert undone.ok and undone.verified, undone
        assert text_of(observe()) == BEFORE
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


@pytest.mark.parametrize('tool', tools.MUTATION_NAMES)
def test_unsupported_formats_refuse_before_replacement(runtime, monkeypatch, tool):
    import win32clipboard
    with station() as (name, owner):
        format_id = win32clipboard.RegisterClipboardFormat('PLUMA unsupported replacement fixture')
        seed(owner, [(format_id, b'owned non-text bytes\0')])
        bind(runtime, monkeypatch, name)
        before = observe()
        cap = task(runtime)
        result = runtime.tool_registry.execute(tool, {'text': AFTER} if tool in tools.MUTATION_NAMES[:2] else {}, cap, runtime.ledger)
        assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
        assert observe() == before and not cap.undo_stack


@pytest.mark.parametrize('args', [{'text': 'bad\0text'}, {'text': 123}, {'text': 'x' * 65537}, {'text': 'x', 'format': 'bitmap'}],
                         ids=['nul', 'not-text', 'too-long', 'non-text-format'])
def test_plain_text_schema_rejects_before_native_capture(runtime, monkeypatch, args):
    spec = runtime.tool_registry.lookup('clipboard_set')
    monkeypatch.setattr(spec, 'undo_builder', lambda *args: pytest.fail('Invalid clipboard capture'))
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('clipboard_set', args, task(runtime), runtime.ledger)


def test_clipboard_write_without_owned_journal_refuses_before_capture(runtime, monkeypatch):
    spec = runtime.tool_registry.lookup('clipboard_set')
    monkeypatch.setattr(spec, 'undo_builder', lambda *args: pytest.fail('Unowned clipboard capture'))
    result = runtime.tool_registry.execute('clipboard_set', {'text': AFTER})
    assert not result.ok and result.error_code == 'CLIPBOARD_JOURNAL_REQUIRED'


def test_native_copied_text_pastes_into_owned_edit_control(runtime, monkeypatch):
    import ctypes as c
    from ctypes import wintypes as w
    from tests.fixtures.clipboard_station import _api
    with station() as (name, owner):
        seed(owner, [(13, BEFORE)])
        bind(runtime, monkeypatch, name)
        text = 'Paste works \u2713 \u03bb'
        cap, result = copy(runtime, text=text)
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        user, _ = _api()
        user.SendMessageW.argtypes, user.SendMessageW.restype = [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.LPARAM
        user.GetWindowTextW.argtypes, user.GetWindowTextW.restype = [w.HWND, w.LPWSTR, c.c_int], c.c_int
        edit = user.CreateWindowExW(0, 'EDIT', '', 0x40000000, 0, 0, 200, 30, owner, None, None, None)
        assert edit
        try:
            user.SendMessageW(edit, 0x0302, 0, 0)  # WM_PASTE, exact owned fixture control
            buffer = c.create_unicode_buffer(256)
            assert user.GetWindowTextW(edit, buffer, len(buffer)) == len(text)
            assert buffer.value == text
        finally:
            assert user.DestroyWindow(edit)


@pytest.mark.parametrize('tool', ['clipboard_set', 'clipboard_clear'])
@pytest.mark.parametrize('input_mode', ['text', 'voice'])
def test_native_plain_text_writes_share_text_voice_request_pipeline(runtime, monkeypatch, tool, input_mode):
    with station() as (name, owner):
        seed(owner, [(13, BEFORE)])
        bind(runtime, monkeypatch, name)
        args = {'text': AFTER} if tool == 'clipboard_set' else {}
        plan = Plan(route=RouteMode.FAST, steps=[ToolCall(tool=tool, arguments=args, purpose='Plain-text clipboard fixture')])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.FAST, reason='Owned fixture', plan=plan))
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Plain-text clipboard fixture'))
        assert result.success and result.final_state == 'SUCCEEDED', result
        row = ActivityQuery(runtime.db).task_by_id(result.task_id)
        assert row['input_mode'] == input_mode
        assert text_of(observe()) == (AFTER if tool == 'clipboard_set' else None)
