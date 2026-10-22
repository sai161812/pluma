"""Narrow native one-operation elevation adapter.

Only the statically selected DNS cache flush is supported. No planner-supplied
script, path, service name or command line reaches this adapter.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import Any

from pluma.tools.base import ToolResult

DNS_FLUSH_SCRIPT = "$ErrorActionPreference='Stop'; try { Clear-DnsClientCache -ErrorAction Stop; exit 0 } catch { exit 1 }"


def dns_flush_arguments() -> list[str]:
    """Fixed PowerShell arguments for the sole supported privileged operation."""
    return ["-NoProfile", "-NonInteractive", "-Command", DNS_FLUSH_SCRIPT]


def run_dns_cache_flush(*, task_id: str, timeout_s: float, task_context: Any) -> ToolResult:
    """Run one fixed DNS cache flush through UAC and an owned child process."""
    tool = "flush_dns_cache"
    if sys.platform != "win32":
        return ToolResult.failure(tool, "One-operation elevation is available only on Windows.", "UNSUPPORTED_PLATFORM")
    if (not isinstance(task_id, str) or not task_id
            or not callable(getattr(task_context, "register_owned_resource", None))):
        return ToolResult.failure(tool, "An owned task is required for elevation.", "ELEVATION_OWNERSHIP_REQUIRED")

    token = getattr(task_context, "cancellation_token", None)
    if token is None:
        return ToolResult.failure(tool, "Task cancellation is unavailable for elevation.", "ELEVATION_CANCELLATION_UNAVAILABLE")

    job = None
    process_handle = None
    assigned = False
    launched = False
    t0 = time.perf_counter()
    try:
        token.raise_if_cancelled()
        import ctypes
        from ctypes import wintypes
        from pathlib import Path
        from pluma.core.job_object import WindowsJobObject

        system_root = os.environ.get("SystemRoot")
        if not system_root:
            return ToolResult.failure(tool, "Windows system directory is unavailable.", "ELEVATION_UNAVAILABLE")
        powershell = Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        if not powershell.is_file():
            return ToolResult.failure(tool, "Windows PowerShell is unavailable.", "ELEVATION_UNAVAILABLE")

        # This fixed script performs one operation. It contains no user data and
        # does not weaken the machine's PowerShell execution policy.
        parameters = subprocess.list2cmdline(dns_flush_arguments())

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("DUMMYUNIONNAME", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        SEE_MASK_NOCLOSEPROCESS = 0x00000040
        SEE_MASK_NOASYNC = 0x00000100
        SEE_MASK_FLAG_NO_UI = 0x00000400
        SW_HIDE = 0
        WAIT_OBJECT_0 = 0
        WAIT_TIMEOUT = 0x00000102
        ERROR_CANCELLED = 1223
        WAIT_SLICE_MS = 50

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        kernel32.GetProcessId.argtypes = [wintypes.HANDLE]
        kernel32.GetProcessId.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        # The local kill-on-close job is owned by this task worker. If STOP or
        # timeout interrupts the worker, closing its handle terminates only the
        # exact child created below.
        job = WindowsJobObject(name=None, kill_on_close=True)
        request = SHELLEXECUTEINFOW()
        request.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        request.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NOASYNC | SEE_MASK_FLAG_NO_UI
        request.lpVerb = "runas"
        request.lpFile = str(powershell)
        request.lpParameters = parameters
        request.lpDirectory = system_root
        request.nShow = SW_HIDE

        if not shell32.ShellExecuteExW(ctypes.byref(request)):
            error = ctypes.get_last_error()
            code = "ELEVATION_CANCELLED" if error == ERROR_CANCELLED else "ELEVATION_LAUNCH_FAILED"
            message = "The one-operation UAC request was cancelled." if error == ERROR_CANCELLED else "The one-operation UAC request could not be started."
            return ToolResult.failure(tool, message, code,
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")

        process_handle = request.hProcess
        launched = bool(process_handle)
        if not launched:
            return ToolResult.failure(tool, "The elevated process handle was unavailable.", "ELEVATION_HANDLE_UNAVAILABLE",
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")

        pid = int(kernel32.GetProcessId(process_handle))
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if pid <= 0 or not kernel32.GetProcessTimes(process_handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(kernel_time), ctypes.byref(user_time)):
            return ToolResult.failure(tool, "Elevated process identity could not be verified.", "ELEVATION_IDENTITY_UNAVAILABLE",
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")
        creation_time = (created.dwHighDateTime << 32) | created.dwLowDateTime

        try:
            job.assign_handle(process_handle, process_id=pid)
            assigned = True
        except Exception:
            # The process may already have exited before assignment. Otherwise
            # terminate only the process returned by ShellExecuteEx and verify
            # its exit before refusing the operation.
            if kernel32.WaitForSingleObject(process_handle, 0) != WAIT_OBJECT_0:
                kernel32.TerminateProcess(process_handle, 1)
                kernel32.WaitForSingleObject(process_handle, 1000)
                return ToolResult.failure(tool, "Elevated process containment failed; the effect may be uncertain.",
                    "ELEVATION_CONTAINMENT_FAILED", duration_ms=(time.perf_counter() - t0) * 1000.0,
                    adapter_used="one_operation_uac")

        task_context.register_owned_resource("subprocess", "PLUMA_CREATED", str(pid), metadata={
            "creation_time": creation_time,
            "command_class": "elevation_operation",
            "operation": "FLUSH_DNS",
        })

        deadline = time.monotonic() + min(max(float(timeout_s), 0.1), 30.0)
        while True:
            try:
                token.raise_if_cancelled()
            except Exception:
                if kernel32.WaitForSingleObject(process_handle, 0) != WAIT_OBJECT_0:
                    kernel32.TerminateProcess(process_handle, 1)
                    kernel32.WaitForSingleObject(process_handle, 1000)
                return ToolResult.failure(tool, "Elevation was stopped; the effect may be uncertain.",
                    "TASK_CANCELLED", duration_ms=(time.perf_counter() - t0) * 1000.0,
                    adapter_used="one_operation_uac")

            remaining_ms = int(max(0.0, deadline - time.monotonic()) * 1000.0)
            wait = kernel32.WaitForSingleObject(process_handle, min(WAIT_SLICE_MS, remaining_ms))
            if wait == WAIT_OBJECT_0:
                break
            if wait != WAIT_TIMEOUT:
                return ToolResult.failure(tool, "Elevated process exit could not be read back.", "ELEVATION_WAIT_FAILED",
                    duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")
            if remaining_ms <= 0:
                kernel32.TerminateProcess(process_handle, 1)
                kernel32.WaitForSingleObject(process_handle, 1000)
                return ToolResult.failure(tool, "The elevated operation timed out; the effect may be uncertain.",
                    "ELEVATION_TIMEOUT", duration_ms=(time.perf_counter() - t0) * 1000.0,
                    adapter_used="one_operation_uac")

        exit_code = wintypes.DWORD()
        if (not kernel32.GetExitCodeProcess(process_handle, ctypes.byref(exit_code))
                or kernel32.WaitForSingleObject(process_handle, 0) != WAIT_OBJECT_0):
            return ToolResult.failure(tool, "Elevated process completion could not be verified.", "ELEVATION_READBACK_FAILED",
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")
        if assigned and job.active_process_count() != 0:
            return ToolResult.failure(tool, "Owned elevated process cleanup could not be verified.", "ELEVATION_CLEANUP_UNVERIFIED",
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")
        if exit_code.value != 0:
            return ToolResult.failure(tool, "The DNS cache flush command reported failure.", "ELEVATED_OPERATION_FAILED",
                duration_ms=(time.perf_counter() - t0) * 1000.0, adapter_used="one_operation_uac")
        return ToolResult.success(tool,
            data={"operation": "FLUSH_DNS", "exit_code": int(exit_code.value), "process_exit_observed": True},
            factual_message="The one-operation DNS cache flush completed and its process exit was verified.",
            verified=False, duration_ms=(time.perf_counter() - t0) * 1000.0,
            adapter_used="one_operation_uac")
    except Exception:
        # If a failure occurs after process creation, the retained exact handle
        # and kill-on-close job prevent an untracked elevated child.
        if process_handle is not None:
            try:
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                if kernel32.WaitForSingleObject(process_handle, 0) != 0:
                    kernel32.TerminateProcess(process_handle, 1)
                    kernel32.WaitForSingleObject(process_handle, 1000)
            except Exception:
                pass
        return ToolResult.failure(tool, "The one-operation elevation adapter failed; the effect may be uncertain.",
            "ELEVATION_ADAPTER_FAILED", duration_ms=(time.perf_counter() - t0) * 1000.0,
            adapter_used="one_operation_uac" if launched else None)
    finally:
        if process_handle is not None:
            try:
                import ctypes
                from ctypes import wintypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(wintypes.HANDLE(process_handle))
            except Exception:
                pass
        if job is not None:
            try:
                job.close()
            except Exception:
                pass
