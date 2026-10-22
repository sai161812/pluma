"""pluma.tools.windows — Window management tools.

Spec §11, §14: Window inspection and focus as registered ToolSpecs.
Postconditions are read back before reporting success.

Boundary: No heavy automation libraries imported at module level.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional
from functools import partial

from pydantic import BaseModel, Field, model_validator

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.app_observations import ListAppWindowsArgs, execute_list, verify_list
from pluma.verify.common import verify_noop, verify_window_focused
from pluma.tools import window_focus as focus
from pluma.tools.window_focus import FocusWindowArgs


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class ListWindowsArgs(ListAppWindowsArgs):
    """Arguments for list_windows."""


class WindowStateArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    hwnd: Optional[int] = Field(default=None, gt=0, le=0xFFFFFFFFFFFFFFFF)
    pid: Optional[int] = Field(default=None, gt=0, le=0xFFFFFFFF)
    creation_time: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode='after')
    def exact_or_active(self):
        supplied = [self.hwnd is not None, self.pid is not None, self.creation_time is not None]
        if any(supplied) and not all(supplied):
            raise ValueError('Supply HWND, PID and creation time together, or omit all for the active window.')
        return self


MinimizeWindowArgs = MaximizeWindowArgs = RestoreWindowArgs = WindowStateArgs


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_list_windows(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_list(args, task_context)


def execute_focus_window(args, task_context=None):
    return focus.execute(args, task_context, tool='focus_window')


def verify_focus_window(result):
    return focus.verify(result)


def capture_state(args, context=None, *, tool):
    from pluma.adapters.window_state import capture
    if context is None:
        raise ValueError('Window mutation requires an owned task.')
    context.cancellation_token.raise_if_cancelled()
    return capture(args, tool)


def execute_state(args, task_context=None, *, tool):
    from pluma.adapters import window_state as native
    try:
        task_context.cancellation_token.raise_if_cancelled()
        state = next(item['pre_state'] for item in reversed(task_context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        if (state['action'] != 'window_state' or state['guard_version'] != 1 or state['tool'] != tool
                or bool(args.get('hwnd') is None) != state['active_target']
                or not state['active_target'] and any(state[key] != args[key] for key in ('hwnd', 'pid', 'creation_time'))):
            raise ValueError('Window state does not match captured intent.')
        receipt = native.apply(state, task_context.cancellation_token)
        return ToolResult.success(tool, data={key: receipt[key] for key in ('hwnd', 'pid', 'creation_time', 'after')},
            verified=True, undo_record=receipt, adapter_used='native_window_api',
            factual_message='Requested window state read back.').model_copy(update={'private_context': {'window_state': receipt}})
    except Exception:
        return ToolResult.failure(tool, 'Window state was refused or unverified. Pre-state retained.', 'WINDOW_STATE_UNVERIFIED')


def verify_state(result):
    from pluma.adapters.window_state import verify, TOOLS
    try:
        state = result.private_context['window_state']
        valid = (result.ok and result.verified and state['tool'] == result.tool and state['action'] == 'window_state'
            and state == result.undo_record and result.adapter_used == 'native_window_api'
            and state['after']['placement']['show'] == TOOLS[result.tool]
            and result.data == {key: state[key] for key in ('hwnd', 'pid', 'creation_time', 'after')}
            and verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_window_placement', detail=(
        'Exact window placement independently read back.' if valid else 'Window placement was not verified.'))


def execute_minimize_window(args, task_context=None):
    return execute_state(args, task_context, tool='minimize_window')


def execute_maximize_window(args, task_context=None):
    return execute_state(args, task_context, tool='maximize_window')


def execute_restore_window(args, task_context=None):
    return execute_state(args, task_context, tool='restore_window')


WINDOW_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="list_windows",
        description="Enumerate visible top-level desktop windows.",
        args_schema=ListWindowsArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_list_windows,
        verifier=verify_list,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="focus_window",
        description="Bring a specific window to the foreground by exact HWND, PID and creation time.",
        args_schema=FocusWindowArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_focus_window,
        verifier=verify_focus_window,
        undo_builder=partial(focus.capture, tool="focus_window"),
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="minimize_window",
        description="Minimize the active or specified window.",
        args_schema=MinimizeWindowArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_minimize_window,
        verifier=verify_state,
        undo_builder=partial(capture_state, tool="minimize_window"),
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="maximize_window",
        description="Maximize the active or specified window.",
        args_schema=MaximizeWindowArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_maximize_window,
        verifier=verify_state,
        undo_builder=partial(capture_state, tool="maximize_window"),
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="restore_window",
        description="Restore a minimized or maximized window to normal bounds.",
        args_schema=RestoreWindowArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_restore_window,
        verifier=verify_state,
        undo_builder=partial(capture_state, tool="restore_window"),
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]


class GeometryTargetArgs(BaseModel):
    model_config = {'strict': True, 'extra': 'forbid'}
    hwnd: int = Field(gt=0, le=0xFFFFFFFFFFFFFFFF)
    pid: int = Field(gt=0, le=0xFFFFFFFF)
    creation_time: int = Field(gt=0)


class MoveWindowArgs(GeometryTargetArgs):
    x: int = Field(ge=-2147483648, le=2147483647)
    y: int = Field(ge=-2147483648, le=2147483647)


class ResizeWindowArgs(GeometryTargetArgs):
    width: int = Field(gt=0, le=32767)
    height: int = Field(gt=0, le=32767)


def capture_geometry(args, context=None, *, tool):
    from pluma.adapters.window_geometry import capture
    token = getattr(context, 'cancellation_token', None)
    if token is not None:
        token.raise_if_cancelled()
    return capture(args, tool)


def execute_geometry(args, task_context=None, *, tool):
    from pluma.adapters import window_geometry as native
    try:
        if task_context is None:
            raise ValueError('A task-owned geometry journal is required.')
        state = next(item['pre_state'] for item in reversed(task_context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
        keys = ('x', 'y') if tool == 'move_window' else ('width', 'height')
        if (state['action'] != 'window_geometry' or state['guard_version'] != 1 or state['tool'] != tool
                or any(state[key] != args[key] for key in ('hwnd', 'pid', 'creation_time'))
                or any(state['after'][key] != args[key] for key in keys)):
            raise ValueError('Window geometry does not match its journal/arguments.')
        native.apply(state, getattr(task_context, 'cancellation_token', None))
        return ToolResult.success(tool, data={key: state[key] for key in ('hwnd', 'pid', 'creation_time', 'coordinate_space', 'after')},
            verified=True, adapter_used='native_window_api', factual_message='Window geometry changed.').model_copy(
                update={'private_context': {'window_geometry': state}})
    except Exception:
        return ToolResult.failure(tool, 'Window geometry could not be verified. Pre-state retained.', 'WINDOW_GEOMETRY_UNVERIFIED')


def verify_geometry(result):
    from pluma.adapters.window_geometry import verify
    try:
        state = result.private_context['window_geometry']
        valid = (result.ok and result.verified and state['tool'] == result.tool
            and state['action'] == 'window_geometry' and state['guard_version'] == 1
            and result.data == {key: state[key] for key in ('hwnd', 'pid', 'creation_time', 'coordinate_space', 'after')}
            and verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_window_identity_and_geometry',
        detail='Exact window geometry readback verified.' if valid else 'Window geometry was not verified.')


from functools import partial

WINDOW_TOOL_SPECS += [ToolSpec(name=name, description=description, args_schema=schema,
    risk_class=RiskClass.LOW, timeout_s=5, process_isolated=True,
    executor=partial(execute_geometry, tool=name), verifier=verify_geometry,
    undo_builder=partial(capture_geometry, tool=name), adapter_priority=[AdapterPriority.NATIVE_API])
    for name, description, schema in [
        ('move_window', 'Move one exact normal window in its native DPI coordinate units without changing foreground or size.', MoveWindowArgs),
        ('resize_window', 'Resize one exact normal window in its native DPI coordinate units without changing foreground or position.', ResizeWindowArgs),
    ]]
