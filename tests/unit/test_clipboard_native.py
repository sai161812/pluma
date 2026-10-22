"""Native READs on an isolated window-station clipboard, never user contents."""
from dataclasses import dataclass
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pluma.adapters import clipboard_native as native
from pluma.brain.prompt_builder import PromptBuilder
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.memory.activity import ActivityQuery
from pluma.policy.rules import PolicyRules
from pluma.tools import clipboard_reads as tools
from pluma.tools.registry import ToolArgumentError
from tests.fixtures.clipboard_station import station, seed
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Native isolated Windows clipboard fixture')
PRIVATE = 'Private copied note: appointment at ten. \u03bb\U0001f980'



@dataclass
class StationExecute:
    name: str
    tool: str

    def __call__(self, args, context):
        with station(self.name):
            return tools.execute_get(args, context, tool=self.tool)


@dataclass
class StationVerify:
    name: str

    def __call__(self, result):
        with station(self.name):
            return tools.verify_get(result)


def fixture_observation():
    return {'data': {'formats': ['unicode_text'], 'unsupported_format_ids': [],
            'is_empty': False, 'clipboard_value': {'unicode_text': PRIVATE}},
            'proof': {'sequence': 7, 'owner': 21, 'digest': 'explicitly-inert-clipboard-fixture'}}


@dataclass
class FixtureExecute:
    tool: str

    def __call__(self, args, context):
        with patch.object(native, 'observe', lambda *args: fixture_observation()):
            result = tools.execute_get(args, context, tool=self.tool)
        return result.model_copy(update={'adapter_used': 'fixture_clipboard',
            'factual_message': 'Explicit inert clipboard read fixture; no native access.'})


def fixture_verify(result):
    with patch.object(native, 'observe', lambda *args: fixture_observation()):
        return tools.verify_get(result.model_copy(update={'adapter_used': 'native_clipboard'}))


def execute_request(runtime, tool, input_mode):
    plan = Plan(route=RouteMode.SMART, steps=[ToolCall(tool=tool, arguments={}, purpose='Private clipboard read fixture')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(route=RouteMode.SMART, reason='Owned fixture', plan=plan))
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=lambda **kwargs: plan)
    result = runtime.orchestrator.execute(PlumaRequest(input_mode=input_mode, text='Inspect clipboard formats fixture'))
    assert result.success and result.final_state == 'SUCCEEDED', result
    cap = runtime.supervisor.get_task(result.task_id)
    observed = result.steps[0].result
    assert observed.ok and observed.verified and observed.private_context == {} and not cap.undo_stack
    assert cap.worker_controller is cap.job_object is None
    assert observed.data['clipboard_value']['unicode_text'] == PRIVATE
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    stored = json.dumps(rows)
    assert len(rows) == 1 and rows[0]['verified'] and '[REDACTED]' in stored
    assert PRIVATE not in stored
    prompt = PromptBuilder().build_user_prompt('Inspect clipboard formats', prior_step_results=[observed.model_dump()])
    assert PRIVATE not in prompt
    assert '[REDACTED]' in prompt


@pytest.mark.parametrize('kind', ['empty', 'text', 'unsupported'])
def test_native_read_formats_are_bounded_and_preserve_interactive_clipboard(kind):
    with station() as (name, owner):
        if kind == 'unsupported':
            import win32clipboard
            format_id = win32clipboard.RegisterClipboardFormat('PLUMA owned unsupported fixture')
            values = [(format_id, b'private unknown fixture\0')]
        else:
            values = [(13, PRIVATE)] if kind == 'text' else []
        seed(owner, values)
        before = native.observe()
        assert native.observe() == before
        data = before['data']
        assert data['is_empty'] is (kind == 'empty')
        if kind == 'text': assert data['clipboard_value']['unicode_text'] == PRIVATE
        if kind == 'unsupported':
            assert data['formats'] == [] and data['unsupported_format_ids'] == [format_id]
        else: assert not data['unsupported_format_ids']


@pytest.mark.parametrize('tool', ['clipboard_get', 'get_clipboard_text'])
@pytest.mark.parametrize('input_mode', ['text', 'voice'])
def test_native_owned_read_pipeline_has_private_caller_data_but_redacted_history_and_prompts(runtime, monkeypatch, tool, input_mode):
    approved(runtime, monkeypatch)
    with station() as (name, owner):
        seed(owner, [(13, PRIVATE)])
        spec = runtime.tool_registry.lookup(tool)
        monkeypatch.setattr(spec, 'executor', StationExecute(name, tool))
        monkeypatch.setattr(spec, 'verifier', StationVerify(name))
        execute_request(runtime, tool, input_mode)


@pytest.mark.parametrize('tool', ['clipboard_get', 'get_clipboard_text'])
@pytest.mark.parametrize('input_mode', ['text', 'voice'])
def test_inert_read_pipeline_protects_payload_in_history_and_prompts(runtime, monkeypatch, tool, input_mode):
    approved(runtime, monkeypatch)
    spec = runtime.tool_registry.lookup(tool)
    monkeypatch.setattr(spec, 'executor', FixtureExecute(tool))
    monkeypatch.setattr(spec, 'verifier', fixture_verify)
    execute_request(runtime, tool, input_mode)


def test_prompt_prior_results_redact_private_clipboard_without_native_access():
    prompt = PromptBuilder().build_user_prompt('Inspect clipboard', prior_step_results=[
        {'tool': 'clipboard_get', 'ok': True, 'data': {'clipboard_value': PRIVATE}}])
    assert PRIVATE not in prompt and '[REDACTED]' in prompt


def test_clipboard_schema_and_denial_prevent_read(runtime, monkeypatch):
    spec = runtime.tool_registry.lookup('clipboard_get')
    monkeypatch.setattr(spec, 'executor', lambda *args: pytest.fail('Invalid/denied clipboard access'))
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('clipboard_get', {'station': 'WinSta0'})
    runtime.policy_engine.rules = PolicyRules(overrides={'clipboard_get': 'DENY'})
    result = runtime.tool_registry.execute('clipboard_get', {}, task(runtime), runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not runtime.tool_registry._worker_controllers


def test_changed_clipboard_sequence_or_payload_cannot_verify(monkeypatch):
    with station() as (name, owner):
        seed(owner, [(13, PRIVATE)])
        result = tools.execute_get({})
        assert result.ok and result.verified
        seed(owner, [(13, PRIVATE + ' newer')])
        assert not tools.verify_get(result).ok


def test_busy_clipboard_and_native_failure_never_report_empty(monkeypatch):
    monkeypatch.setattr(native, 'observe', lambda *args: (_ for _ in ()).throw(OSError('private failing fixture')))
    result = tools.execute_get({})
    assert not result.ok and not result.verified and result.error_code == 'CLIPBOARD_READ_FAILED'
    assert not result.data and 'private failing fixture' not in result.factual_message


@pytest.mark.parametrize('field', ['sequence', 'owner', 'digest', 'data'])
def test_inert_independent_readback_rejects_changed_or_forged_observation(monkeypatch, field):
    from copy import deepcopy
    packet = fixture_observation()
    monkeypatch.setattr(native, 'observe', lambda *args: deepcopy(packet))
    result = tools.execute_get({})
    assert result.ok and result.verified
    if field == 'data': packet['data']['is_empty'] = True
    else: packet['proof'][field] = 'different'
    assert not tools.verify_get(result).ok


@pytest.mark.parametrize('stop', [True, False])
def test_blocked_read_has_owned_stop_and_timeout_without_native_access(runtime, monkeypatch, tmp_path, stop):
    approved(runtime, monkeypatch)
    spec = runtime.tool_registry.lookup('clipboard_get')
    monkeypatch.setattr(spec, 'executor', OwnedProbe(str(tmp_path)))
    monkeypatch.setattr(spec, 'timeout_s', 3 if stop else 1)
    cap = task(runtime)
    with ThreadPoolExecutor(1) as pool:
        running = pool.submit(runtime.tool_registry.execute, 'clipboard_get', {}, cap, runtime.ledger)
        await_file(tmp_path / 'entered', running)
        if stop: runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        result = running.result(5)
    assert not result.ok and not result.verified and result.error_code == ('TASK_CANCELLED' if stop else 'TOOL_TIMEOUT')
    assert not (tmp_path / 'late').exists() and not cap.undo_stack


@pytest.mark.parametrize('raw', [b'\0', b'x\0', b'\0\xd8\0\0', b'x\0' * 65537 + b'\0\0'],
                         ids=['odd', 'unterminated', 'invalid-surrogate', 'oversized'])
def test_malformed_or_oversized_unicode_refuses(raw):
    with pytest.raises((ValueError, UnicodeDecodeError)): native._unicode(raw)
