"""Typed confirmed local system requests with factual non-undoable intents."""
from functools import partial
from typing import Literal
import uuid

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult

SystemAction = Literal['lock', 'sleep_request', 'restart_request', 'shutdown_request']


class EmptyArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}


class ShutdownArgs(EmptyArgs):
    delay_seconds: int = Field(default=30, ge=30, le=300)


class LockState(EmptyArgs):
    session_id: int = Field(ge=0, le=0xffffffff)
    connection_state: int = Field(ge=0, le=9)
    locked: bool


class SleepState(EmptyArgs):
    sleep_100ns: int = Field(ge=0)
    wake_100ns: int = Field(ge=0)


class EventBaseline(EmptyArgs):
    event_baseline: int = Field(ge=0, le=0xffffffff)


class Intent(EmptyArgs):
    action: Literal['non_undoable_system']
    guard_version: Literal[1]
    non_undoable: Literal[True]
    tool: SystemAction
    operation_id: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
    arguments: dict
    before: dict


class ShutdownEvent(EmptyArgs):
    record_id: int = Field(gt=0, le=0xffffffff)
    event_id: Literal[1074]
    operation_id: str
    kind: Literal['restart_request', 'shutdown_request']


def _arguments(tool, args):
    return (ShutdownArgs if tool in ('restart_request', 'shutdown_request') else EmptyArgs).model_validate(args).model_dump()


def _before(tool, value):
    return (LockState if tool == 'lock' else SleepState if tool == 'sleep_request' else EventBaseline).model_validate(value).model_dump()


def _observation(tool, value):
    return (LockState if tool == 'lock' else SleepState if tool == 'sleep_request' else ShutdownEvent).model_validate(value).model_dump()


def capture_intent(args, context=None, *, tool):
    from pluma.adapters.power_actions import capture
    token = getattr(context, 'cancellation_token', None)
    if token is not None:
        token.raise_if_cancelled()
    values = _arguments(tool, args)
    return Intent(action='non_undoable_system', guard_version=1, non_undoable=True, tool=tool,
        operation_id=str(uuid.uuid4()), arguments=values, before=_before(tool, capture(tool))).model_dump()


def execute_power(args, context, *, tool):
    from pluma.adapters.power_actions import run
    from pluma.core.cancellation import TaskCancelledError
    try:
        context.cancellation_token.raise_if_cancelled()
        pending = next(item for item in reversed(context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        state = Intent.model_validate(pending['pre_state']).model_dump()
        if state['tool'] != tool or state['arguments'] != _arguments(tool, args):
            raise ValueError('System request does not match its durable intent.')
        _before(tool, state['before'])
        observed = _observation(tool, run(state, context))
        messages = {'lock': 'Session lock state verified. Unlock requires user authentication.',
            'sleep_request': 'A sleep/wake transition was observed. This cannot be automatically undone.',
            'restart_request': 'Windows restart initiation was observed; completion is not yet established. This cannot be automatically undone.',
            'shutdown_request': 'Windows shutdown initiation was observed; completion is not yet established. This cannot be automatically undone.'}
        result = ToolResult.success(tool, data={'kind': tool, 'operation_id': state['operation_id'], 'observation': observed},
            verified=False, factual_message=messages[tool], adapter_used='native_api').model_copy(
                update={'private_context': {'system_receipt': state}})
        checked = verify_power(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except TaskCancelledError:
        return ToolResult.failure(tool, 'System request was stopped. An accepted OS effect cannot be promised reversed.', 'TASK_CANCELLED')
    except Exception:
        return ToolResult.failure(tool, 'System request refused or effect unverified. Accepted OS effects may remain; no automatic undo is available.',
                                  'SYSTEM_EFFECT_UNVERIFIED')


def verify_power(result):
    from pluma.adapters.power_actions import verify
    try:
        state = Intent.model_validate(result.private_context['system_receipt']).model_dump()
        _before(state['tool'], state['before'])
        _arguments(state['tool'], state['arguments'])
        observed = _observation(state['tool'], result.data['observation'])
        expected = {'kind': state['tool'], 'operation_id': state['operation_id'], 'observation': observed}
        valid = (result.ok and result.tool == state['tool'] and result.adapter_used == 'native_api'
                 and result.data == expected and verify(state, observed))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_system_effect_readback', detail=(
        'Exact native system effect read back.' if valid else 'System effect was not independently verified.'))


POWER_ACTION_SPECS = [ToolSpec(name=tool,
    description='Initiate ' + tool.replace('_', ' ') + ' after exact confirmation; never force applications closed; no automatic undo.',
    args_schema=ShutdownArgs if tool in ('restart_request', 'shutdown_request') else EmptyArgs,
    risk_class=RiskClass.HIGH, timeout_s=300 if tool == 'sleep_request' else 8,
    process_isolated=True, non_undoable=True, executor=partial(execute_power, tool=tool),
    verifier=verify_power, undo_builder=partial(capture_intent, tool=tool),
    adapter_priority=[AdapterPriority.NATIVE_API]) for tool in ('lock', 'sleep_request', 'restart_request', 'shutdown_request')]
