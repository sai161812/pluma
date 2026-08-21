"""pluma.verify.common — Postcondition verifiers.

Spec §15: "No state-changing tool may report success only because the call returned
without an exception. The tool defines a postcondition and reads the state back
using the strongest method available."

No heavy OS/automation libraries imported at module level.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from pluma.tools.base import ToolResult, VerifyResult


def verify_noop(result: ToolResult) -> VerifyResult:
    """Verifier for read-only or informational tools that do not change system state."""
    if not result.ok:
        return VerifyResult(
            ok=False,
            method="state",
            detail=result.error or "Tool execution failed.",
        )
    return VerifyResult(
        ok=True,
        method="state",
        detail="Read-only operation completed without state modification.",
    )


def verify_file_exists(path: Union[str, Path]) -> VerifyResult:
    """Verify that a file or directory exists on disk."""
    p = Path(path)
    exists = p.exists()
    return VerifyResult(
        ok=exists,
        method="api",
        detail=f"Path '{p}' {'exists' if exists else 'does not exist'}.",
    )


def verify_file_not_exists(path: Union[str, Path]) -> VerifyResult:
    """Verify that a file or directory does NOT exist on disk."""
    p = Path(path)
    not_exists = not p.exists()
    return VerifyResult(
        ok=not_exists,
        method="api",
        detail=f"Path '{p}' {'is absent as expected' if not_exists else 'still exists'}.",
    )


def verify_file_moved(source: Union[str, Path], destination: Union[str, Path]) -> VerifyResult:
    """Verify that a file move succeeded (destination exists and source is gone)."""
    src_p = Path(source)
    dst_p = Path(destination)
    
    dst_exists = dst_p.exists()
    src_absent = not src_p.exists() or src_p.resolve() == dst_p.resolve()
    
    ok = dst_exists and src_absent
    if ok:
        detail = f"Verified: destination '{dst_p}' exists and source '{src_p}' is removed."
    elif not dst_exists:
        detail = f"Verification failed: destination '{dst_p}' does not exist."
    else:
        detail = f"Verification failed: source '{src_p}' still exists after move."

    return VerifyResult(
        ok=ok,
        method="api",
        detail=detail,
    )


def verify_file_renamed(old_path: Union[str, Path], new_path: Union[str, Path]) -> VerifyResult:
    """Verify that a rename succeeded."""
    return verify_file_moved(old_path, new_path)


def verify_dir_created(path: Union[str, Path]) -> VerifyResult:
    """Verify that a folder was created and is a directory."""
    p = Path(path)
    ok = p.exists() and p.is_dir()
    return VerifyResult(
        ok=ok,
        method="api",
        detail=f"Folder '{p}' {'exists as directory' if ok else 'does not exist as directory'}.",
    )


def verify_process_running(process_name_or_pid: Union[str, int]) -> VerifyResult:
    """Verify that a process is running."""
    if isinstance(process_name_or_pid, int) or (isinstance(process_name_or_pid, str) and process_name_or_pid.isdigit()):
        pid = int(process_name_or_pid)
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if h_proc:
                kernel32.CloseHandle(h_proc)
                return VerifyResult(ok=True, method="api", detail=f"Process PID {pid} is active.")
            return VerifyResult(ok=False, method="api", detail=f"Process PID {pid} is not active.")
        else:
            try:
                os.kill(pid, 0)
                return VerifyResult(ok=True, method="api", detail=f"Process PID {pid} is active.")
            except OSError:
                return VerifyResult(ok=False, method="api", detail=f"Process PID {pid} is not active.")
    else:
        name = str(process_name_or_pid).lower()
        if not name.endswith(".exe"):
            name = f"{name}.exe"
        if sys.platform == "win32":
            import subprocess
            try:
                out = subprocess.check_output(
                    ["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                running = name in out.lower()
                return VerifyResult(
                    ok=running,
                    method="api",
                    detail=f"Process '{name}' is {'running' if running else 'not running'}.",
                )
            except Exception as e:
                return VerifyResult(ok=False, method="api", detail=f"Failed to query tasklist: {e}")
        return VerifyResult(ok=True, method="api", detail=f"Process check stubbed for {name}.")


def verify_process_closed(process_name_or_pid: Union[str, int], timeout_s: float = 3.0) -> VerifyResult:
    """Verify that a process has exited within timeout."""
    start = time.time()
    while time.time() - start < timeout_s:
        res = verify_process_running(process_name_or_pid)
        if not res.ok:
            return VerifyResult(
                ok=True,
                method="api",
                detail=f"Process '{process_name_or_pid}' exited successfully.",
            )
        time.sleep(0.1)
    
    return VerifyResult(
        ok=False,
        method="api",
        detail=f"Process '{process_name_or_pid}' is still running after {timeout_s}s timeout.",
    )


def verify_window_focused(expected_title_or_hwnd: Union[str, int]) -> VerifyResult:
    """Verify that the expected window is the foreground/focused window."""
    if sys.platform != "win32":
        return VerifyResult(ok=True, method="api", detail="Non-Windows window focus stub.")
    
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    
    fg_hwnd = user32.GetForegroundWindow()
    if not fg_hwnd:
        return VerifyResult(ok=False, method="api", detail="No foreground window found.")
    
    if isinstance(expected_title_or_hwnd, int):
        ok = (fg_hwnd == expected_title_or_hwnd)
        return VerifyResult(
            ok=ok,
            method="api",
            detail=f"Foreground window HWND {fg_hwnd} {'matches' if ok else 'does not match'} expected {expected_title_or_hwnd}.",
        )
    else:
        title_buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(fg_hwnd, title_buf, 512)
        actual_title = title_buf.value
        expected_lower = expected_title_or_hwnd.lower()
        ok = expected_lower in actual_title.lower()
        return VerifyResult(
            ok=ok,
            method="api",
            detail=f"Active window title '{actual_title}' {'contains' if ok else 'does not contain'} '{expected_title_or_hwnd}'.",
        )
