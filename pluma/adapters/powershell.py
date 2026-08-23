"""pluma.adapters.powershell — Controlled PowerShell execution adapter.

Spec §13, §14: Provides bounded, timeout-guarded, Job-Object-isolated
PowerShell execution. Natural language is never passed directly to shell;
only typed/sanitized commands.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import subprocess
import time
from typing import Any, Dict, List, Optional

from pluma.adapters.base import (
    AccessDeniedError,
    AdapterError,
    AdapterTimeoutError,
)
from pluma.core.cancellation import CancellationToken
from pluma.core.job_object import WindowsJobObject

logger = logging.getLogger(__name__)

# Execution limits
DEFAULT_TIMEOUT_S = 5.0
MAX_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class PowerShellResult:
    """Outcome of a controlled PowerShell invocation."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool = False


class PowerShellAdapter:
    """Adapter for executing bounded, controlled PowerShell scripts and commands."""

    def __init__(self, job_object: Optional[WindowsJobObject] = None) -> None:
        self._job_object = job_object

    def run(
        self,
        script: str,
        *,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        token: Optional[CancellationToken] = None,
        job_object: Optional[WindowsJobObject] = None,
    ) -> PowerShellResult:
        """Run a PowerShell script with hard timeout and process containment.

        Args:
            script: The PowerShell script/command string to run.
            timeout_s: Timeout in seconds (clamped to MAX_TIMEOUT_S).
            token: Optional cancellation token to abort before or during execution.
            job_object: Optional Job Object to attach the subprocess to.

        Returns:
            PowerShellResult with stdout, stderr, exit_code, duration_ms.

        Raises:
            AdapterTimeoutError: If execution exceeds timeout_s.
            AccessDeniedError: If execution fails due to permissions/elevation.
            AdapterError: If PowerShell process fails to launch.
        """
        if token and token.is_cancelled:
            raise AdapterError("PowerShell execution aborted: cancellation requested")

        effective_timeout = min(max(0.1, timeout_s), MAX_TIMEOUT_S)
        job = job_object or self._job_object

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ]

        t0 = time.perf_counter()
        proc: Optional[subprocess.Popen[str]] = None

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # Assign to Job Object for deterministic containment
            if job and proc.pid:
                try:
                    job.assign_process(proc.pid)
                except Exception as exc:
                    logger.debug("Failed to assign pid %d to JobObject: %s", proc.pid, exc)

            stdout, stderr = proc.communicate(timeout=effective_timeout)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            exit_code = proc.returncode

            # Check for access denied in output or exit code
            if exit_code != 0:
                err_lower = stderr.lower() + stdout.lower()
                if "access is denied" in err_lower or "unauthorizedaccessexception" in err_lower:
                    raise AccessDeniedError(
                        f"PowerShell command denied permissions: {stderr.strip() or stdout.strip()}"
                    )

            return PowerShellResult(
                stdout=stdout.strip(),
                stderr=stderr.strip(),
                exit_code=exit_code,
                duration_ms=duration_ms,
                timed_out=False,
            )

        except subprocess.TimeoutExpired:
            if proc:
                try:
                    proc.kill()
                    proc.communicate(timeout=1.0)
                except Exception:
                    pass
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("PowerShell command timed out after %.2fs: %s", effective_timeout, script[:60])
            raise AdapterTimeoutError(
                f"PowerShell command timed out after {effective_timeout:.1f}s"
            )

        except (AccessDeniedError, AdapterTimeoutError):
            raise

        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("PowerShell invocation failed: %s", exc)
            raise AdapterError(f"PowerShell execution failed: {exc}")
