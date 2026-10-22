"""Plain-text clipboard tools; private undo data stays in runtime memory."""
from functools import partial
import uuid

from pydantic import Field, field_validator

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.clipboard_reads import ClipboardGetArgs, execute_get, verify_get

ClearClipboardArgs = GetClipboardArgs = ClipboardGetArgs
MUTATION_NAMES = ('clipboard_set', 'set_clipboard_text', 'clipboard_clear', 'clear_clipboard')


def valid_proof(value):
    return (isinstance(value, dict) and set(value) == {'sequence', 'owner', 'digest'}
        and type(value['sequence']) is int and 0 <= value['sequence'] <= 0xffffffff
        and type(value['owner']) is int and value['owner'] >= 0
        and isinstance(value['digest'], str) and len(value['digest']) == 64
        and all(char in '0123456789abcdef' for char in value['digest']))


def seal_capture(state):
    from copy import deepcopy
    record = {key: value for key, value in state.items() if key != 'clipboard_private'}
    if (set(record) != {'action', 'guard_version', 'volatile', 'undo_ref'}
            or record['action'] != 'clipboard_restore' or record['guard_version'] != 1
            or record['volatile'] is not True or str(uuid.UUID(record['undo_ref'])) != record['undo_ref']):
        raise ValueError('Invalid private clipboard intent.')
    private = state['clipboard_private']
    if (set(private) != {'clipboard_before', 'before_proof', 'after_proof'}
            or not valid_proof(private['before_proof']) or private['after_proof'] is not None):
        raise ValueError('Invalid private clipboard capture.')
    if private['clipboard_before'] is not None:
        SetClipboardArgs.model_validate({'text': private['clipboard_before']})
    return record, dict(deepcopy(private), record=deepcopy(record))


class SetClipboardArgs(ClipboardGetArgs):
    text: str = Field(max_length=65536)

    @field_validator('text')
    @classmethod
    def plain_text(cls, value):
        if chr(0) in value or len(value.encode('utf-16-le')) > 131072:
            raise ValueError('Clipboard text is invalid or exceeds its bound.')
        return value


def capture(args, context=None, *, tool):
    from pluma.adapters.clipboard_native import observe, text_of
    before = observe(getattr(context, 'cancellation_token', None))
    return {'action': 'clipboard_restore', 'guard_version': 1, 'volatile': True,
            'undo_ref': str(uuid.uuid4()), 'clipboard_private': {
                'clipboard_before': text_of(before), 'before_proof': before['proof'], 'after_proof': None}}


def execute_mutation(args, context=None, *, tool):
    from pluma.adapters.clipboard_native import write
    try:
        context.cancellation_token.raise_if_cancelled()
        entry = context.execution_binding['clipboard_private']
        record = entry['record']
        pending = next(item for item in reversed(context.undo_stack)
                       if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        if pending['pre_state'] != record:
            raise ValueError('Clipboard intent does not match private capture.')
        expected = SetClipboardArgs.model_validate(args).text if tool in MUTATION_NAMES[:2] else None
        after = write(expected, entry['before_proof'], context.cancellation_token)
        result = ToolResult.success(tool, data={'is_empty': expected is None, 'char_count': len(expected or '')},
            verified=False, undo_record=record, adapter_used='native_clipboard',
            factual_message='Clipboard cleared and read back.' if expected is None else 'Plain text copied to the clipboard and read back.').model_copy(
                update={'private_context': {'clipboard_receipt': {
                    'record': record, 'after_proof': after, 'expected_text': expected}}})
        checked = verify_mutation(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except Exception:
        return ToolResult.failure(tool, 'Clipboard change refused or unverified. Effects may remain.', 'CLIPBOARD_WRITE_UNVERIFIED')


def verify_mutation(result):
    from pluma.adapters.clipboard_native import observe, text_of
    try:
        receipt = result.private_context['clipboard_receipt']
        current = observe()
        expected = receipt['expected_text']
        valid = (result.ok and result.tool in MUTATION_NAMES and result.adapter_used == 'native_clipboard'
                 and result.undo_record == receipt['record'] and current['proof'] == receipt['after_proof']
                 and text_of(current) == expected
                 and result.data == {'is_empty': expected is None, 'char_count': len(expected or '')})
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_clipboard_readback', detail=(
        'Exact clipboard write independently read back.' if valid else 'Clipboard write was not independently verified.'))


def execute_clear_clipboard(args, task_context=None):
    return execute_mutation(args, task_context, tool='clear_clipboard')


def execute_set_clipboard_text(args, task_context=None):
    return execute_mutation(args, task_context, tool='set_clipboard_text')


def execute_get_clipboard_text(args, task_context=None):
    return execute_get(args, task_context, tool='get_clipboard_text')


CLIPBOARD_TOOL_SPECS = [ToolSpec(name=name, description='Read plain text from the Windows clipboard; private values stay out of history and planner context.',
    args_schema=ClipboardGetArgs, risk_class=RiskClass.READ, timeout_s=5, process_isolated=True,
    executor=partial(execute_get, tool=name), verifier=verify_get, adapter_priority=[AdapterPriority.NATIVE_API])
    for name in ('clipboard_get', 'get_clipboard_text')]
CLIPBOARD_TOOL_SPECS += [ToolSpec(name=name,
    description='Copy plain text to the clipboard.' if name in MUTATION_NAMES[:2] else 'Clear the plain-text clipboard.',
    args_schema=SetClipboardArgs if name in MUTATION_NAMES[:2] else ClipboardGetArgs,
    risk_class=RiskClass.LOW, timeout_s=8, process_isolated=True,
    executor=partial(execute_mutation, tool=name), verifier=verify_mutation,
    undo_builder=partial(capture, tool=name), adapter_priority=[AdapterPriority.NATIVE_API]) for name in MUTATION_NAMES]
