"""Explicit local preferences and validated, bounded routine definitions."""
import json
from typing import Annotated

from pydantic import BaseModel, Field, JsonValue, field_validator, model_validator

from pluma.brain.schemas import ToolCall
from pluma.memory import tool_store
from pluma.memory.redaction import _is_sensitive_key
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult

MemoryKey = Annotated[str, Field(min_length=1, max_length=128, pattern=r'^[a-z][a-z0-9_.-]*$')]


class KeyArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    key: MemoryKey

    @field_validator('key')
    @classmethod
    def public_key(cls, value):
        if _is_sensitive_key(value):
            raise ValueError('Private memory keys are unsupported.')
        return value


class SavePreferenceArgs(KeyArgs):
    value: JsonValue

    @field_validator('value')
    @classmethod
    def bounded_public_value(cls, value):
        tool_store.canonical(value)
        return value


class RoutineArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    name: MemoryKey

    @field_validator('name')
    @classmethod
    def public_name(cls, value):
        return KeyArgs.public_key(value)


class CreateRoutineArgs(RoutineArgs):
    steps: list[ToolCall] = Field(min_length=1, max_length=8)

    @model_validator(mode='after')
    def bounded_definition(self):
        from pluma.brain.schemas import RouteMode
        from pluma.brain.tool_subset import ToolSubsetSelector
        if any(s.tool == 'run_routine' or s.target_ref is not None for s in self.steps):
            raise ValueError('Nested routines and stored screen references are unsupported.')
        if any(not ToolSubsetSelector.is_tool_permitted(s.tool, RouteMode.SMART) for s in self.steps):
            raise ValueError('Routine step is outside the supported backend tool scope.')
        tool_store.canonical([s.model_dump() for s in self.steps])
        return self


def preference_prestate(args, context):
    return tool_store.capture(getattr(context, 'storage_path', None), 'preference', args['key'], args['value'])


def routine_prestate(args, context):
    return tool_store.capture(getattr(context, 'storage_path', None), 'routine', args['name'], args['steps'])


def _write(tool, args, context):
    try:
        pending = next(item for item in reversed(context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        state = pending['pre_state']
        value = args['value'] if tool == 'save_preference' else args['steps']
        key = args['key'] if tool == 'save_preference' else args['name']
        if (state['key'] != key or state['after_json'] != tool_store.canonical(value)
                or state['storage_path'] != context.storage_path):
            raise ValueError('Mutation does not match its journal.')
        context.cancellation_token.raise_if_cancelled()
        tool_store.write(state)
        return ToolResult.success(tool, data={'key' if tool == 'save_preference' else 'name': key},
            verified=False, factual_message='Saved preference.' if tool == 'save_preference' else 'Saved routine.',
            adapter_used='sqlite').model_copy(update={'private_context': {'memory_write': state}})
    except Exception:
        return ToolResult.failure(tool, 'Memory write could not be verified. Pre-state retained.', 'MEMORY_WRITE_FAILED')


def execute_save_preference(args, context):
    return _write('save_preference', args, context)


def execute_create_routine(args, context):
    return _write('create_routine', args, context)


def execute_get_preference(args, context):
    try:
        value, observed = tool_store.read(context.storage_path, 'preference', args['key'])
        return ToolResult.success('get_preference', data={'key': args['key'], 'found': observed is not None, 'value': value},
            verified=False, factual_message='Read preference.' if observed else 'Preference was not found.',
            adapter_used='sqlite').model_copy(update={'private_context': {'memory_read': {
                'storage_path': context.storage_path, 'key': args['key'], 'observed': observed}}})
    except Exception:
        return ToolResult.failure('get_preference', 'Preference could not be read.', 'MEMORY_READ_FAILED')


def verify_memory(result):
    try:
        if result.tool in ('save_preference', 'create_routine'):
            state = result.private_context['memory_write']
            kind = 'preference' if result.tool == 'save_preference' else 'routine'
            key_name = 'key' if result.tool == 'save_preference' else 'name'
            ok = result.ok and state['kind'] == kind and result.data == {key_name: state['key']} and tool_store.verify(state)
        elif result.tool == 'get_preference':
            receipt = result.private_context['memory_read']
            value, observed = tool_store.read(receipt['storage_path'], 'preference', receipt['key'])
            ok = result.ok and receipt['observed'] == observed and result.data == {
                'key': receipt['key'], 'value': value, 'found': observed is not None}
        else:
            ok = False
    except Exception:
        ok = False
    return VerifyResult(ok=ok, method='sqlite_readback', detail=(
        'Memory state read back from SQLite.' if ok else 'Memory state was not verified.'))


def execute_run_routine(args, context):
    """A bounded typed macro; every child still crosses registry/policy/ledger."""
    from pluma.tools.registry import ToolArgumentError
    with context.work_lock:
        if context.routine_active:
            return ToolResult.failure('run_routine', 'A routine is already active on this task.', 'ROUTINE_REENTRY')
        context.routine_active = True
        services = context.tool_services
    completed = 0
    try:
        context.cancellation_token.raise_if_cancelled()
        definition, observed = tool_store.read(context.storage_path, 'routine', args['name'])
        if observed is None:
            return ToolResult.failure('run_routine', 'Routine was not found.', 'ROUTINE_NOT_FOUND')
        plan = CreateRoutineArgs(name=args['name'], steps=definition)
        registry = services['registry']
        ledger = services['ledger']
        if ledger is None or not ledger._db.is_open:
            raise ValueError('Routine execution requires its actual ledger.')
        # Validate the complete stored sequence before its first effect.
        calls = []
        for step in plan.steps:
            if not registry.contains(step.tool):
                raise ToolArgumentError('Routine contains an unavailable tool.')
            calls.append((step.tool, registry._validate_args(registry.lookup(step.tool), step.arguments)))
        if context.tool_call_count + len(calls) > 20:
            return ToolResult.failure('run_routine', 'Routine exceeds the remaining task limit.', 'TOOL_CALL_LIMIT')
        action_ids = []
        for tool, arguments in calls:
            context.cancellation_token.raise_if_cancelled()
            child_index = context.next_action_index
            result = registry.execute(tool, arguments, context, services['ledger'],
                policy_engine=services['policy'])
            if not result.ok or not result.verified:
                return ToolResult.failure('run_routine', 'Routine stopped after a failed or unverified step.', 'ROUTINE_STEP_FAILED')
            action = ledger._db.execute_read_one('SELECT id FROM actions WHERE task_id=? AND step_index=? AND tool=? AND verified=1',
                (context.task_id, child_index, tool))
            if action is None:
                raise ValueError('Verified child history was not found.')
            action_ids.append({'id': action['id'], 'tool': tool})
            completed += 1
        return ToolResult.success('run_routine', data={'name': args['name'], 'completed_steps': completed,
            'planned_steps': len(calls)}, verified=False, factual_message=f'Completed {completed} routine steps.',
            adapter_used='task_service').model_copy(update={'private_context': {'routine_receipt': {
                'task_id': context.task_id, 'storage_path': context.storage_path, 'name': args['name'],
                'actions': action_ids, 'completed': completed, 'planned': len(calls)}}})
    except Exception:
        return ToolResult.failure('run_routine', 'Routine could not complete. Prior effects remain tracked.', 'ROUTINE_FAILED')
    finally:
        with context.work_lock:
            context.routine_active = False


def verify_routine(result):
    try:
        receipt = result.private_context['routine_receipt']
        ok = (result.ok and result.tool == 'run_routine' and receipt['completed'] == receipt['planned']
              == result.data['completed_steps'] == result.data['planned_steps'] and 1 <= receipt['planned'] <= 8
              and result.data['name'] == receipt['name']
              and len(receipt['actions']) == receipt['completed']
              and len({a['id'] for a in receipt['actions']}) == receipt['completed'])
        with tool_store.connect(receipt['storage_path']) as db:
            for action in receipt['actions']:
                observed = db.execute('SELECT task_id,tool,verified FROM actions WHERE id=?', (action['id'],)).fetchone()
                ok = ok and observed is not None and list(observed) == [receipt['task_id'], action['tool'], 1]
    except Exception:
        ok = False
    return VerifyResult(ok=ok, method='verified_child_calls', detail=(
        'All routine steps have verified registry results.' if ok else 'Routine completion was not verified.'))


MEMORY_TOOL_SPECS = [
    ToolSpec(name='run_routine', description='Run a saved bounded routine through this task and current policy.',
        args_schema=RoutineArgs, risk_class=RiskClass.MEDIUM, timeout_s=60, execution_scope='task_service',
        executor=execute_run_routine, verifier=verify_routine),
    ToolSpec(name='save_preference', description='Save one explicitly requested, non-secret local preference.',
        args_schema=SavePreferenceArgs, risk_class=RiskClass.MEDIUM, timeout_s=5, process_isolated=True,
        executor=execute_save_preference, undo_builder=preference_prestate, verifier=verify_memory),
    ToolSpec(name='get_preference', description='Read one explicit non-secret local preference.',
        args_schema=KeyArgs, risk_class=RiskClass.READ, timeout_s=5, process_isolated=True,
        executor=execute_get_preference, verifier=verify_memory),
    ToolSpec(name='create_routine', description='Save up to eight validated tool calls as a local routine.',
        args_schema=CreateRoutineArgs, risk_class=RiskClass.MEDIUM, timeout_s=5, process_isolated=True,
        executor=execute_create_routine, undo_builder=routine_prestate, verifier=verify_memory),
]
