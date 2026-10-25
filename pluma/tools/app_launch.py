"""Closed application aliases; native launch remains owned by the parent capsule."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from pluma.tools.base import ToolResult, VerifyResult


class OpenAppArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    app_name: Literal['notepad', 'paint', 'mspaint', 'calculator', 'calc', 'charmap', 'snippingtool', 'taskmgr']
    arguments: list[str] = Field(default_factory=list, max_length=0)
    working_dir: None = None

    @field_validator('app_name', mode='before')
    @classmethod
    def canonical_alias(cls, value):
        return value.strip().casefold().removesuffix('.exe') if isinstance(value, str) else value


def capture(args, context=None):
    from pluma.adapters.app_launch import capture as native_capture
    return native_capture(args, context)


def execute(args, context=None):
    from pluma.adapters import app_launch as native
    try:
        context.cancellation_token.raise_if_cancelled()
        state = next(item['pre_state'] for item in reversed(context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == 'open_app')
        if state['app_name'] != args['app_name'] or state['action'] != 'app_launch' or state['tool'] != 'open_app':
            raise ValueError('Application intent does not match its typed alias.')
        receipt = native.launch(state, context)
        return ToolResult.success('open_app', data={key: receipt[key] for key in ('app_name', 'pid', 'creation_time', 'windows')},
            verified=True, undo_record=receipt, adapter_used='native_owned_launch',
            factual_message='New owned application process and window read back.').model_copy(
                update={'private_context': {'app_launch': receipt}})
    except Exception:
        return ToolResult.failure('open_app', 'Owned application launch was refused or unverified. No existing instance was claimed.', 'APP_LAUNCH_UNVERIFIED')


def verify(result):
    from pluma.adapters.app_launch import verify as native_verify
    try:
        state = result.private_context['app_launch']
        valid = (result.ok and result.tool == 'open_app' and state['tool'] == result.tool
            and result.undo_record == state and result.adapter_used == 'native_owned_launch'
            and result.data == {key: state[key] for key in ('app_name', 'pid', 'creation_time', 'windows')}
            and native_verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_process_image_and_window',
        detail='New native application identity/window independently verified.' if valid else 'Application launch was not verified.')
