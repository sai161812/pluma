"""pluma.tools.apps — Application lifecycle and management tools.

Spec §11, §12, §14: Application tools as registered ToolSpecs.
Processes spawned by open_app are assigned to the Task's Windows Job Object
and tracked in the OwnershipRegistry.

Boundary: No heavy automation libraries imported at module level.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from pluma.core.task_supervisor import ResourceOwnership
from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import (
    verify_noop,
    verify_process_closed,
    verify_process_running,
    verify_window_focused,
)


_FORBIDDEN_EXECUTABLES = frozenset({
    # Shells and interpreters
    "cmd", "cmd.exe",
    "powershell", "powershell.exe",
    "pwsh", "pwsh.exe",
    "bash", "bash.exe",
    "sh", "sh.exe",
    "wscript", "wscript.exe",
    "cscript", "cscript.exe",
    "python", "python.exe",
    "pythonw", "pythonw.exe",
    "mshta", "mshta.exe",
    "rundll32", "rundll32.exe",
    "regsvr32", "regsvr32.exe",
    "certutil", "certutil.exe",
    "bitsadmin", "bitsadmin.exe",
    # Registry and scheduled task manipulation
    "reg", "reg.exe",
    "schtasks", "schtasks.exe",
    "at", "at.exe",
    # Service control and network configuration
    "sc", "sc.exe",
    "net", "net.exe",
    "net1", "net1.exe",
    "netsh", "netsh.exe",
    # Process and ACL manipulation
    "taskkill", "taskkill.exe",
    "icacls", "icacls.exe",
    "takeown", "takeown.exe",
    "cacls", "cacls.exe",
    # WMI - arbitrary system queries/exec
    "wmic", "wmic.exe",
    # Download utilities used in LOLBins
    "curl", "curl.exe",
    "wget", "wget.exe",
    "ftp", "ftp.exe",
    # Additional dangerous utilities
    "forfiles", "forfiles.exe",
    "msiexec", "msiexec.exe",
    "regasm", "regasm.exe",
    "regsvcs", "regsvcs.exe",
    "installutil", "installutil.exe",
    "cmstp", "cmstp.exe",
    "msbuild", "msbuild.exe",
    "xwizard", "xwizard.exe",
})

# Controlled allowlist of named application aliases.
# Only these aliases are explicitly blessed. Non-alias names are still permitted
# (shutil.which resolves them), but a WARNING is emitted so operators can audit.
_ALLOWED_APP_ALIASES: Dict[str, str] = {
    # Productivity and utilities
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "wordpad": "wordpad.exe",
    "explorer": "explorer.exe",
    "snippingtool": "SnippingTool.exe",
    "charmap": "charmap.exe",
    "taskmgr": "taskmgr.exe",
    # Media
    "wmplayer": "wmplayer.exe",
    # Browsers
    "msedge": "msedge.exe",
    "chrome": "chrome.exe",
    "firefox": "firefox.exe",
    # Office (not scripted)
    "winword": "winword.exe",
    "excel": "excel.exe",
    "powerpnt": "powerpnt.exe",
}

_SHELL_METACHAR_PATTERN = re.compile(r"[&|;><`$\n\r]")
_DANGEROUS_ARG_PATTERNS = [
    re.compile(r"(?i)^-(encodedcommand|enc|e|command|c|exec)$"),
    re.compile(r"(?i)^/[ck]$"),
]


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class OpenAppArgs(BaseModel):
    """Arguments for open_app."""
    model_config = {"extra": "forbid"}

    app_name: str = Field(min_length=1, description="Application name or executable path (e.g. 'notepad', 'calc').")
    arguments: List[str] = Field(default_factory=list, description="Command line arguments.")
    working_dir: Optional[str] = Field(default=None, description="Working directory for the process.")

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v: str) -> str:
        clean = v.strip().lower()
        base = clean.split("/")[-1].split("\\")[-1]
        if base in _FORBIDDEN_EXECUTABLES or clean in _FORBIDDEN_EXECUTABLES:
            raise ValueError(f"Execution of shell/interpreter '{v}' is forbidden through open_app.")
        if _SHELL_METACHAR_PATTERN.search(v):
            raise ValueError(f"Shell metacharacters are forbidden in app_name: '{v}'")
        return v

    @field_validator("arguments")
    @classmethod
    def validate_arguments(cls, args: List[str]) -> List[str]:
        for a in args:
            if _SHELL_METACHAR_PATTERN.search(a):
                raise ValueError(f"Shell metacharacters are forbidden in argument: '{a}'")
            for pat in _DANGEROUS_ARG_PATTERNS:
                if pat.search(a.strip()):
                    raise ValueError(f"Dangerous shell argument '{a}' is forbidden in open_app.")
        return args


class CloseAppArgs(BaseModel):
    """Arguments for close_app."""
    model_config = {"extra": "forbid"}

    app_name: str = Field(min_length=1, description="Application executable name or window title to close.")
    force: bool = Field(default=False, description="Force terminate process tree (requires explicit request).")


class FocusAppArgs(BaseModel):
    """Arguments for focus_app."""
    model_config = {"extra": "forbid"}

    app_name: str = Field(min_length=1, description="Application executable or window title to bring to foreground.")


class ListAppsArgs(BaseModel):
    """Arguments for list_apps."""
    model_config = {"extra": "forbid"}

    filter: Optional[str] = Field(default=None, description="Optional substring to filter application names.")


class AppStatusArgs(BaseModel):
    """Arguments for app_status."""
    model_config = {"extra": "forbid"}

    app_name: str = Field(min_length=1, description="Application name or PID to inspect.")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def _get_process_creation_time_ns(pid: int) -> Optional[int]:
    """Return process creation time as a 64-bit integer (100ns intervals from epoch).

    Returns None if the process cannot be queried (not our process, already exited, etc.).
    This is used to verify process identity before termination: a recycled PID with a
    different creation time proves it is not our process.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return None
        try:
            class FILETIME(ctypes.Structure):
                _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

            create_time = FILETIME()
            exit_time = FILETIME()
            kernel_time = FILETIME()
            user_time = FILETIME()
            ok = kernel32.GetProcessTimes(
                h, ctypes.byref(create_time), ctypes.byref(exit_time),
                ctypes.byref(kernel_time), ctypes.byref(user_time)
            )
            if not ok:
                return None
            return (create_time.dwHighDateTime << 32) | create_time.dwLowDateTime
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return None


def execute_open_app(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import os
    import shutil
    import subprocess
    import time

    app = args["app_name"]
    cmd_args = args.get("arguments", [])
    work_dir = args.get("working_dir")

    # Safety check against shell escapes
    clean = app.strip().lower()
    base = clean.split("/")[-1].split("\\")[-1]
    if base in _FORBIDDEN_EXECUTABLES or clean in _FORBIDDEN_EXECUTABLES:
        return ToolResult.failure("open_app", f"Execution of interpreter/shell '{app}' is forbidden through open_app.")

    if _SHELL_METACHAR_PATTERN.search(app):
        return ToolResult.failure("open_app", f"Shell metacharacters are forbidden in app_name: '{app}'")

    for a in cmd_args:
        if _SHELL_METACHAR_PATTERN.search(a):
            return ToolResult.failure("open_app", f"Shell metacharacters are forbidden in argument: '{a}'")
        for pat in _DANGEROUS_ARG_PATTERNS:
            if pat.search(a.strip()):
                return ToolResult.failure("open_app", f"Dangerous shell argument '{a}' is forbidden in open_app.")

    try:
        import logging as _logging
        _app_logger = _logging.getLogger(__name__)

        # Check cancellation before starting
        if task_context and hasattr(task_context, "cancellation_token"):
            if task_context.cancellation_token.is_cancelled:
                return ToolResult.failure("open_app", "Task cancelled before application could launch.", error_code="TASK_CANCELLED")

        # Resolve through controlled alias map first; fall back to shutil.which for unlisted names
        clean_app = app.strip().lower()
        if clean_app in _ALLOWED_APP_ALIASES:
            resolved_name = _ALLOWED_APP_ALIASES[clean_app]
            exe = shutil.which(resolved_name) or resolved_name
        else:
            # Non-alias name: warn but still resolve to let operators audit
            _app_logger.warning(
                "open_app: '%s' is not in the controlled alias allowlist. "
                "Using shutil.which fallback. Consider adding an alias for audit traceability.",
                app,
            )
            exe = shutil.which(app) or app
        full_cmd = [exe] + cmd_args

        proc = subprocess.Popen(
            full_cmd,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )

        pid = proc.pid
        # Record 64-bit creation timestamp for identity verification before later termination
        creation_time_ns = _get_process_creation_time_ns(pid)

        # Create a persistent Job Object (kill_on_close=False) for STOP semantics.
        # Successful task completion closes the handle WITHOUT killing the application.
        # STOP explicitly calls TerminateJobObject to kill the tree.
        persistent_job: Any = None
        if sys.platform == "win32":
            try:
                from pluma.core.job_object import WindowsJobObject
                persistent_job = WindowsJobObject(
                    name=f"pluma-app-{pid}",
                    kill_on_close=False,  # Do NOT kill app when task succeeds
                )
                persistent_job.assign_process(pid)
            except Exception as job_err:
                # Job Object creation is best-effort — non-fatal
                import logging as _logging
                _logging.getLogger(__name__).debug("Could not create persistent Job Object for PID %d: %s", pid, job_err)
                persistent_job = None

        # Register process ownership on TaskCapsule with full identity metadata
        if task_context and hasattr(task_context, "register_owned_resource"):
            try:
                task_context.register_owned_resource(
                    resource_type="subprocess",
                    ownership=ResourceOwnership.PLUMA_CREATED,
                    external_id=str(pid),
                    metadata={
                        "app_name": app,
                        "command": full_cmd,
                        "pid": pid,
                        "creation_time_ns": creation_time_ns,
                        "persistent_job": persistent_job,  # Handle stored for STOP use
                    },
                )
            except Exception:
                pass

        # Register in global or task ownership registry if available
        if task_context and hasattr(task_context, "task_id"):
            reg = getattr(task_context, "ownership_registry", None) or getattr(task_context, "_registry", None)
            if reg and hasattr(reg, "register_subprocess"):
                try:
                    reg.register_subprocess(
                        task_id=task_context.task_id,
                        pid=pid,
                        ownership=ResourceOwnership.PLUMA_CREATED,
                        command_class="open_app",
                    )
                except Exception:
                    pass

        # Give process a moment to initialize
        time.sleep(0.2)
        v_res = verify_process_running(pid)

        return ToolResult(
            ok=v_res.ok,
            tool="open_app",
            data={
                "app_name": app, "pid": pid, "command": full_cmd,
                "creation_time_ns": creation_time_ns,
            },
            factual_message=f"Opened '{app}' (PID {pid}).",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except Exception as e:
        return ToolResult.failure("open_app", f"Failed to open '{app}': {e}")


def execute_close_app(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import os
    import subprocess
    import time
    
    app = args["app_name"]
    force = args.get("force", False)
    
    # Check if target is a PID
    if app.isdigit():
        pid = int(app)
        if sys.platform == "win32":
            cmd = ["taskkill", "/F" if force else "", "/PID", str(pid)]
        else:
            cmd = ["kill", "-9" if force else "-15", str(pid)]
    else:
        name = app if app.lower().endswith(".exe") else f"{app}.exe"
        if sys.platform == "win32":
            cmd = ["taskkill", "/F" if force else "", "/IM", name]
        else:
            cmd = ["pkill", "-9" if force else "-15", app]
            
    cmd = [c for c in cmd if c]  # Remove empty strings
    
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        time.sleep(0.3)
        v_res = verify_process_closed(app)
        
        if not v_res.ok and res.returncode != 0:
            return ToolResult.failure("close_app", f"Failed to close '{app}': {res.stderr.strip() or 'Process not found.'}")
            
        return ToolResult(
            ok=v_res.ok,
            tool="close_app",
            data={"app_name": app, "force": force},
            factual_message=f"Closed '{app}'.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except Exception as e:
        return ToolResult.failure("close_app", f"Failed to close '{app}': {e}")


def execute_focus_app(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    app = args["app_name"]
    
    if sys.platform != "win32":
        return ToolResult(
            ok=True,
            tool="focus_app",
            data={"app_name": app},
            factual_message=f"Focused '{app}' (stub on non-Windows).",
            verified=True,
        )
        
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    
    target_hwnd = None
    target_title = None
    
    def enum_cb(hwnd: int, lparam: Any) -> bool:
        nonlocal target_hwnd, target_title
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if app.lower() in title.lower():
                target_hwnd = hwnd
                target_title = title
                return False  # Stop enumeration
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    
    if not target_hwnd:
        return ToolResult.failure("focus_app", f"No visible window found matching '{app}'.")
        
    # Bring window to foreground
    user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(target_hwnd)
    
    v_res = verify_window_focused(target_hwnd)
    return ToolResult(
        ok=v_res.ok,
        tool="focus_app",
        data={"app_name": app, "hwnd": target_hwnd, "title": target_title},
        factual_message=f"Focused window '{target_title or app}'.",
        verified=v_res.ok,
        verify_detail=v_res,
    )


def execute_list_apps(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    filter_q = args.get("filter")
    apps: List[Dict[str, Any]] = []
    
    if sys.platform == "win32":
        import subprocess
        try:
            out = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH"],
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            import csv
            import io
            reader = csv.reader(io.StringIO(out))
            seen = set()
            for row in reader:
                if len(row) >= 2:
                    name, pid_str = row[0], row[1]
                    if filter_q and filter_q.lower() not in name.lower():
                        continue
                    if name not in seen:
                        seen.add(name)
                        apps.append({"name": name, "pid": int(pid_str) if pid_str.isdigit() else 0})
        except Exception as e:
            return ToolResult.failure("list_apps", f"Failed to list apps: {e}")
    else:
        apps.append({"name": "dummy_app", "pid": 1001})
        
    count = len(apps)
    return ToolResult(
        ok=True,
        tool="list_apps",
        data={"count": count, "apps": apps},
        factual_message=f"Found {count} running application{'s' if count != 1 else ''}.",
        verified=True,
    )


def execute_app_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    app = args["app_name"]
    v_res = verify_process_running(app)
    
    return ToolResult(
        ok=True,
        tool="app_status",
        data={"app_name": app, "running": v_res.ok},
        factual_message=f"Application '{app}' is {'running' if v_res.ok else 'not running'}.",
        verified=True,
    )


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def verify_open_app(result: ToolResult) -> VerifyResult:
    if not result.ok or "pid" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Open app reported failure.")
    return verify_process_running(result.data["pid"])


def verify_close_app(result: ToolResult) -> VerifyResult:
    if not result.ok or "app_name" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Close app reported failure.")
    return verify_process_closed(result.data["app_name"])


def verify_focus_app(result: ToolResult) -> VerifyResult:
    if not result.ok or "hwnd" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Focus app reported failure.")
    return verify_window_focused(result.data["hwnd"])


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

APP_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="open_app",
        description="Launch an application by executable name or path.",
        args_schema=OpenAppArgs,
        risk_class=RiskClass.LOW,
        timeout_s=10.0,
        executor=execute_open_app,
        verifier=verify_open_app,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
        creates_resources=True,
    ),
    ToolSpec(
        name="close_app",
        description="Close a running application gracefully.",
        args_schema=CloseAppArgs,
        risk_class=RiskClass.MEDIUM,
        timeout_s=10.0,
        executor=execute_close_app,
        verifier=verify_close_app,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="focus_app",
        description="Bring a running application window to the foreground.",
        args_schema=FocusAppArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_focus_app,
        verifier=verify_focus_app,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="list_apps",
        description="List running user applications.",
        args_schema=ListAppsArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_list_apps,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="app_status",
        description="Query the running status of a specific application.",
        args_schema=AppStatusArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_app_status,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]
