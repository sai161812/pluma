"""P03: bounded owned worker I/O/lifetime on real Windows and injected faults.

All processes, pipes and files belong to these fixtures. No desktop apps,
clipboard, microphone or model are used. This is not P10's combined gate.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
import multiprocessing
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from pluma.adapters.worker_pipe import WorkerPipe, WorkerIOCancelled
from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.core.job_object import WindowsJobObject
from pluma.core.task_supervisor import TaskCapsule
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools import registry as runner


def await_file(path, future=None):
    deadline = time.monotonic() + 6
    while not path.exists() and time.monotonic() < deadline:
        if future is not None and future.done():
            pytest.fail(f"Owned worker ended before marker: {future.result()}")
        time.sleep(0.005)
    assert path.exists(), "Owned fixture did not reach boundary."


@dataclass
class OwnedProbe:
    root: str
    cooperative: bool = False
    descendant: bool = False

    def __call__(self, args, context):
        root = Path(self.root)
        if self.descendant:
            from pluma.core.ownership import get_process_creation_time
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            context.register_owned_resource("subprocess", "PLUMA_CREATED", str(child.pid), {
                "task_id": context.task_id, "pid": child.pid,
                "creation_time": get_process_creation_time(child.pid),
                "command_class": "p03_owned_fixture",
            })
            (root / "child").write_text(str(child.pid))
        (root / "entered").touch()
        if self.cooperative:
            while not context.cancellation_token.is_cancelled:
                time.sleep(0.002)
            (root / "cooperated").touch()
            return ToolResult.failure("worker_probe", "Owned fixture cancelled.")
        time.sleep(30)
        (root / "late").touch()
        return ToolResult.success("worker_probe", factual_message="Owned marker created.")


def request(task_id="p03"):
    return runner.WorkerRequest(task_id, "worker_probe", {}, 30)


def never_read_requests(conn, task_id, admission):
    """Owned spawn target for forcing a full parent request pipe."""
    time.sleep(30)


def owned_noop(args):
    return ToolResult.success("worker_probe", factual_message="Owned fixture returned.")


@pytest.fixture
def controller():
    ctrl = runner.TaskWorkerController("p03")
    try:
        yield ctrl
    finally:
        ctrl.terminate_and_join()


@pytest.mark.parametrize("cooperative", [False, True])
def test_real_response_wait_stops_owned_worker(controller, tmp_path, cooperative, record_property):
    token = CancellationToken()
    controller.GRACE_S = 0.4 if cooperative else 0.05
    capsule_job = WindowsJobObject()
    try:
        with ThreadPoolExecutor(1) as pool:
            executing = pool.submit(controller.execute_call, OwnedProbe(str(tmp_path), cooperative), {}, request(), 30,
                                    job_object=capsule_job, cancellation_token=token)
            await_file(tmp_path / "entered", executing)
            proc = controller._proc
            identity = dict(controller.worker_identity)
            started = time.monotonic()
            token.cancel()
            controller.terminate_and_join()
            elapsed = time.monotonic() - started
            status, _ = executing.result(2)
        assert elapsed < 1.5  # independent of the 30-second tool deadline
        record_property("owned_stop_seconds", elapsed)
        assert status == "cancelled" and not proc.is_alive()
        assert identity["pid"] == proc.pid and identity["creation_time"] > 0
        assert identity["task_id"] == "p03" and identity["ownership"] == "PLUMA_CREATED"
        assert identity["command_class"] == "tool_worker"
        assert controller.worker_identity["exit_code"] is not None
        assert not (tmp_path / "late").exists()
        if cooperative:
            assert (tmp_path / "cooperated").exists() and proc.exitcode == 0
        controller.terminate_and_join()  # repeated disposal, no restart
        assert controller.execute_call(OwnedProbe(str(tmp_path)), {}, request(), 1)[0] == "cancelled"
    finally:
        capsule_job.close()


def test_real_owned_descendant_stops_unrelated_fixture_survives(controller, tmp_path):
    import _winapi
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    child_handle = None
    try:
        with ThreadPoolExecutor(1) as pool:
            executing = pool.submit(controller.execute_call, OwnedProbe(str(tmp_path), descendant=True), {}, request(), 30)
            await_file(tmp_path / "entered", executing)
            child_pid = int((tmp_path / "child").read_text())
            child_handle = _winapi.OpenProcess(0x100000 | 0x1000, False, child_pid)
            assert _winapi.WaitForSingleObject(child_handle, 0) == _winapi.WAIT_TIMEOUT
            controller.terminate_and_join()
            assert executing.result(2)[0] == "cancelled"
        assert _winapi.WaitForSingleObject(child_handle, 1000) == _winapi.WAIT_OBJECT_0
        assert not controller._proc.is_alive()
        assert unrelated.poll() is None
        assert not (tmp_path / "late").exists()
    finally:
        controller.terminate_and_join()
        if child_handle is not None:
            _winapi.CloseHandle(child_handle)
        unrelated.kill()
        unrelated.wait(3)


@pytest.mark.parametrize("cancel", [False, True])
def test_controller_interrupts_real_full_request_pipe(controller, tmp_path, monkeypatch, cancel):
    token = CancellationToken()
    create = runner._MP_CONTEXT.Process
    def factory(*args, **kwargs):
        kwargs["target"] = never_read_requests
        return create(*args, **kwargs)
    monkeypatch.setattr(runner._MP_CONTEXT, "Process", factory)
    with ThreadPoolExecutor(1) as pool:
        executing = pool.submit(controller.execute_call, OwnedProbe(str(tmp_path)),
                                {"payload": b"x" * (2 * 1024 * 1024)}, request(), 30 if cancel else 0.25,
                                cancellation_token=token)
        if cancel:
            deadline = time.monotonic() + 3
            while (controller._conn is None or controller._conn._pending is None) and not executing.done() and time.monotonic() < deadline:
                time.sleep(0.001)
            assert controller._conn is not None and controller._conn._pending is not None
            began = time.monotonic()
            controller.terminate_and_join()
            assert time.monotonic() - began < 1.5
        assert executing.result(2)[0] == ("cancelled" if cancel else "timeout")
    assert token.is_cancelled and token.wait_for_cancel(0)
    assert not controller._proc.is_alive() and controller._conn is None
    assert not (tmp_path / "entered").exists()


def test_controller_response_deadline_terminates_worker(controller, tmp_path):
    began = time.monotonic()
    assert controller.execute_call(OwnedProbe(str(tmp_path)), {}, request(), 0.8)[0] == "timeout"
    assert time.monotonic() - began < 2
    assert not controller._proc.is_alive() and controller._conn is None
    assert not (tmp_path / "late").exists()


@pytest.mark.parametrize("operation", ["send", "recv"])
@pytest.mark.parametrize("cancel", [False, True])
def test_real_pipe_pending_io_is_bounded(operation, cancel):
    parent, child = multiprocessing.Pipe()
    stop = threading.Event()
    pipe = WorkerPipe(parent, stop.is_set)
    started = threading.Event()

    def blocked():
        started.set()
        if operation == "send":
            return pipe.send(b"x" * (2 * 1024 * 1024), time.monotonic() + (10 if cancel else 0.08))
        return pipe.recv(time.monotonic() + (10 if cancel else 0.08))

    try:
        with ThreadPoolExecutor(1) as pool:
            executing = pool.submit(blocked)
            assert started.wait(1)
            # Observe an actual pending OVERLAPPED, not a scheduling assumption.
            deadline = time.monotonic() + 1
            while pipe._pending is None and not executing.done() and time.monotonic() < deadline:
                time.sleep(0.001)
            assert pipe._pending is not None
            if cancel:
                stop.set()
            with pytest.raises(WorkerIOCancelled if cancel else TimeoutError):
                executing.result(1)
        assert pipe._pending is None
    finally:
        stop.set()
        pipe.close()
        pipe.close()
        child.close()


@pytest.mark.parametrize("size", [0, 20, 1024 * 1024])
def test_native_pipe_preserves_multiprocessing_wire_format(size):
    parent, child = multiprocessing.Pipe()
    pipe = WorkerPipe(parent, lambda: False)
    payload = ("ok", b"x" * size)
    try:
        with ThreadPoolExecutor(1) as pool:
            writing = pool.submit(child.send, payload)
            assert pipe.recv(time.monotonic() + 2) == payload
            writing.result(2)
            reading = pool.submit(child.recv)
            pipe.send(payload, time.monotonic() + 2)
            assert reading.result(2) == payload
    finally:
        pipe.close()
        child.close()


def test_pipe_failed_cancellation_retains_operation_for_retry(monkeypatch):
    import _winapi
    closed = []
    pipe = WorkerPipe(SimpleNamespace(close=lambda: closed.append(True)), lambda: True)
    ov = SimpleNamespace(event=1, cancel=lambda: None, GetOverlappedResult=lambda wait: (0, 0))
    monkeypatch.setattr(_winapi, "WaitForSingleObject", lambda *a: _winapi.WAIT_TIMEOUT)
    with pytest.raises(RuntimeError, match="did not drain"):
        pipe._complete(ov, _winapi.ERROR_IO_PENDING, time.monotonic() + 1)
    assert pipe._pending is ov and not closed
    monkeypatch.setattr(_winapi, "WaitForSingleObject", lambda *a: _winapi.WAIT_OBJECT_0)
    pipe.close()
    assert pipe._pending is None and closed == [True]


def test_stop_during_os_start_retains_owner_until_start_returns(controller, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    create = runner._MP_CONTEXT.Process

    def factory(*args, **kwargs):
        proc = create(*args, **kwargs)
        start = proc.start
        def blocked_start():
            entered.set()
            assert release.wait(3)
            start()
        proc.start = blocked_start
        return proc

    monkeypatch.setattr(runner._MP_CONTEXT, "Process", factory)
    controller.CLEANUP_S = 0.08
    with ThreadPoolExecutor(1) as pool:
        executing = pool.submit(controller.execute_call, OwnedProbe(str(tmp_path)), {}, request(), 30)
        try:
            assert entered.wait(2)
            began = time.monotonic()
            with pytest.raises(RuntimeError, match="startup is still pending"):
                controller.terminate_and_join()
            assert time.monotonic() - began < 0.3
            assert controller._proc is not None and controller._conn is not None
            assert controller._admission.is_cancelled()
        finally:
            release.set()
        assert executing.result(3)[0] == "cancelled"
    assert not controller._proc.is_alive()
    assert not (tmp_path / "entered").exists()
    assert controller._conn is None


def test_cancel_before_native_start_does_not_launch(controller, tmp_path, monkeypatch):
    token = CancellationToken()
    create = runner._MP_CONTEXT.Process
    launched = []
    def factory(*args, **kwargs):
        proc = create(*args, **kwargs)
        proc.start = lambda: launched.append(True)
        token.cancel()
        return proc
    monkeypatch.setattr(runner._MP_CONTEXT, "Process", factory)
    assert controller.execute_call(OwnedProbe(str(tmp_path)), {}, request(), 30, cancellation_token=token)[0] == "cancelled"
    assert not launched and controller._conn is None


def test_queued_call_has_own_deadline_without_stopping_inflight_call(controller):
    controller._lock.acquire()
    try:
        started = time.monotonic()
        assert controller.execute_call(lambda args: None, {}, request(), 0.05)[0] == "timeout"
        assert time.monotonic() - started < 0.3
        assert controller._proc is None and not controller._stop.is_set()
    finally:
        controller._lock.release()


@pytest.mark.parametrize("failure", ["kill", "still_alive", "pipe", "job"])
def test_failed_cleanup_retains_owned_references_and_can_retry(controller, failure):
    controller.CLEANUP_S = 0.05
    alive, fail = [True], [True]
    def kill():
        if failure == "kill" and fail[0]:
            raise OSError("Injected owned-handle failure")
        if not (failure == "still_alive" and fail[0]):
            alive[0] = False
    def close():
        if failure == "pipe" and fail[0]:
            raise RuntimeError("Injected owned-pipe failure")
    def terminate():
        if failure == "job" and fail[0]:
            raise RuntimeError("Injected owned-job failure")
    proc = SimpleNamespace(pid=123, exitcode=1, is_alive=lambda: alive[0], kill=kill, join=lambda **kw: None)
    conn = SimpleNamespace(close=close)
    controller._proc, controller._conn = proc, conn
    job_closed = [False]
    # Explicit readback on the double; a call return is no longer evidence.
    type_job = type("OwnedJobDouble", (), {
        "terminate": staticmethod(terminate),
        "close": lambda self: job_closed.__setitem__(0, True),
        "active_process_count": lambda self: 1 if failure == "job" and fail[0] else 0,
        "is_closed": property(lambda self: job_closed[0]),
    })
    controller._worker_job = type_job()
    with pytest.raises((OSError, RuntimeError)):
        controller.terminate_and_join()
    assert controller._proc is proc and controller._conn is conn and controller._stop.is_set()
    fail[0] = False
    controller.terminate_and_join()
    assert not alive[0] and controller._conn is None


def test_containment_failure_never_admits_executor(controller, tmp_path):
    job = SimpleNamespace(assign_process=lambda pid: (_ for _ in ()).throw(OSError("Injected containment refusal")))
    status, _ = controller.execute_call(OwnedProbe(str(tmp_path)), {}, request(), 5, job_object=job)
    assert status == "error" and not controller._proc.is_alive()
    assert controller._conn is None and not (tmp_path / "entered").exists()


def test_repeated_disposal_is_safe_concurrently(controller, tmp_path):
    with ThreadPoolExecutor(5) as pool:
        executing = pool.submit(controller.execute_call, OwnedProbe(str(tmp_path)), {}, request(), 30)
        await_file(tmp_path / "entered", executing)
        stopping = [pool.submit(controller.terminate_and_join) for _ in range(4)]
        for future in stopping:
            future.result(2)
        assert executing.result(2)[0] == "cancelled"
    assert not controller._proc.is_alive() and controller._conn is None


def test_idle_pool_never_retags_an_old_task_controller():
    registry = runner.ToolRegistry()
    try:
        old = registry.get_worker("old")
        assert old.execute_call(owned_noop, {}, request("old"), 5)[0] == "ok"
        registry.cleanup_task("old", recycle=True)
        new = registry.get_worker("new")
        assert new is not old and old.task_id == "old"
        assert new.execute_call(owned_noop, {}, request("new"), 5)[0] == "ok"
        old.terminate_and_join()
        assert new._proc.is_alive() and not old._proc.is_alive()
        assert new.worker_identity["task_id"] == "new"
    finally:
        registry.close()


def test_owned_handle_identity_and_job_assignment_ignore_reused_pid(controller, monkeypatch):
    from pluma.core import job_object
    assert controller.execute_call(owned_noop, {}, request(), 5)[0] == "ok"
    proc = controller._proc
    # A stale/reused numeric PID must never influence handle-based operations.
    replacement_pid = SimpleNamespace(pid=99999999, sentinel=proc.sentinel)
    monkeypatch.setattr(job_object.kernel32, "OpenProcess", lambda *a: pytest.fail("Worker PID was reopened"))
    assert job_object.owned_process_creation_time(replacement_pid) == controller.worker_identity["creation_time"]
    with WindowsJobObject() as job:
        job.assign_process(replacement_pid)
        job.terminate()
        proc.join(2)
        assert not proc.is_alive()


class EmptyArgs(BaseModel):
    model_config = {"extra": "forbid"}


def owned_probe_policy():
    from tests.fixtures.policy import owned_fixture_policy
    return owned_fixture_policy('worker_probe')


@contextmanager
def owned_registry_execution(registry, capsule, ledger):
    """Cancel before pool join even when a startup assertion raises."""
    with ThreadPoolExecutor(1) as pool:
        executing = pool.submit(registry.execute, "worker_probe", {}, capsule, ledger=ledger)
        try:
            yield executing
        finally:
            capsule.cancellation_token.cancel()
            if capsule.worker_controller is not None:
                capsule.worker_controller.terminate_and_join()


def test_registry_cancellation_is_unverified_and_persisted(tmp_path):
    capsule = TaskCapsule(request_id="p03-ledger")
    capsule.job_object = WindowsJobObject()
    db = DbConnection(str(tmp_path / "ledger.db"))
    db.open()
    ledger = ActivityLedger(db)
    ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id,
                                 input_mode="text", command_text="Owned cancellation fixture", started_at="2026-10-19T00:00:00Z"))
    registry = runner.ToolRegistry(policy_engine=owned_probe_policy())
    registry.register(ToolSpec(name="worker_probe", description="Owned fixture", args_schema=EmptyArgs,
        risk_class=RiskClass.HIGH, timeout_s=30, executor=OwnedProbe(str(tmp_path)),
        verifier=lambda result: VerifyResult(ok=False, method="state", detail="Marker absent.")))
    try:
        with owned_registry_execution(registry, capsule, ledger) as executing:
            await_file(tmp_path / "entered", executing)
            capsule.cancellation_token.cancel()
            capsule.worker_controller.terminate_and_join()
            result = executing.result(2)
        assert not result.ok and not result.verified and result.error_code == "TASK_CANCELLED"
        actions = ActivityQuery(db).actions_for_task(capsule.task_id)
        assert len(actions) == 1 and not actions[0]["verified"]
        assert capsule.undo_stack == [] and not (tmp_path / "late").exists()
        assert not capsule.worker_controller._proc.is_alive()
    finally:
        registry.close()
        capsule.close_resources()
        db.close()


def test_registry_startup_assertion_drains_before_pool_join(tmp_path):
    capsule = TaskCapsule(request_id="p10-startup-failure")
    capsule.job_object = WindowsJobObject()
    registry = runner.ToolRegistry(policy_engine=owned_probe_policy())
    registry.register(ToolSpec(name="worker_probe", description="Owned failure fixture",
        args_schema=EmptyArgs, risk_class=RiskClass.HIGH, timeout_s=30,
        executor=OwnedProbe(str(tmp_path)),
        verifier=lambda result: VerifyResult(ok=False, method="state", detail="No effect expected.")))
    class StartupAssertion(Exception):
        pass
    try:
        began = time.monotonic()
        with pytest.raises(StartupAssertion):
            with owned_registry_execution(registry, capsule, None) as executing:
                await_file(tmp_path / "entered", executing)
                proc = capsule.worker_controller._proc
                raise StartupAssertion("Injected startup observation failure")
        assert time.monotonic() - began < 6  # does not wait for the 30-second tool
        assert capsule.stop_latch_set and not proc.is_alive()
        assert capsule.worker_controller.verify_cleanup() is True
        assert executing.done() and not (tmp_path / "late").exists()
    finally:
        registry.close()
        capsule.close_resources()
