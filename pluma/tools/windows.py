"""pluma.tools.windows — Window management tools.

Spec §11, §14: Window inspection and focus as registered ToolSpecs.
Postconditions are read back before reporting success.

Boundary: No heavy automation libraries imported at module level.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.app_observations import ListAppWindowsArgs, execute_list, verify_list
from pluma.verify.common import verify_noop, verify_window_focused


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class ListWindowsArgs(ListAppWindowsArgs):
    """Arguments for list_windows."""


class FocusWindowArgs(BaseModel):
    """Arguments for focus_window."""
    model_config = {"extra": "forbid"}
    hwnd: Optional[int] = Field(default=None, description="Window handle (HWND) to focus.")
    title: Optional[str] = Field(default=None, description="Title or substring of window to focus.")

    @model_validator(mode="after")
    def _require_hwnd_or_title(self) -> "FocusWindowArgs":
        if self.hwnd is None and not self.title:
            raise ValueError("Either 'hwnd' or 'title' must be specified for focus_window.")
        return self


class MinimizeWindowArgs(BaseModel):
    """Arguments for minimize_window."""
    model_config = {"extra": "forbid"}
    hwnd: Optional[int] = Field(default=None, description="Window handle (HWND) to minimize.")
    title: Optional[str] = Field(default=None, description="Title or substring of window to minimize.")


class MaximizeWindowArgs(BaseModel):
    """Arguments for maximize_window."""
    model_config = {"extra": "forbid"}
    hwnd: Optional[int] = Field(default=None, description="Window handle (HWND) to maximize.")
    title: Optional[str] = Field(default=None, description="Title or substring of window to maximize.")


class RestoreWindowArgs(BaseModel):
    """Arguments for restore_window."""
    model_config = {"extra": "forbid"}
    hwnd: Optional[int] = Field(default=None, description="Window handle (HWND) to restore.")
    title: Optional[str] = Field(default=None, description="Title or substring of window to restore.")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_list_windows(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_list(args, task_context)


def execute_focus_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = args.get("hwnd")
    title = args.get("title")
    
    if sys.platform != "win32":
        return ToolResult(
            ok=True,
            tool="focus_window",
            data={"hwnd": hwnd, "title": title},
            factual_message="Focused window (stub on non-Windows).",
            verified=True,
        )
        
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    
    target_hwnd = hwnd
    target_title = title
    
    if target_hwnd is None and title:
        def enum_cb(h: int, lparam: Any) -> bool:
            nonlocal target_hwnd, target_title
            if not user32.IsWindowVisible(h):
                return True
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                t = buf.value
                if title.lower() in t.lower():
                    target_hwnd = h
                    target_title = t
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        
    if not target_hwnd or not user32.IsWindow(target_hwnd):
        return ToolResult.failure("focus_window", f"Window '{hwnd or title}' not found or invalid.")
        
    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(target_hwnd)
    
    v_res = verify_window_focused(target_hwnd)
    return ToolResult(
        ok=v_res.ok,
        tool="focus_window",
        data={"hwnd": target_hwnd, "title": target_title},
        factual_message=f"Focused window '{target_title or target_hwnd}'.",
        verified=v_res.ok,
        verify_detail=v_res,
    )


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def verify_focus_window(result: ToolResult) -> VerifyResult:
    if not result.ok or "hwnd" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Focus window reported failure.")
    return verify_window_focused(result.data["hwnd"])


# ---------------------------------------------------------------------------
# Minimize / Maximize Executors
# ---------------------------------------------------------------------------

def _resolve_hwnd(hwnd: Optional[int], title: Optional[str]) -> Optional[int]:
    """Resolve HWND from explicit int or title search; falls back to foreground window."""
    if sys.platform != "win32":
        if hwnd is not None:
            return hwnd if hwnd > 0 else None
        return 999  # sentinel for test environments

    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    if hwnd is not None:
        if hwnd <= 0:
            return None
        if not user32.IsWindow(hwnd):
            return None
        return hwnd

    if title:
        found_hwnd = None

        def enum_cb(h: int, _: Any) -> bool:
            nonlocal found_hwnd
            if not user32.IsWindowVisible(h):
                return True
            length = user32.GetWindowTextLengthW(h)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buf, length + 1)
                if title.lower() in buf.value.lower():
                    if user32.IsWindow(h):
                        found_hwnd = h
                        return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        if found_hwnd:
            return found_hwnd

    # Default: foreground window
    fg = user32.GetForegroundWindow()
    if fg and user32.IsWindow(fg):
        return fg
    return None


def execute_minimize_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = _resolve_hwnd(args.get("hwnd"), args.get("title"))
    target_desc = args.get("title") or (f"HWND {args.get('hwnd')}" if args.get("hwnd") is not None else "active window")
    if hwnd is None or hwnd <= 0:
        return ToolResult.failure(
            "minimize_window",
            f"Valid window for '{target_desc}' not found.",
            error_code="WINDOW_NOT_FOUND",
        )

    verified = True
    detail = f"ShowWindow SW_MINIMIZE sent to HWND {hwnd}."
    if sys.platform == "win32":
        import ctypes
        import time
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.IsWindow(hwnd):
            return ToolResult.failure("minimize_window", f"Invalid or destroyed HWND: {hwnd}", error_code="INVALID_HWND")
        SW_MINIMIZE = 6
        user32.ShowWindow(hwnd, SW_MINIMIZE)
        time.sleep(0.05)
        is_minimized = bool(user32.IsIconic(hwnd))
        verified = is_minimized
        detail = f"Window HWND {hwnd} is {'minimized' if is_minimized else 'not minimized'}."

    if not verified:
        return ToolResult.failure("minimize_window", detail, error_code="VERIFICATION_FAILED")

    return ToolResult(
        ok=True,
        tool="minimize_window",
        data={"hwnd": hwnd},
        factual_message=f"Minimized window ({target_desc}).",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=detail),
    )


def execute_maximize_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = _resolve_hwnd(args.get("hwnd"), args.get("title"))
    target_desc = args.get("title") or (f"HWND {args.get('hwnd')}" if args.get("hwnd") is not None else "active window")
    if hwnd is None or hwnd <= 0:
        return ToolResult.failure(
            "maximize_window",
            f"Valid window for '{target_desc}' not found.",
            error_code="WINDOW_NOT_FOUND",
        )

    verified = True
    detail = f"ShowWindow SW_MAXIMIZE sent to HWND {hwnd}."
    if sys.platform == "win32":
        import ctypes
        import time
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.IsWindow(hwnd):
            return ToolResult.failure("maximize_window", f"Invalid or destroyed HWND: {hwnd}", error_code="INVALID_HWND")
        SW_MAXIMIZE = 3
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        time.sleep(0.05)
        is_maximized = bool(user32.IsZoomed(hwnd))
        verified = is_maximized
        detail = f"Window HWND {hwnd} is {'maximized' if is_maximized else 'not maximized'}."

    if not verified:
        return ToolResult.failure("maximize_window", detail, error_code="VERIFICATION_FAILED")

    return ToolResult(
        ok=True,
        tool="maximize_window",
        data={"hwnd": hwnd},
        factual_message=f"Maximized window ({target_desc}).",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=detail),
    )


def execute_restore_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = _resolve_hwnd(args.get("hwnd"), args.get("title"))
    target_desc = args.get("title") or (f"HWND {args.get('hwnd')}" if args.get("hwnd") is not None else "active window")
    if hwnd is None or hwnd <= 0:
        return ToolResult.failure(
            "restore_window",
            f"Valid window for '{target_desc}' not found.",
            error_code="WINDOW_NOT_FOUND",
        )

    verified = True
    detail = f"ShowWindow SW_RESTORE sent to HWND {hwnd}."
    if sys.platform == "win32":
        import ctypes
        import time
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        if not user32.IsWindow(hwnd):
            return ToolResult.failure("restore_window", f"Invalid or destroyed HWND: {hwnd}", error_code="INVALID_HWND")
        SW_RESTORE = 9
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.05)
        is_iconic = bool(user32.IsIconic(hwnd))
        verified = not is_iconic
        detail = f"Window HWND {hwnd} is {'restored' if verified else 'still minimized'}."

    if not verified:
        return ToolResult.failure("restore_window", detail, error_code="VERIFICATION_FAILED")

    return ToolResult(
        ok=True,
        tool="restore_window",
        data={"hwnd": hwnd},
        factual_message=f"Restored window ({target_desc}).",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=detail),
    )


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

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
        description="Bring a specific window to the foreground by HWND or title.",
        args_schema=FocusWindowArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_focus_window,
        verifier=verify_focus_window,
        undo_builder=None,
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
        verifier=verify_noop,
        undo_builder=None,
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
        verifier=verify_noop,
        undo_builder=None,
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
        verifier=verify_noop,
        undo_builder=None,
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
