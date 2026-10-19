"""Bounded pre-action-wiring audit. No production fixes or user-resource actions.

Strict xfails assert required behavior for reproduced defects, not acceptance.
Use --runxfail to obtain the actual failing assertions. Unexpected setup errors
remain failures; resolving a defect produces XPASS until its marker is removed.
"""

from __future__ import annotations

import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import BaseModel

from pluma.app import PlumaApplicationRuntime
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.config.paths import PlumaPaths
from pluma.core import ipc, task_supervisor
from pluma.core.cancellation import TaskCancelledError
from pluma.core.orchestrator import Orchestrator
from pluma.core.resident import ResidentCore
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import TaskWorkerController, ToolRegistry, WorkerRequest


class FakeJob:
    def __init__(self, **kwargs):
        self.closed = False

    def terminate(self, **kwargs):
        pass

    def close(self):
        self.closed = True

    def active_process_count(self):
        return 0  # inert fixture owns no operating-system process

    @property
    def is_closed(self):
        return self.closed


class EmptyArgs(BaseModel):
    pass


@pytest.fixture
def isolated_supervisor(monkeypatch, tmp_path):
    """No OS jobs, production paths, credentials, microphone or hotkeys."""
    monkeypatch.setattr("pluma.core.job_object.WindowsJobObject", FakeJob)
    paths = PlumaPaths(tmp_path / "local", tmp_path / "roaming")
    monkeypatch.setattr("pluma.config.paths.get_paths", lambda: paths)
    supervisor = TaskSupervisor(paths=paths)
    yield supervisor
    for capsule in list(supervisor._tasks.values()):
        capsule.close_resources()


def bare_resident(supervisor):
    # Constructor intentionally skipped: it loads/creates a production IPC key.
    core = object.__new__(ResidentCore)
    core.supervisor = supervisor
    core._running = False
    core._hotkey_thread = None
    core.voice_enabled = False
    core.voice_activation = None
    core.voice_pipeline = None
    core.audio_capture = None
    core.ipc = SimpleNamespace(start=lambda: None, stop=lambda: None)
    return core


def probe_spec(executor, undo_builder=None, verifier=None):
    return ToolSpec(
        name="audit_probe", description="An audit-only counter, with no OS effects.",
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=1,
        executor=executor, undo_builder=undo_builder,
        verifier=verifier or (lambda result: VerifyResult(ok=True, method="state", detail="Counter observed.")),
    )


def test_global_stop_latches_every_task_before_first_grace(isolated_supervisor, monkeypatch):
    supervisor = isolated_supervisor
    capsules = [supervisor.create_task(str(i)) for i in range(2)]
    at_grace = []
    monkeypatch.setattr(task_supervisor, "time", SimpleNamespace(
        sleep=lambda seconds: at_grace.append(tuple(c.stop_latch_set for c in capsules))))
    supervisor.stop_all_active_tasks()
    assert at_grace and all(at_grace[0]), f"First cleanup grace observed stop latches {at_grace}"


def test_worker_stop_interrupts_outstanding_response_wait():
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    errors = []

    class Connection:
        def send(self, value): pass
        def close(self): pass
        def poll(self, timeout):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Audit owner did not release its fixture")
            return False

    controller = TaskWorkerController("audit-owned-controller")
    exited = threading.Event()
    controller._proc = SimpleNamespace(pid=1, exitcode=0, is_alive=lambda: not exited.is_set(),
                                       kill=exited.set, join=lambda **kw: None)
    controller._conn = Connection()

    def execute():
        try: controller.execute_call(lambda args: None, {}, WorkerRequest(
            task_id="audit-owned-controller", tool_name="audit_probe", validated_args={}, timeout_s=2), timeout_s=2)
        except Exception as exc: errors.append(type(exc).__name__)

    def stop():
        try: controller.terminate_and_join()
        except Exception as exc: errors.append(type(exc).__name__)
        finally: stopped.set()

    executing = threading.Thread(target=execute, name="audit-owned-execute")
    stopping = threading.Thread(target=stop, name="audit-owned-stop")
    executing.start()
    try:
        if not entered.wait(1): raise RuntimeError("Fixture did not enter response wait")
        stopping.start()
        interrupted = stopped.wait(0.15)
    finally:
        release.set()
        executing.join(4)
        if stopping.ident is not None: stopping.join(4)
        controller.terminate_and_join()
    if errors or executing.is_alive() or stopping.is_alive():
        raise RuntimeError(f"Fixture cleanup failed: {errors}")
    assert interrupted, "STOP could not acquire the controller until the outstanding response wait ended"


def test_stop_during_prestate_prevents_executor_start(isolated_supervisor):
    capsule = isolated_supervisor.create_task("audit-prestate")
    calls = []

    def capture(args):
        capsule.cancellation_token.cancel()
        return {"action": "audit_only"}

    def execute(args):
        calls.append(capsule.stop_latch_set)
        return ToolResult.success("audit_probe", factual_message="Counter observed.")

    registry = ToolRegistry()
    registry.register(probe_spec(execute, undo_builder=capture))
    try:
        try: registry.execute("audit_probe", {}, capsule)
        except TaskCancelledError: pass
    finally:
        registry.close()
    assert not calls, f"Executor started after the latch was set: {calls}"


def test_failed_worker_cleanup_requires_residual_state(isolated_supervisor):
    capsule = isolated_supervisor.create_task("audit-cleanup-failure")
    worker = Mock()
    worker.terminate_and_join.side_effect = RuntimeError("Owned fixture termination failed")
    capsule.worker_controller = worker
    isolated_supervisor.stop_task(capsule.task_id, grace_s=0)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL, (
        f"Cleanup failure became {capsule.state.value}; worker reference retained: {capsule.worker_controller is worker}")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-05: FAST result overwrites STOPPED_WITH_RESIDUAL with STOPPED")
def test_fast_stop_preserves_supervisor_residual_outcome(isolated_supervisor, monkeypatch):
    from pluma.core.request import InputMode, PlumaRequest
    from pluma.core.router import RouteResult
    from pluma.memory.activity import ActivityLedger, ActivityQuery
    from pluma.memory.db import DbConnection

    supervisor = isolated_supervisor
    monkeypatch.setattr(task_supervisor, "time", SimpleNamespace(sleep=lambda seconds: None))
    request = PlumaRequest(input_mode=InputMode.TEXT, text="audit-only counter")
    capsule = supervisor.create_task(request.request_id)
    capsule.undo_stack.append({"non_undoable": True, "action": "audit_external_commit"})

    def execute(args):
        capsule.cancellation_token.cancel()
        return ToolResult.failure("audit_probe", "Audit fixture requested STOP")

    registry = ToolRegistry()
    registry.register(probe_spec(execute))
    plan = Plan(task_id=capsule.task_id, route=RouteMode.FAST,
                steps=[ToolCall(tool="audit_probe", arguments={}, purpose="Audit only")])
    route = RouteResult(route=RouteMode.FAST, reason="Audit fixture", plan=plan)
    db = DbConnection(":memory:")
    db.open()
    ledger = ActivityLedger(db)
    supervisor._ledger = ledger
    orchestrator = Orchestrator(registry=registry, supervisor=supervisor, ledger=ledger,
                                router=SimpleNamespace(route=lambda req: route))
    try:
        result = orchestrator.execute(request, capsule=capsule)
        stored = ActivityQuery(db).task_by_id(capsule.task_id)["final_state"]
    finally:
        registry.close()
        db.close()
    assert result.final_state == stored == capsule.state.value, (
        f"Supervisor {capsule.state.value}; returned {result.final_state}; ledger {stored}")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-06: runtime close does not stop active capsules or close the tool registry")
def test_runtime_close_drains_active_task_and_registry(isolated_supervisor):
    capsule = isolated_supervisor.create_task("audit-runtime-close")
    isolated_supervisor.start_task(capsule.task_id)
    worker = Mock()
    capsule.worker_controller = worker
    job = capsule.job_object
    runtime = object.__new__(PlumaApplicationRuntime)
    runtime.supervisor = isolated_supervisor
    runtime.resident_core = bare_resident(isolated_supervisor)
    runtime.llm_lifecycle = Mock()
    runtime.voice_lifecycle = Mock()
    runtime.tool_registry = Mock()
    runtime.db = Mock()
    runtime.close()
    assert capsule.stop_latch_set and job.closed and worker.terminate_and_join.called and runtime.tool_registry.close.called, (
        f"state={capsule.state.value}; latch={capsule.stop_latch_set}; job closed={job.closed}; "
        f"worker drained={worker.terminate_and_join.called}; registry closed={runtime.tool_registry.close.called}")


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-07: STOP does not stop microphone capture until key release")
def test_voice_stop_closes_capture_without_key_release(isolated_supervisor):
    core = bare_resident(isolated_supervisor)
    capture = SimpleNamespace(recording=False)
    capture.start = lambda: setattr(capture, "recording", True)
    capture.stop_and_get = lambda: (setattr(capture, "recording", False) or b"")
    core.audio_capture = capture
    core._on_voice_press()
    isolated_supervisor.stop_task(core._current_voice_capsule.task_id, grace_s=0)
    still_recording = capture.recording
    capture.stop_and_get()  # owner cleanup; no real device was opened
    assert not still_recording, "Task reached STOPPED while its capture remained recording"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-07: empty voice capture leaves a CREATED capsule active")
def test_empty_voice_capture_finalizes_its_capsule(isolated_supervisor):
    core = bare_resident(isolated_supervisor)
    core.audio_capture = SimpleNamespace(start=lambda: None, stop_and_get=lambda: b"")
    core.voice_pipeline = SimpleNamespace(process_audio=lambda *a, **kw: None)
    core._on_voice_press()
    capsule = core._current_voice_capsule
    core._on_voice_release()
    assert capsule not in isolated_supervisor.get_active_tasks(), f"Empty capture left {capsule.state.value} active"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-08: stop_all IPC reports success without checking final task state")
def test_ipc_stop_reply_distinguishes_residual_cleanup(isolated_supervisor, monkeypatch):
    capsule = isolated_supervisor.create_task("audit-ipc-residual")
    capsule.undo_stack.append({"non_undoable": True, "action": "audit_external_commit"})
    core = bare_resident(isolated_supervisor)
    monkeypatch.setattr(task_supervisor, "time", SimpleNamespace(sleep=lambda seconds: None))
    response = core.handle_ipc_command({"command": "stop"})
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert "residual" in str(response).lower(), f"IPC omitted known residual state: {response}"


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-08: failed stop still appears in IPC stopped_tasks")
def test_ipc_stop_reply_does_not_claim_nonterminal_task_stopped(isolated_supervisor, monkeypatch):
    capsule = isolated_supervisor.create_task("audit-ipc-failed-cleanup")
    # P04 now converts resource-cleanup errors into terminal residual evidence.
    # Keep BA-08's separate nonterminal IPC assertion by injecting an unexpected
    # failure at the state boundary, after the actual ROLLING_BACK transition.
    transition = isolated_supervisor._transition
    def fail_after_rollback(capsule, state):
        transition(capsule, state)
        if state == TaskState.ROLLING_BACK:
            raise RuntimeError("Audit fixture nonterminal boundary failure")
    monkeypatch.setattr(isolated_supervisor, "_transition", fail_after_rollback)
    core = bare_resident(isolated_supervisor)
    monkeypatch.setattr(task_supervisor, "time", SimpleNamespace(sleep=lambda seconds: None))
    response = core.handle_ipc_command({"command": "stop"})
    if capsule.state != TaskState.ROLLING_BACK:
        raise RuntimeError("Fixture did not reproduce nonterminal cleanup failure")
    assert capsule.task_id not in response.get("stopped_tasks", []), (
        f"Task remains {capsule.state.value} but IPC reports {response}")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows credential initialization path")
@pytest.mark.xfail(strict=True, raises=AssertionError, reason="BA-09: first Windows credential can inherit a broadly readable ACL")
def test_first_windows_credential_is_verified_before_return(tmp_path):
    import ctypes
    from ctypes import wintypes

    # Only this new empty fixture directory gets a permissive ACL. Owner Rights
    # preserves full control; Builtin Users inherit read access to demonstrate
    # why Windows os.open(mode=0600) alone is not a credential security boundary.
    root = tmp_path / "audit-permissive-fixture"
    root.mkdir()
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.ULONG)]
    advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
    advapi.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    advapi.SetFileSecurityW.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor = ctypes.c_void_p()
    if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            "D:P(A;OICI;FA;;;OW)(A;OICI;GR;;;BU)", 1, ctypes.byref(descriptor), None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not advapi.SetFileSecurityW(str(root), 0x80000004, descriptor):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.LocalFree(descriptor)
    key = root / "Pluma" / "ipc_secret.key"
    try:
        try:
            secret = ipc._get_or_create_ipc_secret(paths_root=str(root))
        except RuntimeError:
            return  # Refusing an insecure credential location is also safe.
        if len(secret) != ipc.IPC_SECRET_SIZE: raise RuntimeError("Fixture credential creation failed")
        secure = True
        try: ipc._verify_win32_file_dacl(str(key))
        except RuntimeError: secure = False
        assert secure, "Factory returned a new credential whose inherited Users-read ACL its own validator rejects"
    finally:
        key.unlink(missing_ok=True)  # exact fixture key only, no secret logging


def test_unknown_tool_never_reaches_policy():
    policy = Mock()
    registry = ToolRegistry(policy_engine=policy)
    with pytest.raises(KeyError): registry.execute("audit_unknown", {})
    policy.evaluate.assert_not_called()


def test_invalid_arguments_never_reach_policy():
    class RequiredArgs(BaseModel):
        required_count: int
    policy = Mock()
    registry = ToolRegistry(policy_engine=policy)
    spec = probe_spec(lambda args: ToolResult.success("audit_probe"))
    spec.args_schema = RequiredArgs
    registry.register(spec)
    with pytest.raises(ValueError): registry.execute("audit_probe", {})
    policy.evaluate.assert_not_called()


def test_failed_verification_cannot_report_success():
    registry = ToolRegistry()
    registry.register(probe_spec(
        lambda args: ToolResult.success("audit_probe", factual_message="Counter observed."),
        verifier=lambda result: VerifyResult(ok=False, method="state", detail="Postcondition absent.")))
    try: result = registry.execute("audit_probe", {})
    finally: registry.close()
    assert not result.ok and not result.verified


def test_pre_cancelled_task_does_not_start_executor(isolated_supervisor):
    capsule = isolated_supervisor.create_task("audit-pre-cancel")
    capsule.cancellation_token.cancel()
    executor = Mock(return_value=ToolResult.success("audit_probe"))
    registry = ToolRegistry()
    registry.register(probe_spec(executor))
    with pytest.raises(TaskCancelledError): registry.execute("audit_probe", {}, capsule)
    executor.assert_not_called()
