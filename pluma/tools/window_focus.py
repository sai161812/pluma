"""Registered focus tools with minimal native foreground/placement undo."""
from functools import partial
from typing import Optional
from pydantic import BaseModel, Field, model_validator
from pluma.tools.base import ToolResult, VerifyResult


class FocusWindowArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    hwnd: int = Field(gt=0, le=0xFFFFFFFFFFFFFFFF)
    pid: int = Field(gt=0, le=0xFFFFFFFF)
    creation_time: int = Field(gt=0)


class FocusAppArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    app_name: Optional[str] = Field(default=None, min_length=1, max_length=128, pattern=r'^[\w.-]+$')
    hwnd: Optional[int] = Field(default=None, gt=0, le=0xFFFFFFFFFFFFFFFF)
    pid: Optional[int] = Field(default=None, gt=0, le=0xFFFFFFFF)
    creation_time: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode='after')
    def name_or_window(self):
        fields = (self.hwnd, self.pid, self.creation_time)
        if self.app_name is not None and any(value is not None for value in fields):
            raise ValueError('Supply a name or one exact window target.')
        if self.app_name is None and any(value is None for value in fields):
            raise ValueError('Supply one unambiguous application name or an exact window identity.')
        return self


def capture(args, context=None, *, tool):
    from pluma.adapters.window_focus import capture as native_capture
    context.cancellation_token.raise_if_cancelled()
    return native_capture(args, tool)


def execute(args, context=None, *, tool):
    from pluma.adapters import window_focus as native
    try:
        context.cancellation_token.raise_if_cancelled()
        state = next(item['pre_state'] for item in reversed(context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        if (state['action'] != 'window_focus' or state['guard_version'] != 1 or state['tool'] != tool
                or native.target(args, tool) != {key: state[key] for key in ('hwnd', 'pid', 'creation_time')}):
            raise ValueError('Focus intent does not match the target.')
        receipt = native.apply(state, context.cancellation_token)
        return ToolResult.success(tool, data={key: state[key] for key in ('hwnd', 'pid', 'creation_time')},
            verified=True, undo_record=receipt, adapter_used='native_window_api',
            factual_message='Exact target foreground identity read back.').model_copy(update={'private_context': {'window_focus': receipt}})
    except Exception:
        return ToolResult.failure(tool, 'Focus refused or unverified; Windows foreground restrictions were preserved.', 'FOCUS_UNVERIFIED')


def verify(result):
    from pluma.adapters.window_focus import verify as native_verify
    try:
        state = result.private_context['window_focus']
        valid = (result.ok and state['tool'] == result.tool and result.undo_record == state
            and result.adapter_used == 'native_window_api'
            and result.data == {key: state[key] for key in ('hwnd', 'pid', 'creation_time')} and native_verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_foreground_identity',
        detail='Exact foreground readback verified.' if valid else 'Foreground identity was not verified.')
