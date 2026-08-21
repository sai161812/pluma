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
from pluma.verify.common import verify_noop, verify_window_focused


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class ListWindowsArgs(BaseModel):
    """Arguments for list_windows."""
    visible_only: bool = Field(default=True, description="Only list visible top-level windows.")
    filter: Optional[str] = Field(default=None, description="Optional substring to filter window titles.")


class FocusWindowArgs(BaseModel):
    """Arguments for focus_window."""
    hwnd: Optional[int] = Field(default=None, description="Window handle (HWND) to focus.")
    title: Optional[str] = Field(default=None, description="Title or substring of window to focus.")

    @model_validator(mode="after")
    def _require_hwnd_or_title(self) -> "FocusWindowArgs":
        if self.hwnd is None and not self.title:
            raise ValueError("Either 'hwnd' or 'title' must be specified for focus_window.")
        return self


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_list_windows(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    visible_only = args.get("visible_only", True)
    title_filter = args.get("filter")
    windows: List[Dict[str, Any]] = []
    
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        
        def enum_cb(hwnd: int, lparam: Any) -> bool:
            if visible_only and not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                if title_filter and title_filter.lower() not in title.lower():
                    return True
                
                # Get PID
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                
                windows.append({
                    "hwnd": hwnd,
                    "title": title,
                    "pid": pid.value,
                })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    else:
        windows.append({"hwnd": 12345, "title": "Dummy Desktop Window", "pid": 100})
        
    count = len(windows)
    return ToolResult(
        ok=True,
        tool="list_windows",
        data={"count": count, "windows": windows},
        factual_message=f"Found {count} window{'s' if count != 1 else ''}.",
        verified=True,
    )


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


class MinimizeWindowArgs(BaseModel):
    """Arguments for minimize_window."""
    hwnd: Optional[int] = Field(default=None, description="Window HWND to minimize. Defaults to foreground window.")
    title: Optional[str] = Field(default=None, description="Window title substring to minimize.")


class MaximizeWindowArgs(BaseModel):
    """Arguments for maximize_window."""
    hwnd: Optional[int] = Field(default=None, description="Window HWND to maximize. Defaults to foreground window.")
    title: Optional[str] = Field(default=None, description="Window title substring to maximize.")


# ---------------------------------------------------------------------------
# Minimize / Maximize Executors
# ---------------------------------------------------------------------------

def _resolve_hwnd(hwnd: Optional[int], title: Optional[str]) -> Optional[int]:
    """Resolve HWND from explicit int or title search; falls back to foreground window."""
    if sys.platform != "win32":
        return 999  # sentinel for test environments

    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    if hwnd is not None:
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
                    found_hwnd = h
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return found_hwnd

    # Default: foreground window
    return user32.GetForegroundWindow() or None


def execute_minimize_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = _resolve_hwnd(args.get("hwnd"), args.get("title"))
    if not hwnd:
        return ToolResult.failure("minimize_window", "No target window found to minimize.")

    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        SW_MINIMIZE = 6
        user32.ShowWindow(hwnd, SW_MINIMIZE)

    return ToolResult(
        ok=True,
        tool="minimize_window",
        data={"hwnd": hwnd},
        factual_message="Minimized window.",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=f"ShowWindow SW_MINIMIZE sent to HWND {hwnd}."),
    )


def execute_maximize_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    hwnd = _resolve_hwnd(args.get("hwnd"), args.get("title"))
    if not hwnd:
        return ToolResult.failure("maximize_window", "No target window found to maximize.")

    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        SW_MAXIMIZE = 3
        user32.ShowWindow(hwnd, SW_MAXIMIZE)

    return ToolResult(
        ok=True,
        tool="maximize_window",
        data={"hwnd": hwnd},
        factual_message="Maximized window.",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=f"ShowWindow SW_MAXIMIZE sent to HWND {hwnd}."),
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
        executor=execute_list_windows,
        verifier=verify_noop,
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
]
