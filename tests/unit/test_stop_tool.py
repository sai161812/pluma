"""Registered STOP uses the existing priority global service, not a tool future."""
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from pluma.core import job_object
from pluma.memory.activity import ActivityQuery
from pluma.tools.registry import ToolArgumentError, WorkerRequest
from pluma.tools.system import execute_stop_current, verify_stop_current
from tests.unit.test_runtime_shutdown import NATIVE_JOB, runtime, task
from tests.unit.test_worker_cancellation import OwnedProbe, await_file


def test_registered_stop_latches_every_task_before_cleanup_without_policy_wait(runtime, monkeypatch):
    first, command = task(runtime, 'other-active'), task(runtime, 'stop-command')
    observed = []
    original = type(first).close_resources
    def close(cap, **kwargs):
        observed.append(first.stop_latch_set and command.stop_latch_set)
        return original(cap, **kwargs)
    monkeypatch.setattr(type(first), 'close_resources', close)
    def forbidden(**kwargs):
        pytest.fail('STOP waited for ordinary policy evaluation.')
    result = runtime.tool_registry.execute('stop_current', {}, command, runtime.ledger,
        policy_engine=SimpleNamespace(evaluate=forbidden))
    assert result.ok and result.data['latch_acknowledged_count'] == 2
    assert runtime.supervisor.join_stop_operations(2)
    assert observed and all(observed)
    for cap in (first, command):
        assert cap.terminal_ready.is_set() and cap.state.value == 'STOPPED'
        assert ActivityQuery(runtime.db).task_by_id(cap.task_id)['stop_reason'] == 'user_stop'
    assert len(ActivityQuery(runtime.db).actions_for_task(command.task_id)) == 1


def test_registered_stop_interrupts_native_worker_without_counting_ack_as_cleanup(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    active, command = task(runtime, 'owned-busy'), task(runtime, 'stop-command')
    worker = runtime.tool_registry.get_worker(active.task_id)
    active.worker_controller = worker
    active._tool_registry = runtime.tool_registry
    with ThreadPoolExecutor(1) as pool:
        call = pool.submit(worker.execute_call, OwnedProbe(str(tmp_path)), {},
            WorkerRequest(active.task_id, 'worker_probe', {}, 10), 10,
            job_object=active.job_object, cancellation_token=active.cancellation_token)
        try:
            await_file(tmp_path / 'entered', call)
            result = runtime.tool_registry.execute('stop_current', {}, command, runtime.ledger)
            assert result.ok and active.stop_latch_set and command.stop_latch_set
            assert call.result(3)[0] == 'cancelled'
            assert runtime.supervisor.join_stop_operations(3)
            assert worker.verify_cleanup() and not (tmp_path / 'late').exists()
            assert result.verified == verify_stop_current(result).ok
            assert result.data['stop_contract'] == 'pluma.stop.v1'
        finally:
            runtime.supervisor.stop_all_active_tasks()


def test_unconfigured_stop_service_refuses_false_success():
    result = execute_stop_current({})
    assert not result.ok and not result.verified and result.error_code == 'STOP_SERVICE_UNAVAILABLE'


@pytest.mark.parametrize('args', [{'reason': 'task_timeout'}, {'scope': 'all'}])
def test_stop_arguments_validated_before_latching(runtime, args):
    cap = task(runtime)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('stop_current', args, cap, runtime.ledger)
    assert not cap.stop_latch_set
