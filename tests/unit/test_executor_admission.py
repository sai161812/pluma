"""P01: controlled ordering at thread/process executor admission.

Only inert counters and owned temporary files/processes are used. The two
spawn tests exercise the actual controller and inherited gate; they are not
P10's full hung-worker/descendant/STOP cleanup or hardware latency acceptance.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import inspect
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.core.job_object import WindowsJobObject
from pluma.core.task_supervisor import TaskCapsule
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools import registry as runner


class EmptyArgs(BaseModel):
    model_config = {"extra": "forbid"}


def spec(executor, **kwargs):
    return ToolSpec(
        name="admission_probe", description="P01 inert fixture.",
        args_schema=EmptyArgs, risk_class=kwargs.pop("risk_class", RiskClass.LOW),
        timeout_s=kwargs.pop("timeout_s", 5), executor=executor,
        verifier=kwargs.pop("verifier", lambda result: VerifyResult(ok=True, method="state", detail="Counter read back.")),
        **kwargs,
    )


@pytest.fixture
def task():
    capsule = TaskCapsule(request_id="p01-fixture")
    registry = runner.ToolRegistry()
    try:
        yield capsule, registry
    finally:
        registry.close()
        capsule.close_resources()


def wait(event):
    assert event.wait(5), "Owned fixture did not reach the controlled boundary."


def cancelled(future):
    try:
        result = future.result(6)
    except TaskCancelledError:
        return
    assert not result.ok and not result.verified
    assert result.error_code == "TASK_CANCELLED"


@pytest.mark.parametrize("during", ["policy", "prestate"])
def test_stop_during_wait_prevents_prestate_or_execution(task, during):
    capsule, registry = task
    entered, release = threading.Event(), threading.Event()
    calls = []

    def capture(args):
        calls.append("prestate")
        if during == "prestate":
            entered.set()
            wait(release)
        return {"action": "counter", "previous": 7}

    def evaluate(**kwargs):
        entered.set()
        wait(release)
        return SimpleNamespace(decision="ALLOW")

    registry.register(spec(lambda args: calls.append("executor"), undo_builder=capture))
    if during == "policy":
        registry._policy_engine = SimpleNamespace(evaluate=evaluate)
    with ThreadPoolExecutor(max_workers=1) as callers:
        future = callers.submit(registry.execute, "admission_probe", {}, capsule)
        try:
            wait(entered)
            capsule.cancellation_token.cancel()
        finally:
            release.set()
        cancelled(future)
    assert calls == (["prestate"] if during == "prestate" else [])
    assert capsule.undo_stack == []
    assert capsule.worker_controller is None


@pytest.mark.parametrize("cancellable", [True, False])
def test_already_stopped_never_admits_even_noncancellable_tool(task, cancellable):
    capsule, registry = task
    calls = []
    registry.register(spec(lambda args: calls.append("executor"), cancellable=cancellable))
    capsule.cancellation_token.cancel()
    with pytest.raises(TaskCancelledError):
        registry.execute("admission_probe", {}, capsule)
    assert calls == []


def test_stopped_queued_thread_cannot_escape_after_pool_drain(task, monkeypatch):
    capsule, registry = task
    occupied, release, queued = threading.Event(), threading.Event(), threading.Event()
    calls, submitted = [], []
    registry.register(spec(lambda args: calls.append(capsule.stop_latch_set)))
    with ThreadPoolExecutor(max_workers=1) as workers, ThreadPoolExecutor(max_workers=1) as callers:
        def occupy():
            occupied.set()
            wait(release)
        blocker = workers.submit(occupy)
        wait(occupied)

        class Pool:
            def submit(self, *args):
                future = workers.submit(*args)
                submitted.append(future)
                queued.set()
                return future

        monkeypatch.setattr(runner, "_GLOBAL_TOOL_EXECUTOR", Pool())
        future = callers.submit(registry.execute, "admission_probe", {}, capsule)
        try:
            wait(queued)
            assert not submitted[0].running()
            capsule.cancellation_token.cancel()
        finally:
            release.set()
        blocker.result(6)
        cancelled(future)
    assert calls == []
    assert submitted[0].done()


def test_stop_during_invocation_preparation_is_checked_on_worker(task):
    capsule, registry = task
    calls = []

    class Probe:
        @property
        def __signature__(self):
            capsule.cancellation_token.cancel()
            return inspect.Signature([inspect.Parameter("args", inspect.Parameter.POSITIONAL_OR_KEYWORD)])

        def __call__(self, args):
            calls.append(capsule.stop_latch_set)

    registry.register(spec(Probe()))
    result = registry.execute("admission_probe", {}, capsule)
    assert not result.ok and result.error_code == "TASK_CANCELLED"
    assert calls == []


def test_rejected_worker_entry_records_failure_without_undo(task, tmp_path):
    capsule, registry = task
    calls = []

    class Probe:
        @property
        def __signature__(self):
            capsule.cancellation_token.cancel()
            return inspect.Signature([inspect.Parameter("args", inspect.Parameter.POSITIONAL_OR_KEYWORD)])

        def __call__(self, args):
            calls.append("executor")

    registry.register(spec(Probe(), undo_builder=lambda args: {"action": "counter", "previous": 7}))
    with DbConnection(str(tmp_path / "rejected.db")) as db:
        ledger, query = ActivityLedger(db), ActivityQuery(db)
        ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id, input_mode="text", command_text="Fixture counter"))
        result = registry.execute("admission_probe", {}, capsule, ledger=ledger)
        actions = query.actions_for_task(capsule.task_id)
        assert len(actions) == 1 and actions[0]["verified"] == 0
        assert "TASK_CANCELLED" in actions[0]["error_json"]
        assert query.available_undo_records_for_task(capsule.task_id) == []
    assert not result.ok and not result.verified and result.undo_record is None
    assert capsule.undo_stack == [] and calls == []


def test_queued_timeout_is_cancelled_without_later_execution(task, monkeypatch):
    capsule, registry = task
    occupied, release = threading.Event(), threading.Event()
    calls = []
    registry.register(spec(lambda args: calls.append("executor"), timeout_s=0.05))
    with ThreadPoolExecutor(max_workers=1) as workers:
        def occupy():
            occupied.set()
            wait(release)
        blocker = workers.submit(occupy)
        wait(occupied)
        monkeypatch.setattr(runner, "_GLOBAL_TOOL_EXECUTOR", workers)
        try:
            result = registry.execute("admission_probe", {}, capsule)
        finally:
            release.set()
        blocker.result(6)
    assert not result.ok and result.error_code == "TOOL_TIMEOUT"
    assert calls == []


def test_stop_does_not_wait_for_admitted_tool_body(task):
    capsule, registry = task
    entered, release, latched = threading.Event(), threading.Event(), threading.Event()

    def execute(args, context):
        assert not context.stop_latch_set
        entered.set()
        wait(release)
        return ToolResult.success("admission_probe", factual_message="Counter observed.")

    def stop():
        capsule.cancellation_token.cancel()
        latched.set()

    registry.register(spec(execute))
    with ThreadPoolExecutor(max_workers=2) as callers:
        executing = callers.submit(registry.execute, "admission_probe", {}, capsule)
        try:
            wait(entered)
            stopping = callers.submit(stop)
            wait(latched)  # body still blocked; not a physical latency claim
        finally:
            release.set()
        stopping.result(6)
        assert executing.result(6).verified
    assert capsule.stop_latch_set


def test_verified_success_keeps_prestate_and_sqlite_evidence(task, tmp_path):
    capsule, registry = task
    order, counter = [], [7]

    def capture(args):
        order.append("prestate")
        return {"action": "counter", "previous": counter[0]}

    def execute(args, context):
        order.append("executor")
        counter[0] = 9
        return ToolResult.success("admission_probe", data={"value": counter[0]}, factual_message="Counter set to 9.")

    def verify(result):
        order.append("verify")
        return VerifyResult(ok=counter[0] == 9, method="state", detail="Counter equals 9.")

    registry.register(spec(execute, undo_builder=capture, verifier=verify))
    with DbConnection(str(tmp_path / "ledger.db")) as db:
        ledger, query = ActivityLedger(db), ActivityQuery(db)
        ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id, input_mode="text", command_text="Fixture counter"))
        result = registry.execute("admission_probe", {}, capsule, ledger=ledger)
        assert result.ok and result.verified
        actions = query.actions_for_task(capsule.task_id)
        undos = query.available_undo_records_for_task(capsule.task_id)
        assert len(actions) == len(undos) == 1
        assert actions[0]["verified"] == 1
        assert undos[0]["action_id"] == actions[0]["id"]
    assert order == ["prestate", "executor", "verify"]
    assert result.undo_record == {"action": "counter", "previous": 7}
    assert capsule.undo_stack == [result.undo_record]


def test_process_gate_created_after_stop_is_closed():
    token = CancellationToken()
    assert token._process_admission is None
    token.cancel()
    gate = token.process_admission()
    assert token.process_admission() is gate
    with pytest.raises(TaskCancelledError):
        gate.admit_executor()


def test_native_gate_handle_is_released_with_token():
    import ctypes
    from ctypes import wintypes
    import gc
    import weakref
    token = CancellationToken()
    gate = token.process_admission()
    handle, reference = gate._handle, weakref.ref(gate)
    del gate, token
    gc.collect()
    assert reference() is None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetHandleInformation.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetHandleInformation.restype = wintypes.BOOL
    flags = wintypes.DWORD()
    assert not kernel.GetHandleInformation(handle, ctypes.byref(flags))
    assert ctypes.get_last_error() == 6  # ERROR_INVALID_HANDLE


def test_stop_while_waiting_for_controller_prevents_worker_start(task, monkeypatch):
    capsule, registry = task
    controller = runner.TaskWorkerController(capsule.task_id)
    gate_ready = threading.Event()
    original = capsule.cancellation_token.process_admission

    def gate():
        result = original()
        gate_ready.set()
        return result

    monkeypatch.setattr(capsule.cancellation_token, "process_admission", gate)
    controller._lock.acquire()
    with ThreadPoolExecutor(max_workers=1) as callers:
        future = callers.submit(controller.execute_call, lambda args: None, {}, runner.WorkerRequest(capsule.task_id, "admission_probe", {}, 1), 1, cancellation_token=capsule.cancellation_token)
        try:
            wait(gate_ready)
            capsule.cancellation_token.cancel()
        finally:
            controller._lock.release()
        with pytest.raises(TaskCancelledError):
            future.result(6)
    assert controller._proc is None
    assert controller._conn is None


def test_stop_during_worker_startup_rejects_at_child_entry(task, monkeypatch):
    capsule, registry = task
    controller = runner.TaskWorkerController(capsule.task_id)
    responses, calls = [], []

    class Connection:
        def __init__(self): self.message = None
        def send(self, message): self.message = message
        def poll(self, timeout):
            message = self.message

            class ChildConnection:
                def __init__(self): self.received = 0
                def poll(self, timeout): return True
                def recv(self):
                    self.received += 1
                    return message if self.received == 1 else "STOP"
                def send(self, response): responses.append(response)

            runner._worker_process_loop(ChildConnection(), capsule.task_id, controller._admission)
            return True
        def recv(self): return responses.pop()
        def close(self): pass

    def start(job_object=None, admission=None):
        controller._conn = Connection()
        controller._admission = admission
        capsule.cancellation_token.cancel()

    monkeypatch.setattr(controller, "_ensure_worker_started", start)
    status, message = controller.execute_call(lambda args: calls.append("executor"), {}, runner.WorkerRequest(capsule.task_id, "admission_probe", {}, 1), 1, cancellation_token=capsule.cancellation_token)
    assert status == "cancelled"
    assert calls == []
    controller.terminate_and_join()


@pytest.mark.parametrize("stop_during", ["receive", "preparation"])
def test_worker_rejects_late_request_before_executor(stop_during):
    token, calls, responses = CancellationToken(), [], []

    def execute(args):
        calls.append("executor")

    class Probe:
        @property
        def __signature__(self):
            token.cancel()
            return inspect.signature(execute)

        def __call__(self, args):
            calls.append("executor")

    class Connection:
        def __init__(self): self.received = 0
        def poll(self, timeout): return True
        def recv(self):
            self.received += 1
            if self.received > 1: return "STOP"
            if stop_during == "receive": token.cancel()
            return (Probe() if stop_during == "preparation" else execute, {}, runner.WorkerRequest("owned", "admission_probe", {}, 1))
        def send(self, response): responses.append(response)

    runner._worker_process_loop(Connection(), "owned", token.process_admission())
    assert [status for status, _ in responses] == ["cancelled"]
    assert calls == []


def test_worker_refuses_wrong_task_without_execution():
    calls, responses = [], []

    class Connection:
        def __init__(self): self.received = 0
        def poll(self, timeout): return True
        def recv(self):
            self.received += 1
            if self.received > 1: return "STOP"
            return (lambda args: calls.append("executor"), {}, runner.WorkerRequest("other-task", "admission_probe", {}, 1))
        def send(self, response): responses.append(response)

    runner._worker_process_loop(Connection(), "owned", CancellationToken().process_admission())
    assert responses == [("error", "Worker request does not belong to this task.")]
    assert calls == []


@dataclass
class SpawnProbe:
    """Preparation barrier in an actual spawned owned worker, using temp files."""
    root: str
    pause: bool = False

    @property
    def __signature__(self):
        root = Path(self.root)
        (root / "prepared").touch()
        deadline = time.monotonic() + 8
        while self.pause and not (root / "release").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("P01 owner did not release preparation fixture.")
            time.sleep(0.005)
        return inspect.Signature([inspect.Parameter("args", inspect.Parameter.POSITIONAL_OR_KEYWORD), inspect.Parameter("context", inspect.Parameter.POSITIONAL_OR_KEYWORD)])

    def __call__(self, args, context):
        (Path(self.root) / "executed").write_text(context.task_id, encoding="utf-8")
        return ToolResult.success("admission_probe", factual_message="Owned marker created.")


@pytest.mark.parametrize("stop", [False, True])
def test_actual_spawn_inherits_live_task_gate(task, tmp_path, stop):
    capsule, registry = task
    capsule.job_object = WindowsJobObject(name="pluma-p01-" + capsule.task_id)
    registry.register(spec(SpawnProbe(str(tmp_path), pause=stop), risk_class=RiskClass.HIGH, timeout_s=10))
    with ThreadPoolExecutor(max_workers=1) as callers:
        future = callers.submit(registry.execute, "admission_probe", {}, capsule)
        try:
            deadline = time.monotonic() + 8
            while not (tmp_path / "prepared").exists() and not future.done() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert (tmp_path / "prepared").exists(), future.result(1) if future.done() else "Worker preparation timed out"
            assert capsule.worker_controller._proc.is_alive()
            if stop:
                capsule.cancellation_token.cancel()
        finally:
            (tmp_path / "release").touch()
        result = future.result(10)
    proc = capsule.worker_controller._proc
    registry.close()
    assert not proc.is_alive(), "Owned fixture worker did not exit"
    if stop:
        assert not result.ok and not result.verified
        assert result.error_code == "TASK_CANCELLED"
        assert not (tmp_path / "executed").exists()
        assert capsule.undo_stack == []
    else:
        assert result.ok and result.verified
        assert (tmp_path / "executed").read_text(encoding="utf-8") == capsule.task_id


def test_recycled_controller_rebinds_task_and_gate(task, tmp_path, monkeypatch):
    capsule, registry = task
    capsule.job_object = WindowsJobObject(name="pluma-p01-rebind-" + capsule.task_id)
    registry.register(spec(SpawnProbe(str(tmp_path)), risk_class=RiskClass.HIGH))
    assert registry.execute("admission_probe", {}, capsule).ok
    controller = capsule.worker_controller
    old_proc = controller._proc
    capsule.cancellation_token.cancel()
    next_capsule = TaskCapsule(request_id="p01-next-fixture")
    next_capsule.job_object = WindowsJobObject(name="pluma-p01-rebind-" + next_capsule.task_id)
    try:
        # Same route as the existing idle-controller pool: ownership is renamed
        # but the next call must restart the worker with its new live gate.
        controller.task_id = next_capsule.task_id
        monkeypatch.setattr(registry, "get_worker", lambda task_id: controller)
        result = registry.execute("admission_probe", {}, next_capsule)
        new_proc = controller._proc
        assert result.ok and result.verified
        assert new_proc is not old_proc and not old_proc.is_alive()
        assert (tmp_path / "executed").read_text(encoding="utf-8") == next_capsule.task_id
        registry.close()
        assert not new_proc.is_alive()
    finally:
        registry.close()
        next_capsule.close_resources()


def test_spawn_crash_does_not_strand_stop_latch(task, tmp_path):
    capsule, registry = task
    capsule.job_object = WindowsJobObject(name="pluma-p01-crash-" + capsule.task_id)
    registry.register(spec(SpawnProbe(str(tmp_path), pause=True), risk_class=RiskClass.HIGH, timeout_s=10))
    with ThreadPoolExecutor(max_workers=1) as callers:
        executing = callers.submit(registry.execute, "admission_probe", {}, capsule)
        try:
            deadline = time.monotonic() + 8
            while not (tmp_path / "prepared").exists() and not executing.done() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert (tmp_path / "prepared").exists()
            proc = capsule.worker_controller._proc
            proc.kill()  # only this test's registered task worker
            proc.join(3)
            assert not proc.is_alive()
            stopping = callers.submit(capsule.cancellation_token.cancel)
            assert stopping.result(3)
            assert capsule.stop_latch_set
            with pytest.raises(TaskCancelledError):
                capsule.cancellation_token.process_admission().admit_executor()
        finally:
            (tmp_path / "release").touch()
        result = executing.result(10)
    assert not result.ok and not result.verified
    assert not (tmp_path / "executed").exists()
