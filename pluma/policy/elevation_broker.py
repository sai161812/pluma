from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
import time

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from pluma.tools.base import ToolResult

logger = logging.getLogger(__name__)

DEFAULT_ELEVATION_TIMEOUT_S = 15.0

_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\. ]{1,128}$")
_SHELL_INJECTION_PATTERN = re.compile(r"[;&|`$<>]")


class ElevationOpType(str, Enum):
    """Allowlisted single-operation privilege elevation operation types."""
    RESTART_SERVICE = "RESTART_SERVICE"
    START_SERVICE = "START_SERVICE"
    STOP_SERVICE = "STOP_SERVICE"
    FLUSH_DNS = "FLUSH_DNS"
    INSTALL_MSI = "INSTALL_MSI"


class ElevationOperation(BaseModel):
    """Typed, allowlisted elevation operation schema (extra='forbid')."""
    model_config = {"extra": "forbid"}

    op_type: ElevationOpType
    service_name: Optional[str] = Field(default=None, description="Alphanumeric Windows service name.")
    package_path: Optional[str] = Field(default=None, description="Path to MSI package.")

    @field_validator("service_name")
    @classmethod
    def validate_service_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not _SAFE_IDENTIFIER_PATTERN.match(clean) or _SHELL_INJECTION_PATTERN.search(clean):
                raise ValueError(f"Invalid service name: '{v}'. Must be safe alphanumeric identifier.")
        return v

    @field_validator("package_path")
    @classmethod
    def validate_package_path(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            clean = v.strip()
            if not os.path.isabs(clean):
                raise ValueError(f"MSI package path must be an absolute path: '{v}'")
            if not clean.lower().endswith(".msi"):
                raise ValueError(f"Package path must end with .msi: '{v}'")
            if not os.path.exists(clean) and os.environ.get("PLUMA_TEST_MODE") != "1":
                raise ValueError(f"MSI package file not found at '{v}'")
        return v


class ElevationBroker:
    """Brokers single-operation elevated subprocess execution without elevating the resident core."""

    def __init__(self, timeout_s: float = DEFAULT_ELEVATION_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s

    def execute_operation(
        self,
        operation: ElevationOperation,
        timeout_s: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute a typed, allowlisted elevated operation."""
        if operation.op_type == ElevationOpType.RESTART_SERVICE:
            if not operation.service_name:
                return ToolResult.failure("elevate", "service_name is required for RESTART_SERVICE.")
            script = f"Restart-Service -Name '{operation.service_name}' -Force"
        elif operation.op_type == ElevationOpType.START_SERVICE:
            if not operation.service_name:
                return ToolResult.failure("elevate", "service_name is required for START_SERVICE.")
            script = f"Start-Service -Name '{operation.service_name}'"
        elif operation.op_type == ElevationOpType.STOP_SERVICE:
            if not operation.service_name:
                return ToolResult.failure("elevate", "service_name is required for STOP_SERVICE.")
            script = f"Stop-Service -Name '{operation.service_name}' -Force"
        elif operation.op_type == ElevationOpType.FLUSH_DNS:
            script = "Clear-DnsClientCache"
        elif operation.op_type == ElevationOpType.INSTALL_MSI:
            if not operation.package_path:
                return ToolResult.failure("elevate", "package_path is required for INSTALL_MSI.")
            script = f"$p = Start-Process msiexec.exe -ArgumentList '/i \"{operation.package_path}\" /qn' -PassThru -Wait; exit $p.ExitCode"
        else:
            return ToolResult.failure("elevate", f"Unsupported elevation operation: {operation.op_type}")

        return self._execute_elevated_script(script, timeout_s=timeout_s, task_id=task_id)

    def _execute_elevated_script(
        self,
        script: str,
        timeout_s: Optional[float] = None,
        task_id: Optional[str] = None,
    ) -> ToolResult:
        """Execute a single PowerShell script elevated via UAC ('runas') and wait for completion.

        The resident process remains unelevated. An isolated temporary subprocess is launched,
        executed to completion, and terminated.
        """

        effective_timeout = timeout_s or self.timeout_s
        logger.info(
            "Task %s: Dispatching isolated elevated operation (timeout: %.1fs)...",
            task_id or "unknown", effective_timeout,
        )

        t0 = time.perf_counter()

        if sys.platform != "win32" or os.environ.get("PLUMA_TEST_MODE") == "1":
            # Emulated mock execution for non-Windows / CI testing
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return ToolResult(
                ok=True,
                tool="elevate",
                factual_message="Elevated script executed successfully (test mode).",
                duration_ms=duration_ms,
                adapter_used="elevation_broker_mock",
            )



        try:
            import tempfile
            from pathlib import Path
            import ctypes
            from ctypes import wintypes

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("DUMMYUNIONNAME", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)
                ]

            SEE_MASK_NOCLOSEPROCESS = 0x00000040
            SEE_MASK_FLAG_NO_UI = 0x00000400
            SW_HIDE = 0

            shell32 = ctypes.WinDLL("shell32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            temp_fd, temp_path = tempfile.mkstemp(suffix=".ps1", prefix="pluma_elev_")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(script)

                sei = SHELLEXECUTEINFOW()
                sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
                sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
                sei.lpVerb = "runas"
                sei.lpFile = "powershell.exe"
                sei.lpParameters = f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"{temp_path}\""
                sei.nShow = SW_HIDE

                if not shell32.ShellExecuteExW(ctypes.byref(sei)):
                    err = ctypes.get_last_error()
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    return ToolResult.failure(
                        tool="elevate",
                        error=f"ShellExecuteExW failed with error {err}",
                        duration_ms=duration_ms,
                        adapter_used="elevation_broker",
                    )

                hProcess = sei.hProcess
                if hProcess:
                    # Wait for process
                    timeout_ms = int(effective_timeout * 1000)
                    WAIT_TIMEOUT = 0x00000102
                    res = kernel32.WaitForSingleObject(hProcess, timeout_ms)
                    if res == WAIT_TIMEOUT:
                        kernel32.TerminateProcess(hProcess, 1)
                        kernel32.CloseHandle(hProcess)
                        duration_ms = (time.perf_counter() - t0) * 1000.0
                        return ToolResult.failure(
                            tool="elevate",
                            error=f"Elevated operation timed out after {effective_timeout:.1f}s.",
                            duration_ms=duration_ms,
                            adapter_used="elevation_broker",
                        )
                    
                    exit_code = wintypes.DWORD()
                    kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                    kernel32.CloseHandle(hProcess)

                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if exit_code.value != 0:
                        return ToolResult.failure(
                            tool="elevate",
                            error=f"Elevated execution failed with exit code {exit_code.value}",
                            duration_ms=duration_ms,
                            adapter_used="elevation_broker",
                        )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    ok=True,
                    tool="elevate",
                    factual_message="Single-operation elevated command executed successfully.",
                    duration_ms=duration_ms,
                    adapter_used="elevation_broker",
                )
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass

        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Elevation broker failed: %s", exc)
            return ToolResult.failure(
                tool="elevate",
                error=f"Elevation broker error: {exc}",
                duration_ms=duration_ms,
                adapter_used="elevation_broker",
            )
