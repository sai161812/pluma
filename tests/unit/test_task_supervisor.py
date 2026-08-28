"""tests.unit.test_task_supervisor — Tests for TaskSupervisor and STOP sequence."""

import subprocess
import sys
import threading
import time

import pytest

from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.ownership import OwnershipRegistry
from pluma.core.task_supervisor import TaskState, TaskSupervisor


@pytest.fixture
def supervisor() -> TaskSupervisor:
    registry = OwnershipRegistry()
    return TaskSupervisor(ownership_registry=registry)


def test_create_and_start_task(supervisor: TaskSupervisor) -> None:
    capsule = supervisor.create_task("req-123")
    assert capsule.state == TaskState.CREATED
    assert capsule.job_object is not None

    supervisor.start_task(capsule.task_id)
    assert capsule.state == TaskState.RUNNING


def test_stop_cancels_long_running_task(supervisor: TaskSupervisor) -> None:
    """Gate test: STOP cancels a dummy long-running task."""
    capsule = supervisor.create_task("req-234")
    supervisor.start_task(capsule.task_id)

    # Spawn the dummy long-running task inside the job object
    proc = subprocess.Popen([sys.executable, "tests/fixtures/fixture_app.py", "spin"])
    try:
        if capsule.job_object:
            capsule.job_object.assign_process(proc)

        assert proc.poll() is None

        # Issue STOP
        supervisor.stop_task(capsule.task_id)

        # The state should be STOPPED immediately
        assert capsule.state == TaskState.STOPPED
        assert capsule.stop_latch_set is True

        # Process should be terminated by the Job Object boundary
        time.sleep(0.2)
        assert proc.poll() is not None

    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def test_stop_blocks_subsequent_steps(supervisor: TaskSupervisor) -> None:
    """Gate test: STOP prevents a queued next step from starting."""
    capsule = supervisor.create_task("req-345")
    supervisor.start_task(capsule.task_id)

    supervisor.stop_task(capsule.task_id)

    # Latch is set
    assert capsule.cancellation_token.is_cancelled
    
    # If a worker tries to check cancellation before next step, it raises
    with pytest.raises(TaskCancelledError):
        capsule.cancellation_token.raise_if_cancelled()


def test_stop_latch_latency(supervisor: TaskSupervisor) -> None:
    """Gate test: STOP latch latency target <100ms."""
    capsule = supervisor.create_task("req-456")
    supervisor.start_task(capsule.task_id)

    # Must execute in < 100ms
    t0 = time.perf_counter()
    supervisor.stop_task(capsule.task_id, grace_s=0.0)
    duration_ms = (time.perf_counter() - t0) * 1000.0

    assert capsule.stop_latch_set is True
    assert duration_ms < 100.0, f"STOP latency too high: {duration_ms}ms"


def test_stop_all_active_tasks(supervisor: TaskSupervisor) -> None:
    t1 = supervisor.create_task("req-A")
    t2 = supervisor.create_task("req-B")
    
    supervisor.start_task(t1.task_id)
    supervisor.start_task(t2.task_id)
    
    supervisor.stop_all_active_tasks()
    
    assert t1.state == TaskState.STOPPED
    assert t2.state == TaskState.STOPPED
