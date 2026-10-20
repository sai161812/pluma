"""Activity reads the actual executor ledger in an owned native worker."""
from types import SimpleNamespace

import pytest

from pluma.core import job_object
from pluma.core.cancellation import TaskCancelledError
from pluma.memory.activity import ActivityQuery, TaskRecord
from pluma.tools.registry import ToolArgumentError
from pluma.tools.system import execute_show_activity, verify_activity
from tests.unit.test_runtime_shutdown import NATIVE_JOB, runtime, task


def test_activity_native_worker_reads_executor_ledger_and_redacts(runtime, monkeypatch, tmp_path):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    monkeypatch.setenv('PLUMA_DB_PATH', str(tmp_path / 'must-not-create.db'))
    runtime.ledger.insert_task(TaskRecord(task_id='older-owned-task', request_id='prior',
        input_mode='voice', command_text='Owned prior command'))
    # Also defend old records written without current ledger redaction.
    runtime.db.execute_write('UPDATE tasks SET command_text=? WHERE task_id=?',
        ('password=private-history-fixture', 'older-owned-task'))
    cap = task(runtime, 'read-owned-history')
    result = runtime.tool_registry.execute('show_activity', {'limit': 5}, cap, runtime.ledger)
    assert result.ok and result.verified
    rows = {r['task_id']: r for r in result.data['records']}
    assert set(rows) == {'older-owned-task', cap.task_id}
    assert rows['older-owned-task']['input_mode'] == 'voice'
    assert 'private-history-fixture' not in str(result)
    assert not (tmp_path / 'must-not-create.db').exists()
    worker = cap.worker_controller
    assert worker.worker_identity['ownership'] == 'PLUMA_CREATED'
    actions = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(actions) == 1 and actions[0]['verified']
    assert 'private-history-fixture' not in str(actions)
    assert runtime.close(3).complete and worker.verify_cleanup()


def test_empty_ledger_is_verified_but_missing_ledger_is_failure(runtime):
    result = execute_show_activity({'limit': 3}, SimpleNamespace(storage_path=str(runtime.paths.db_path)))
    assert result.ok and result.verified and result.data['records'] == []
    missing = runtime.paths.db_path.parent / 'absent.db'
    result = execute_show_activity({}, SimpleNamespace(storage_path=str(missing)))
    assert not result.ok and result.error_code == 'ACTIVITY_READ_FAILED'
    assert not missing.exists()


def test_corrupt_storage_does_not_become_empty_success(tmp_path):
    path = tmp_path / 'owned-corrupt.db'
    path.write_bytes(b'not sqlite')
    result = execute_show_activity({}, SimpleNamespace(storage_path=str(path)))
    assert not result.ok and not result.verified and result.data == {}


@pytest.mark.parametrize('args', [{'limit': True}, {'limit': '3'}, {'limit': 101}, {'storage_path': 'other.db'}])
def test_activity_rejects_malformed_or_planner_selected_storage(runtime, args):
    cap = task(runtime)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('show_activity', args, cap, runtime.ledger)
    assert cap.worker_controller is None


def test_activity_stop_prevents_owned_worker_dispatch(runtime):
    cap = task(runtime)
    cap.cancellation_token.cancel()
    with pytest.raises(TaskCancelledError):
        runtime.tool_registry.execute('show_activity', {}, cap, runtime.ledger)
    assert cap.worker_controller is None


def test_activity_long_commands_are_bounded_and_marked(runtime):
    runtime.ledger.insert_task(TaskRecord(task_id='long-command', request_id='prior',
        input_mode='text', command_text='owned ' * 1000))
    result = execute_show_activity({}, SimpleNamespace(storage_path=str(runtime.paths.db_path)))
    assert result.ok and result.data['records'][0]['command_truncated']
    assert len(result.data['records'][0]['command']) == 4096
    assert verify_activity(result).ok
    assert not verify_activity(result.model_copy(update={'data': {'count': 1, 'limit': 1, 'records': []}})).ok
