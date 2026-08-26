"""pluma.core.job_object — Windows Job Object wrapper for process containment.

Spec §12.1: "Use a Windows Job Object for task-spawned subprocesses and set
kill-on-job-close behavior where appropriate. This gives a hard boundary for
PLUMA-owned descendants even if a worker tries to spawn children."
"""

from __future__ import annotations

import logging
import subprocess
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Only define Win32 APIs if on Windows.
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    # Constants
    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    PROCESS_ALL_ACCESS = 0x1FFFFF

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]

    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        wintypes.LPVOID,
        wintypes.DWORD,
    ]

    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]

    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


class JobObjectError(Exception):
    """Raised when a Job Object operation fails."""
    pass


class WindowsJobObject:
    """A safe wrapper around a Win32 Job Object.

    Ensures that any processes assigned to the job (and their children)
    are terminated when the job object handle is closed, or when explicitly
    terminated.
    """

    def __init__(self, name: Optional[str] = None, kill_on_close: bool = True) -> None:
        self._handle: Any = None
        self._kill_on_close = kill_on_close
        if sys.platform != "win32":
            logger.warning("WindowsJobObject is a no-op on non-Windows platforms.")
            return

        h_job = kernel32.CreateJobObjectW(None, name)
        if not h_job:
            err = ctypes.get_last_error()
            raise JobObjectError(f"CreateJobObjectW failed with error code {err}")
        self._handle = h_job

        if kill_on_close:
            # Configure KILL_ON_JOB_CLOSE
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            
            result = kernel32.SetInformationJobObject(
                self._handle,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            if not result:
                err = ctypes.get_last_error()
                self.close()
                raise JobObjectError(f"SetInformationJobObject failed with error {err}")

    def assign_process(self, pid_or_popen: int | subprocess.Popen) -> None:
        """Assign a process to this Job Object.

        Args:
            pid_or_popen: The process ID or a subprocess.Popen instance.
        """
        if self._handle is None:
            return

        if hasattr(pid_or_popen, "pid"):
            pid = pid_or_popen.pid
        else:
            pid = int(pid_or_popen)  # type: ignore[arg-type]

        h_process = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not h_process:
            err = ctypes.get_last_error()
            raise JobObjectError(f"OpenProcess failed for PID {pid} with error {err}")

        try:
            result = kernel32.AssignProcessToJobObject(self._handle, h_process)
            if not result:
                err = ctypes.get_last_error()
                raise JobObjectError(
                    f"AssignProcessToJobObject failed for PID {pid} with error {err}"
                )
        finally:
            kernel32.CloseHandle(h_process)

    def terminate(self, exit_code: int = 1) -> None:
        """Terminate all processes in the job object immediately."""
        if self._handle is None:
            return
            
        result = kernel32.TerminateJobObject(self._handle, exit_code)
        if not result:
            err = ctypes.get_last_error()
            logger.debug("TerminateJobObject returned false (error %s)", err)

    def close(self) -> None:
        """Close the Job Object handle.
        
        Since KILL_ON_JOB_CLOSE is set, this will also terminate any assigned
        processes that are still running.
        """
        if self._handle is not None:
            kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self) -> "WindowsJobObject":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
