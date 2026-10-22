"""Typed application operations built on native exact-target process control."""
from typing import Optional
from pydantic import BaseModel, Field, model_validator

from pluma.tools.base import ToolResult
from pluma.tools.processes import execute_process_control, verify_process_control


class CloseAppArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    app_name: Optional[str] = Field(default=None, min_length=1, max_length=128, pattern=r'^[\w.-]+$')
    pid: Optional[int] = Field(default=None, gt=0, le=0xFFFFFFFF)
    creation_time: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode='after')
    def name_or_exact(self):
        if self.app_name is not None:
            if self.pid is not None or self.creation_time is not None:
                raise ValueError('Supply one application name or an exact PID/creation time.')
        elif self.pid is None or self.creation_time is None:
            raise ValueError('An exact PID/creation time or one unambiguous application name is required.')
        return self


def capture_close(args, context=None):
    from pluma.adapters.app_targets import process
    from pluma.adapters.process_control import capture_intent
    return capture_intent(process(args), context, tool='close_app')


def execute_close(args, context=None):
    from pluma.adapters.app_targets import process
    try:
        context.cancellation_token.raise_if_cancelled()
        return execute_process_control(process(args), context, tool='close_app')
    except Exception:
        return ToolResult.failure('close_app', 'Application target is ambiguous, changed or unavailable. No force fallback.', 'APP_CLOSE_UNVERIFIED')


verify_close = verify_process_control
