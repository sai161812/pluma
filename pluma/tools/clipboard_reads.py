"""Typed private native plain-text clipboard reads with independent readback."""
from pydantic import BaseModel

from pluma.tools.base import ToolResult, VerifyResult


class ClipboardGetArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}


def execute_get(args, context=None, *, tool='clipboard_get'):
    from pluma.adapters.clipboard_native import observe
    try:
        ClipboardGetArgs.model_validate(args)
        observation = observe(getattr(context, 'cancellation_token', None))
        count = len(observation['data']['formats'])
        unknown = len(observation['data']['unsupported_format_ids'])
        result = ToolResult.success(tool, data=observation['data'], verified=False,
            factual_message=f'Read plain-text clipboard state; {unknown} non-text formats are outside this operation.',
            adapter_used='native_clipboard').model_copy(update={
                'private_context': {'clipboard_observation': observation}})
        checked = verify_get(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except Exception:
        return ToolResult.failure(tool, 'Clipboard could not be read. No empty-content claim was made.', 'CLIPBOARD_READ_FAILED')


def verify_get(result):
    from pluma.adapters.clipboard_native import observe
    try:
        packet = result.private_context['clipboard_observation']
        valid = (result.ok and result.tool in ('clipboard_get', 'get_clipboard_text')
                 and result.adapter_used == 'native_clipboard' and result.data == packet['data']
                 and observe() == packet)
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_clipboard_sequence_and_content', detail=(
        'Native clipboard sequence, owner and supported contents independently read back.' if valid
        else 'Clipboard observation changed or readback failed.'))
