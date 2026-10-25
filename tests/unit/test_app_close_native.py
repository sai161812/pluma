"""Application close through native exact process control, owned fixtures only."""
import json
from types import SimpleNamespace

import pytest

from pluma.adapters import app_targets
from pluma.brain.schemas import Plan, ToolCall, RouteMode
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_memory_tools import approved
from tests.unit.test_process_control_native import owned_target
from tests.unit.test_runtime_shutdown import runtime, task


@pytest.mark.parametrize('mode', ['close', 'refuse', 'headless'])
def test_native_application_close_is_factual_and_never_force_falls_back(runtime, monkeypatch, tmp_path, mode):
    import _winapi
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target', mode) as (target, handle, fixture):
        with owned_target(runtime, tmp_path / 'unrelated', 'headless') as (other, unrelated, ignored):
            cap = task(runtime)
            result = runtime.tool_registry.execute('close_app', target, cap, runtime.ledger)
            assert result.ok == result.verified == (mode == 'close'), result
            assert (_winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0) == (mode == 'close')
            assert _winapi.WaitForSingleObject(unrelated, 0) == _winapi.WAIT_TIMEOUT
            assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
            intent = cap.undo_stack[-1]
            assert intent.get('non_undoable') is True
            assert result.private_context == {}
            runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED if result.ok else TaskState.FAILED)


def test_denied_application_close_cannot_capture_or_dispatch(runtime, monkeypatch, tmp_path):
    import _winapi
    approved(runtime, monkeypatch)
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(lambda request: ConfirmationResponse(approved=False))
    with owned_target(runtime, tmp_path / 'target') as (target, handle, fixture):
        cap = task(runtime)
        result = runtime.tool_registry.execute('close_app', target, cap, runtime.ledger)
        assert not result.ok and _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        assert not cap.undo_stack and cap.task_id not in runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('args', [{'pid': 1}, {}, {'app_name': 'notepad', 'pid': 1, 'creation_time': 1},
    {'app_name': 'notepad', 'force': True}, {'app_name': 'title substring with spaces'}, {'pid': True, 'creation_time': 1}])
def test_close_schema_precedes_policy(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('close_app', args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers


def test_application_names_are_exact_unique_and_complete(monkeypatch):
    rows = [{'available': True, 'name': 'notepad.exe', 'pid': 10, 'creation_time': 1, 'hwnd': 20},
            {'available': True, 'name': 'notepad.exe', 'pid': 11, 'creation_time': 2, 'hwnd': 21}]
    monkeypatch.setattr(app_targets, 'enumerate_windows', lambda args: {'windows': rows, 'limited': False})
    with pytest.raises(ValueError): app_targets.by_name('notepad')
    rows.pop()
    assert app_targets.by_name('NOTEPAD.exe') == {'pid': 10, 'creation_time': 1}
    with pytest.raises(ValueError): app_targets.by_name('note')
    rows.append({'available': False})
    with pytest.raises(ValueError): app_targets.by_name('notepad')


@pytest.mark.parametrize('mode', ['text', 'voice'])
def test_close_app_shares_text_voice_and_durable_pipeline(runtime, monkeypatch, tmp_path, mode):
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'target') as (target, handle, fixture):
        plan = Plan(route=RouteMode.FAST, steps=[ToolCall(tool='close_app', arguments=target, purpose='Owned native app fixture')])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.FAST, reason='Owned fixture', plan=plan))
        result = runtime.orchestrator.execute(PlumaRequest(input_mode=mode, text='Close owned fixture'))
        assert result.success and result.steps[0].result.verified, result
        assert ActivityQuery(runtime.db).task_by_id(result.task_id)['input_mode'] == mode
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(result.task_id)
