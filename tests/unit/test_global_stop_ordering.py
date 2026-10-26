"""P02 latch-all, cleanup ownership and request-race fixtures.

No user applications, models, microphone or production IPC are used. Timing
properties describe these controlled fixtures, never physical hotkey p95.
"""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import threading
import time

import pytest
from pydantic import BaseModel

from pluma.config.paths import PlumaPaths
from pluma.core import task_supervisor as module
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.task_supervisor import InvalidTaskTransition, TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord
from pluma.memory.db import DbConnection
from pluma.rollback.engine import RollbackResult
from pluma.tools.base import RiskClass, ToolSpec, ToolResult, VerifyResult
from pluma.tools.registry import ToolRegistry


class Job:
    def __init__(self, **kwargs):
        self.closed = False
        self.terminated = 0

    def terminate(self, **kwargs):
        self.terminated += 1

    def close(self):
        self.closed = True

    def active_process_count(self):
        return 0  # this inert job contains no actual processes

    @property
    def is_closed(self):
        return self.closed


def empty_rollback(task_id):
    return RollbackResult(task_id, True, 0, 0, 0)


@pytest.fixture
def supervisor(monkeypatch, tmp_path):
    monkeypatch.setattr("pluma.core.job_object.WindowsJobObject", Job)
    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda seconds: None))
    result = TaskSupervisor(paths=PlumaPaths(tmp_path / "local", tmp_path / "roaming"))
    yield result
    for capsule in list(result._tasks.values()):
        capsule.close_resources()


def task(supervisor, name, running=False):
    capsule = supervisor.create_task(name)
    if running:
        supervisor.start_task(capsule.task_id)
    return capsule


def wait(event):
    assert event.wait(5), "Owned fixture did not reach its controlled boundary."


class EmptyArgs(BaseModel):
    model_config = {"extra": "forbid"}


@pytest.mark.parametrize("phase", ["grace", "worker", "rollback", "resources"])
def test_blocked_first_cleanup_cannot_leave_later_task_admitting(supervisor, monkeypatch, phase, record_property):
    capsules = [task(supervisor, "created"), task(supervisor, "running", running=True)]
    entered, release = threading.Event(), threading.Event()
    starts, observations, acknowledgements = [], [], []
    started = time.perf_counter()

    def observe():
        observations.append(tuple(cap.stop_latch_set for cap in capsules))
        if not entered.is_set():
            acknowledgements.append((time.perf_counter() - started) * 1000)
            entered.set()
            wait(release)

    if phase == "grace":
        monkeypatch.setattr(module, "time", SimpleNamespace(sleep=lambda seconds: observe()))
    elif phase == "worker":
        capsules[0].worker_controller = SimpleNamespace(terminate_and_join=observe, verify_cleanup=lambda: True)
    elif phase == "rollback":
        def rollback(**kwargs):
            observe()
            return empty_rollback(kwargs["task_id"])
        supervisor._rollback_engine = SimpleNamespace(rollback_task=rollback)
    else:
        supervisor._registry = SimpleNamespace(cleanup_task_resources=lambda task_id: (observe() or []))

    registry = ToolRegistry()
    registry.register(ToolSpec(name="stop_probe", description="P02 inert counter.", args_schema=EmptyArgs,
        risk_class=RiskClass.LOW, timeout_s=1,
        executor=lambda args: starts.append("executor"),
        verifier=lambda result: VerifyResult(ok=True, method="state", detail="Counter observed.")))
    with ThreadPoolExecutor(max_workers=1) as callers:
        stopping = callers.submit(supervisor.stop_all_active_tasks)
        try:
            wait(entered)
            assert all(cap.stop_latch_set for cap in capsules)
            assert all(cap.state in (TaskState.STOPPING, TaskState.ROLLING_BACK) for cap in capsules)
            assert not stopping.done()
            # This is the actual P01 registry admission path for the later task,
            # while the first cleanup is still blocked.
            with pytest.raises(TaskCancelledError):
                registry.execute("stop_probe", {}, capsules[1])
            with pytest.raises(TaskCancelledError):
                supervisor.create_task("during-stop")
            with pytest.raises(TaskCancelledError):
                supervisor.start_task(capsules[1].task_id)
        finally:
            release.set()
            registry.close()
        assert stopping.result(6) == [cap.task_id for cap in capsules]
    total_ms = (time.perf_counter() - started) * 1000
    assert observations and all(all(values) for values in observations)
    assert starts == []
    assert all(cap.state == TaskState.STOPPED for cap in capsules)
    assert supervisor._global_stop_depth == 0
    fresh = task(supervisor, "after-stop", running=True)
    assert not fresh.stop_latch_set
    record_property("measurement_kind", "controlled fixture latch acknowledgement versus completed cleanup; not hotkey p95")
    record_property("latch_ack_ms", round(acknowledgements[0], 3))
    record_property("completed_cleanup_ms", round(total_ms, 3))


def test_every_latch_precedes_first_state_claim(supervisor, monkeypatch):
    capsules = [task(supervisor, "A"), task(supervisor, "B", True)]
    original = supervisor._transition
    observations = []

    def transition(capsule, state):
        if state == TaskState.STOPPING:
            observations.append(tuple(cap.stop_latch_set for cap in capsules))
        return original(capsule, state)

    monkeypatch.setattr(supervisor, "_transition", transition)
    supervisor.stop_all_active_tasks()
    assert observations == [(True, True), (True, True)]


def test_native_worker_events_are_latched_before_first_grace(supervisor, monkeypatch):
    capsules = [task(supervisor, "native-created"), task(supervisor, "native-running", True)]
    gates = [cap.cancellation_token.process_admission() for cap in capsules]
    observed = []

    def grace(seconds):
        observed.append(tuple(cap.cancellation_token.is_cancelled for cap in capsules))
        for cap, gate in zip(capsules, gates):
            if gate.is_closed:
                assert cap.terminal_ready.is_set() and cap.cancellation_token.is_cancelled
            else:
                assert gate.is_cancelled()
                with pytest.raises(TaskCancelledError):
                    gate.admit_executor()

    monkeypatch.setattr(module, "time", SimpleNamespace(sleep=grace))
    supervisor.stop_all_active_tasks()
    assert observed == [(True, True), (True, True)]


def test_overlapping_global_stops_do_not_duplicate_cleanup_or_reopen_admission(supervisor):
    capsules = [task(supervisor, "A"), task(supervisor, "B", True)]
    entered, release = threading.Event(), threading.Event()
    calls = []

    def terminate(index):
        calls.append(index)
        if index == 0:
            entered.set()
            wait(release)

    for index, capsule in enumerate(capsules):
        capsule.worker_controller = SimpleNamespace(terminate_and_join=lambda index=index: terminate(index), verify_cleanup=lambda: True)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(supervisor.stop_all_active_tasks)
        try:
            wait(entered)
            second = callers.submit(supervisor.stop_all_active_tasks)
            assert second.result(3) == [cap.task_id for cap in capsules]
            assert not first.done()
            assert supervisor._global_stop_depth == 1
            supervisor.stop_task(capsules[1].task_id, grace_s=0)
            with pytest.raises(TaskCancelledError):
                supervisor.create_task("overlap-rejected")
        finally:
            release.set()
        first.result(6)
    assert calls == [0, 1]
    assert all(cap.state == TaskState.STOPPED for cap in capsules)
    assert supervisor._global_stop_depth == 0


def test_task_stop_then_global_latches_other_tasks_and_preserves_first_reason(supervisor):
    first, second = task(supervisor, "A", True), task(supervisor, "B")
    entered, release = threading.Event(), threading.Event()
    calls = []

    def terminate():
        calls.append("A")
        entered.set()
        wait(release)

    first.worker_controller = SimpleNamespace(terminate_and_join=terminate, verify_cleanup=lambda: True)
    with ThreadPoolExecutor(max_workers=2) as callers:
        single = callers.submit(supervisor.stop_task, first.task_id, StopReason.TASK_TIMEOUT, 0)
        try:
            wait(entered)
            batch = callers.submit(supervisor.stop_all_active_tasks)
            assert batch.result(3) == [first.task_id, second.task_id]
            assert second.stop_latch_set and second.state == TaskState.STOPPED
            assert not single.done()
            assert first.cancellation_token.reason == StopReason.TASK_TIMEOUT
        finally:
            release.set()
        single.result(6)
    assert calls == ["A"] and first.state == TaskState.STOPPED


def test_repeated_stop_during_rollback_does_not_reenter_cleanup(supervisor):
    capsule = task(supervisor, "rollback", True)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def rollback(**kwargs):
        calls.append(kwargs["task_id"])
        entered.set()
        wait(release)
        return empty_rollback(kwargs["task_id"])

    supervisor._rollback_engine = SimpleNamespace(rollback_task=rollback)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(supervisor.stop_task, capsule.task_id, StopReason.USER_STOP, 0)
        try:
            wait(entered)
            assert capsule.state == TaskState.ROLLING_BACK
            repeat = callers.submit(supervisor.stop_task, capsule.task_id, StopReason.TASK_TIMEOUT, 0)
            repeat.result(3)
            assert supervisor.stop_all_active_tasks() == [capsule.task_id]
            assert capsule.state == TaskState.ROLLING_BACK and not first.done()
            assert capsule.cancellation_token.reason == StopReason.USER_STOP
        finally:
            release.set()
        first.result(6)
    assert calls == [capsule.task_id] and capsule.state == TaskState.STOPPED


@pytest.mark.parametrize("terminal", [TaskState.SUCCEEDED, TaskState.FAILED, TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL, TaskState.ABORTED_BY_CRASH])
def test_global_preserves_terminal_tasks(supervisor, terminal):
    finished = task(supervisor, "finished")
    if terminal == TaskState.SUCCEEDED:
        supervisor.start_task(finished.task_id)
    elif terminal in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL):
        supervisor.transition(finished.task_id, TaskState.STOPPING)
    supervisor.transition(finished.task_id, terminal)
    live = task(supervisor, "created")
    before = (finished.state, finished.completed_at, finished.cancellation_token.reason, finished.stop_latch_set)
    assert supervisor.stop_all_active_tasks() == [live.task_id]
    assert (finished.state, finished.completed_at, finished.cancellation_token.reason, finished.stop_latch_set) == before
    assert live.state == TaskState.STOPPED


def test_creation_preparing_across_completed_stop_cannot_publish(supervisor, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    jobs = []

    class PreparingJob(Job):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            jobs.append(self)
            if len(jobs) == 1:
                entered.set()
                wait(release)

    monkeypatch.setattr("pluma.core.job_object.WindowsJobObject", PreparingJob)
    with ThreadPoolExecutor(max_workers=2) as callers:
        creating = callers.submit(supervisor.create_task, "straddles-stop")
        try:
            wait(entered)
            # Creation holds the old resource/state lock. Global latch still
            # completes, and the generation detects this even after STOP exits.
            stopping = callers.submit(supervisor.stop_all_active_tasks)
            assert stopping.result(3) == []
            assert supervisor._global_stop_depth == 0
        finally:
            release.set()
        with pytest.raises(TaskCancelledError):
            creating.result(6)
    assert jobs[0].closed
    assert supervisor.get_active_tasks() == []
    assert len(supervisor._tasks) == 0
    assert task(supervisor, "fresh-after-stop", True).state == TaskState.RUNNING


def test_new_request_during_stop_allocates_no_job(supervisor, monkeypatch):
    capsule = task(supervisor, "existing")
    entered, release = threading.Event(), threading.Event()
    allocations = []

    def allocate(**kwargs):
        allocations.append("job")
        return Job()

    def terminate():
        entered.set()
        wait(release)

    monkeypatch.setattr("pluma.core.job_object.WindowsJobObject", allocate)
    capsule.worker_controller = SimpleNamespace(terminate_and_join=terminate, verify_cleanup=lambda: True)
    with ThreadPoolExecutor(max_workers=1) as callers:
        stopping = callers.submit(supervisor.stop_all_active_tasks)
        try:
            wait(entered)
            with pytest.raises(TaskCancelledError):
                supervisor.create_task("rejected-before-resources")
            assert allocations == []
        finally:
            release.set()
        stopping.result(6)


def test_terminal_cleanup_cannot_hold_other_tasks_latch_hostage(supervisor):
    finished, live = task(supervisor, "finishing", True), task(supervisor, "live")
    entered, release = threading.Event(), threading.Event()

    class ClosingJob(Job):
        def close(self):
            entered.set()
            wait(release)
            super().close()

    old_job = finished.job_object
    old_job.close()
    finished.job_object = ClosingJob()
    with ThreadPoolExecutor(max_workers=2) as callers:
        finishing = callers.submit(supervisor.mark_succeeded, finished.task_id)
        try:
            wait(entered)
            stopping = callers.submit(supervisor.stop_all_active_tasks)
            assert live.cancellation_token.wait_for_cancel(3)
            assert live.state == TaskState.STOPPING
            assert not stopping.done()  # latch acknowledged, cleanup still waits
            assert finished.state == TaskState.SUCCEEDED and not finished.stop_latch_set
        finally:
            release.set()
        finishing.result(6)
        assert stopping.result(6) == [live.task_id]
    assert live.state == TaskState.STOPPED


@pytest.mark.parametrize("operation", ["start", "succeed"])
def test_lifecycle_racing_latch_cannot_bypass_stop_claim(supervisor, monkeypatch, operation):
    first, later = task(supervisor, "first"), task(supervisor, "later", operation == "succeed")
    entered, release, start_attempted = threading.Event(), threading.Event(), threading.Event()
    original = later.cancellation_token.cancel

    def cancel(reason=StopReason.USER_STOP):
        result = original(reason)
        entered.set()
        wait(release)
        return result

    def start():
        start_attempted.set()
        if operation == "start":
            supervisor.start_task(later.task_id)
        else:
            supervisor.mark_succeeded(later.task_id)

    monkeypatch.setattr(later.cancellation_token, "cancel", cancel)
    with ThreadPoolExecutor(max_workers=2) as callers:
        stopping = callers.submit(supervisor.stop_all_active_tasks)
        try:
            wait(entered)
            starting = callers.submit(start)
            wait(start_attempted)
        finally:
            release.set()
        with pytest.raises(TaskCancelledError if operation == "start" else InvalidTaskTransition):
            starting.result(6)
        stopping.result(6)
    assert first.state == later.state == TaskState.STOPPED


def test_cleanup_error_does_not_omit_later_tasks_or_leave_global_admission_closed(supervisor):
    first, later = task(supervisor, "failed-cleanup"), task(supervisor, "later")
    observations = []

    def cleanup(task_id):
        observations.append((first.stop_latch_set, later.stop_latch_set))
        if task_id == first.task_id:
            raise RuntimeError("Owned injected resource cleanup failure")
        return []

    supervisor._registry = SimpleNamespace(cleanup_task_resources=cleanup)
    assert supervisor.stop_all_active_tasks() == [first.task_id, later.task_id]
    assert all(all(values) for values in observations)
    assert later.state == TaskState.STOPPED
    assert first.state == TaskState.STOPPED_WITH_RESIDUAL  # P04 now records the cleanup failure
    assert supervisor._global_stop_depth == 0
    assert task(supervisor, "explicit-next", True).state == TaskState.RUNNING


def test_global_state_and_sqlite_agree_for_successful_fixture_cleanup(supervisor, tmp_path):
    with DbConnection(str(tmp_path / "ledger.db")) as db:
        ledger, query = ActivityLedger(db), ActivityQuery(db)
        supervisor._ledger = ledger
        capsules = [task(supervisor, "created"), task(supervisor, "running", True)]
        for capsule in capsules:
            ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id, input_mode="text", command_text="P02 owned fixture"))
        supervisor.stop_all_active_tasks()
        rows = {row["task_id"]: row for row in query.recent_tasks()}
        assert set(rows) == {cap.task_id for cap in capsules}
        for capsule in capsules:
            assert rows[capsule.task_id]["final_state"] == capsule.state.value == "STOPPED"
            assert rows[capsule.task_id]["stop_reason"] == "user_stop"
            assert rows[capsule.task_id]["completed_at"]


def test_empty_repeated_global_stop_allows_next_explicit_command(supervisor):
    assert supervisor.stop_all_active_tasks() == []
    assert supervisor.stop_all_active_tasks() == []
    assert supervisor._global_stop_depth == 0
    assert task(supervisor, "next", True).state == TaskState.RUNNING
