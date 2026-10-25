"""Fixed one-operation UAC with pre-dispatch ownership and independent DNS readback."""
from __future__ import annotations

import re
import subprocess
import sys
import time
import uuid
from types import SimpleNamespace
from typing import Any

from pluma.tools.base import ToolResult

DNS_FLUSH_SCRIPT = (
    "Import-Module (Join-Path $PSHOME 'Modules\\DnsClient\\DnsClient.psd1') -ErrorAction Stop; "
    "DnsClient\\Clear-DnsClientCache -ErrorAction Stop"
)
DNS_READ_SCRIPT = (
    "$ErrorActionPreference='Stop'; "
    "Import-Module (Join-Path $PSHOME 'Modules\\DnsClient\\DnsClient.psd1') -ErrorAction Stop; "
    "$count=@(DnsClient\\Get-DnsClientCache -ErrorAction Stop).Count; "
    "[Console]::Out.Write($count)"
)


def dns_flush_arguments(gate_name: str) -> list[str]:
    """The only variable is an executor-created event name, never planner data."""
    if not re.fullmatch(r"Local\\PLUMA-DNS-[0-9a-f]{32}", gate_name):
        raise ValueError("Invalid elevation admission event.")
    script = (
        "$ErrorActionPreference='Stop'; try { "
        "$gate=[Threading.EventWaitHandle]::OpenExisting('" + gate_name + "',"
        "[Security.AccessControl.EventWaitHandleRights]::Synchronize); "
        "try { if (-not $gate.WaitOne(15000)) { exit 2 } } finally { $gate.Close() }; "
        + DNS_FLUSH_SCRIPT + "; exit 0 } catch { exit 1 }"
    )
    return ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script]


class _WindowsElevation:
    """Retain the exact launch handle even if PID/creation-time lookup fails."""

    def __init__(self):
        import win32api
        import win32event
        from pluma.core.job_object import WindowsJobObject
        self.process = None
        self.job = None
        self.gate = None
        self.gate_name = "Local\\PLUMA-DNS-" + uuid.uuid4().hex
        try:
            self.job = WindowsJobObject(kill_on_close=True)
            self.gate = win32event.CreateEvent(None, True, False, self.gate_name)
            if win32api.GetLastError() == 183:
                raise RuntimeError("Elevation admission event already exists.")
        except Exception:
            self.close()
            raise

    def launch(self):
        import pythoncom
        from win32com.shell import shell
        from pluma.adapters.commands import windows_directory
        windows = windows_directory()
        powershell = windows / "System32/WindowsPowerShell/v1.0/powershell.exe"
        # NOASYNC keeps ShellExecute in this owned, killable worker. A child
        # created after STOP cannot mutate: its admission event is never set.
        pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)
        try:
            receipt = shell.ShellExecuteEx(
                fMask=0x40 | 0x100 | 0x400, lpVerb="runas", lpFile=str(powershell),
                lpParameters=subprocess.list2cmdline(dns_flush_arguments(self.gate_name)),
                lpDirectory=str(windows), nShow=0,
            )
        finally:
            pythoncom.CoUninitialize()
        self.process = receipt.get("hProcess")
        if self.process is None:
            raise RuntimeError("The elevated child handle is unavailable.")

    def identity(self):
        import win32process
        from pluma.core.job_object import owned_process_creation_time
        pid = win32process.GetProcessId(self.process)
        created = owned_process_creation_time(SimpleNamespace(sentinel=int(self.process)))
        if pid <= 0 or created <= 0:
            raise RuntimeError("The elevated child identity is unavailable.")
        return pid, created

    def contain(self, pid):
        self.job.assign_handle(int(self.process), process_id=pid)

    def admit(self):
        import win32event
        win32event.SetEvent(self.gate)

    def exited(self, timeout_ms=0):
        import win32event
        status = win32event.WaitForSingleObject(self.process, timeout_ms)
        if status not in (0, 258):
            raise RuntimeError("The elevated child wait failed.")
        return status == 0

    def exit_code(self):
        import win32process
        if not self.exited():
            raise RuntimeError("The elevated child has not exited.")
        return win32process.GetExitCodeProcess(self.process)

    def close(self):
        """Every path terminates/waits through the retained handle before release."""
        import win32api
        verified = True
        if self.process is not None:
            try:
                if not self.exited():
                    win32api.TerminateProcess(self.process, 1)
            except Exception:
                # Job close provides a second containment boundary.
                pass
        if self.job is not None:
            try:
                self.job.close()
            except Exception:
                verified = False
        if self.process is not None:
            try:
                verified = self.exited(1000) and verified
            except Exception:
                verified = False
            finally:
                self.process.Close()
                self.process = None
        if self.gate is not None:
            self.gate.Close()
            self.gate = None
        return verified


def read_dns_cache(task_context, timeout_s):
    """Read only the count through the existing owned suspended-command adapter."""
    from pluma.adapters.commands import run, windows_directory
    if timeout_s <= 0:
        raise TimeoutError("DNS readback exhausted the tool deadline.")
    system = windows_directory() / "System32"
    binding = {
        "command_id": "dns_cache_readback",
        "argv": [str(system / "WindowsPowerShell/v1.0/powershell.exe"),
            "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", DNS_READ_SCRIPT],
        "cwd": str(system), "timeout_s": min(timeout_s, 8.0),
        "read_only": True, "encoding": "utf-8",
    }
    observed, proof = run(binding, task_context)
    output = observed["command_output"]
    raw = output["stdout"].strip()
    if (observed["exit_code"] != 0 or proof["exit_readback"] != 0
            or proof["tree_empty"] is not True or output["stderr"].strip()
            or not re.fullmatch(r"[0-9]{1,10}", raw)):
        raise ValueError("DNS cache readback was unavailable or malformed.")
    return {"cache_entry_count": int(raw), "cache_readback_observed": True}


def run_dns_cache_flush(*, task_id: str, timeout_s: float, task_context: Any) -> ToolResult:
    tool = "flush_dns_cache"
    if sys.platform != "win32":
        return ToolResult.failure(tool, "One-operation elevation requires Windows.", "UNSUPPORTED_PLATFORM")
    token = getattr(task_context, "cancellation_token", None)
    if (not task_id or getattr(task_context, "task_id", None) != task_id or token is None
            or not callable(getattr(task_context, "register_owned_resource", None))):
        return ToolResult.failure(tool, "An owned cancellable task is required.", "ELEVATION_OWNERSHIP_REQUIRED")
    native = None
    start = time.monotonic()
    deadline = start + min(max(float(timeout_s), .1), 30.0)
    try:
        token.raise_if_cancelled()
        native = _WindowsElevation()
        token.raise_if_cancelled()
        native.launch()
        pid, created = native.identity()
        native.contain(pid)
        task_context.register_owned_resource("subprocess", "PLUMA_CREATED", str(pid), {
            "task_id": task_id, "pid": pid, "creation_time": created,
            "command_class": "elevation_operation", "operation": "FLUSH_DNS",
            "lifetime": "task",
        })
        token.raise_if_cancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError("Elevation admission exceeded its deadline.")
        native.admit()
        while not native.exited(50) or native.job.active_process_count() != 0:
            token.raise_if_cancelled()
            if time.monotonic() >= deadline:
                raise TimeoutError("Elevation exceeded its deadline.")
        if native.exit_code() != 0 or native.job.active_process_count() != 0:
            return ToolResult.failure(tool, "The elevated operation or child cleanup failed.",
                "ELEVATED_OPERATION_FAILED", adapter_used="one_operation_uac")
        token.raise_if_cancelled()
        readback = read_dns_cache(task_context, deadline - time.monotonic())
        if readback["cache_entry_count"] != 0:
            return ToolResult.failure(tool,
                "The DNS cache was still populated at readback; the flush effect is unverified.",
                "DNS_CACHE_NOT_EMPTY", adapter_used="one_operation_uac").model_copy(update={"data": readback})
        return ToolResult.success(tool, data={
            "operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True,
            **readback,
        }, factual_message="Flushed the DNS cache and independently observed an empty cache.",
            verified=False, adapter_used="one_operation_uac",
            duration_ms=(time.monotonic() - start) * 1000)
    except Exception:
        return ToolResult.failure(tool,
            "The one-operation elevation or DNS readback failed; effects may be uncertain.",
            "ELEVATION_OPERATION_FAILED", adapter_used="one_operation_uac")
    finally:
        # A return before identity/containment/registration is not an exception.
        # Cleanup belongs here so such returns and all raised failures are covered.
        if native is not None:
            try:
                clean = native.close()
            except Exception:
                clean = False
            if not clean:
                return ToolResult.failure(tool,
                    "Elevated child termination could not be verified.",
                    "ELEVATION_CLEANUP_UNVERIFIED", adapter_used="one_operation_uac")
