"""P11 elevation failure paths and real owned-child/read-only native checks.

No test in this file opens UAC or mutates the machine's DNS/power state.
"""
from types import SimpleNamespace
import subprocess
import sys

import pytest

from pluma.adapters import elevation
from pluma.core.cancellation import CancellationToken
from pluma.tools.base import ToolResult
from pluma.tools.system import verify_flush_dns_cache


class Context:
    task_id = "p11-elevation-regression"

    def __init__(self):
        self.cancellation_token = CancellationToken()
        self.resources = []

    def register_owned_resource(self, *args, **kwargs):
        self.resources.append((args, kwargs))


class NativeFixture:
    def __init__(self, stage=None):
        self.stage = stage
        self.events = []
        self.closed = False
        self.job = SimpleNamespace(active_process_count=lambda: 0)

    def launch(self):
        self.events.append("launch")
        if self.stage == "launch":
            raise RuntimeError("Injected launch failure")

    def identity(self):
        self.events.append("identity")
        if self.stage == "identity":
            raise RuntimeError("Injected identity lookup failure")
        return 123, 456

    def contain(self, pid):
        self.events.append("contain")
        if self.stage == "contain":
            raise RuntimeError("Injected containment failure")

    def admit(self):
        self.events.append("admit")

    def exited(self, timeout_ms=0):
        self.events.append("exit_read")
        return True

    def exit_code(self):
        return 0

    def close(self):
        self.closed = True
        return self.stage != "cleanup"


@pytest.mark.parametrize("stage", ["launch", "identity", "contain", "registration"])
def test_every_pre_admission_failure_closes_child_without_releasing_gate(monkeypatch, stage):
    native = NativeFixture(stage)
    monkeypatch.setattr(elevation, "_WindowsElevation", lambda: native)
    monkeypatch.setattr(elevation, "read_dns_cache", lambda *args: pytest.fail("No readback before admission"))
    context = Context()
    if stage == "registration":
        def denied(*args, **kwargs):
            raise RuntimeError("Injected registry failure")
        context.register_owned_resource = denied
    result = elevation.run_dns_cache_flush(task_id=context.task_id, timeout_s=10, task_context=context)
    assert not result.ok and native.closed
    assert "admit" not in native.events


@pytest.mark.parametrize("readback", [0, 1, None])
def test_success_requires_independent_empty_cache_observation(monkeypatch, readback):
    native = NativeFixture()
    context = Context()
    monkeypatch.setattr(elevation, "_WindowsElevation", lambda: native)

    def read(ctx, timeout):
        assert ctx is context and timeout > 0
        assert len(context.resources) == 1
        assert context.resources[0][0][3]["lifetime"] == "task"
        assert native.events[:4] == ["launch", "identity", "contain", "admit"]
        if readback is None:
            raise RuntimeError("Readback unavailable")
        return {"cache_entry_count": readback, "cache_readback_observed": True}

    monkeypatch.setattr(elevation, "read_dns_cache", read)
    result = elevation.run_dns_cache_flush(task_id=context.task_id, timeout_s=10, task_context=context)
    assert native.closed
    assert result.ok is (readback == 0)
    assert verify_flush_dns_cache(result).ok is (readback == 0)
    if readback == 1:
        assert result.error_code == "DNS_CACHE_NOT_EMPTY"


def test_stop_after_registration_never_releases_admission_gate(monkeypatch):
    native = NativeFixture()
    context = Context()
    monkeypatch.setattr(elevation, "_WindowsElevation", lambda: native)
    def register(*args, **kwargs):
        context.cancellation_token.cancel()
    context.register_owned_resource = register
    result = elevation.run_dns_cache_flush(task_id=context.task_id, timeout_s=10, task_context=context)
    assert not result.ok and native.closed and "admit" not in native.events


def test_unverified_cleanup_overrides_success(monkeypatch):
    native = NativeFixture("cleanup")
    context = Context()
    monkeypatch.setattr(elevation, "_WindowsElevation", lambda: native)
    monkeypatch.setattr(elevation, "read_dns_cache", lambda *args:
        {"cache_entry_count": 0, "cache_readback_observed": True})
    result = elevation.run_dns_cache_flush(task_id=context.task_id, timeout_s=10, task_context=context)
    assert not result.ok and result.error_code == "ELEVATION_CLEANUP_UNVERIFIED"


@pytest.mark.parametrize("data", [
    {"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True},
    {"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True,
        "cache_entry_count": 3, "cache_readback_observed": True},
    {"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True,
        "cache_entry_count": False, "cache_readback_observed": True},
])
def test_exit_only_populated_or_malformed_receipts_never_verify(data):
    result = ToolResult.success("flush_dns_cache", data=data,
        adapter_used="one_operation_uac", factual_message="Injected receipt.")
    assert not verify_flush_dns_cache(result).ok


def test_real_uncontained_owned_child_is_terminated_when_identity_lookup_fails(monkeypatch):
    """Reproduce the former early-return hole using a real, non-elevated child."""
    import win32api
    import win32con
    processes = []
    original = elevation._WindowsElevation

    class FailedIdentity(original):
        def launch(self):
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append(child)
            current = win32api.GetCurrentProcess()
            self.process = win32api.DuplicateHandle(current, int(child._handle),
                current, 0, False, win32con.DUPLICATE_SAME_ACCESS)

        def identity(self):
            raise RuntimeError("Injected GetProcessTimes failure after a real launch")

    monkeypatch.setattr(elevation, "_WindowsElevation", FailedIdentity)
    context = Context()
    try:
        result = elevation.run_dns_cache_flush(task_id=context.task_id, timeout_s=10, task_context=context)
        assert not result.ok and not context.resources
        assert len(processes) == 1
        assert processes[0].wait(timeout=2) is not None
    finally:
        for child in processes:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)


def test_native_dns_reader_observes_count_and_drains_owned_process():
    """Actual read-only Get-DnsClientCache; never a flush."""
    context = Context()
    result = elevation.read_dns_cache(context, 8)
    assert type(result["cache_entry_count"]) is int and result["cache_entry_count"] >= 0
    assert result["cache_readback_observed"] is True
    assert len(context.resources) == 1
    args, kwargs = context.resources[0]
    assert args[0] == "subprocess"
    metadata = args[3]
    assert metadata["task_id"] == context.task_id and metadata["creation_time"] > 0


@pytest.mark.parametrize("stdout,exit_code,tree_empty", [
    ("cached.private.example", 0, True), ("0", 1, True), ("0", 0, False), ("", 0, True),
])
def test_dns_reader_rejects_unreadable_or_failed_command(monkeypatch, stdout, exit_code, tree_empty):
    from pluma.adapters import commands
    monkeypatch.setattr(commands, "run", lambda *args: (
        {"exit_code": exit_code, "command_output": {"stdout": stdout, "stderr": ""}},
        {"exit_readback": exit_code, "tree_empty": tree_empty}))
    with pytest.raises(ValueError):
        elevation.read_dns_cache(Context(), 8)


def test_native_admission_event_is_closed_until_parent_releases_it():
    from pluma.adapters.commands import run, windows_directory
    native = elevation._WindowsElevation()
    system = windows_directory() / "System32"
    script = ("$g=[Threading.EventWaitHandle]::OpenExisting('" + native.gate_name
        + "',[Security.AccessControl.EventWaitHandleRights]::Synchronize); "
        "try { [Console]::Out.Write($g.WaitOne(0)) } finally { $g.Close() }")
    binding = {"command_id": "admission_event_probe", "argv": [
        str(system / "WindowsPowerShell/v1.0/powershell.exe"),
        "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
        "cwd": str(system), "timeout_s": 8, "read_only": True, "encoding": "utf-8"}
    try:
        before, proof = run(binding, Context())
        assert before["exit_code"] == 0 and proof["tree_empty"]
        assert before["command_output"]["stdout"] == "False"
        native.admit()
        after, proof = run(binding, Context())
        assert after["exit_code"] == 0 and proof["tree_empty"]
        assert after["command_output"]["stdout"] == "True"
    finally:
        assert native.close()
