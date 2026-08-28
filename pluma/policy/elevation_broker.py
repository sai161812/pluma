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
            script = f"Start-Process msiexec.exe -ArgumentList '/i \"{operation.package_path}\" /qn' -Wait"
        else:
            return ToolResult.failure("elevate", f"Unsupported elevation operation: {operation.op_type}")

        return self.execute_elevated_script(script, timeout_s=timeout_s, task_id=task_id)

    def execute_elevated_script(
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


            # Write script to temporary .ps1 file to eliminate command-line injection
            temp_fd, temp_path = tempfile.mkstemp(suffix=".ps1", prefix="pluma_elev_")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(script)

                cmd = [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy", "Bypass",
                    "-Command",
                    f"Start-Process powershell.exe -ArgumentList '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"{temp_path}\"' -Verb RunAs -Wait",
                ]

                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )

                try:
                    stdout, stderr = proc.communicate(timeout=effective_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    return ToolResult.failure(
                        tool="elevate",
                        error=f"Elevated operation timed out after {effective_timeout:.1f}s.",
                        duration_ms=duration_ms,
                        adapter_used="elevation_broker",
                    )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                if proc.returncode != 0:
                    err_msg = stderr.strip() or stdout.strip() or f"Process returned exit code {proc.returncode}"
                    return ToolResult.failure(
                        tool="elevate",
                        error=f"Elevated execution failed: {err_msg}",
                        duration_ms=duration_ms,
                        adapter_used="elevation_broker",
                    )

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
