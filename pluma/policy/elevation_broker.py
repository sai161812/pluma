"""pluma.policy.elevation_broker — Single-operation privilege elevation broker.

Spec §15:
- "The PLUMA resident core process NEVER runs elevated."
- "Any action requiring elevation is brokered as an isolated, single-operation
   out-of-process execution through ElevationBroker and immediately dropped."
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

from pluma.tools.base import ToolResult

logger = logging.getLogger(__name__)

DEFAULT_ELEVATION_TIMEOUT_S = 15.0


class ElevationBroker:
    """Brokers single-operation elevated subprocess execution without elevating the resident core."""

    def __init__(self, timeout_s: float = DEFAULT_ELEVATION_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s

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

        if sys.platform != "win32":
            # Emulated mock execution for non-Windows / CI testing
            duration_ms = (time.perf_counter() - t0) * 1000.0
            return ToolResult(
                ok=True,
                tool="elevate",
                factual_message=f"Elevated script executed successfully (non-Windows mock).",
                duration_ms=duration_ms,
                adapter_used="elevation_broker_mock",
            )

        try:
            # Launch elevated powershell runner with hidden window and RunAs verb
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy", "Bypass",
                "-Command",
                f"Start-Process powershell.exe -ArgumentList '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"{script}\"' -Verb RunAs -Wait",
            ]

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
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

        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Elevation broker failed: %s", exc)
            return ToolResult.failure(
                tool="elevate",
                error=f"Elevation broker error: {exc}",
                duration_ms=duration_ms,
                adapter_used="elevation_broker",
            )
