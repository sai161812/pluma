"""P04 cleanup readback, retention and persisted residual facts.

Owned files/processes/jobs only. Inert doubles explicitly model readback; their
returns are not native acceptance. No desktop, capture or model is activated.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pluma.config.paths import PlumaPaths
from pluma.core.cleanup import CleanupEvidence, latest_unresolved
from pluma.core import job_object, ownership
from pluma.core.cancellation import TaskCancelledError
from pluma.core.job_object import JobObjectError, WindowsJobObject
from pluma.core.ownership import OwnershipRegistry
from pluma.core.task_supervisor import ResourceOwnership, TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery, TaskRecord, ActionRecord, UndoRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolSpec, VerifyResult
from pluma.rollback.engine import RollbackEngine
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.registry import ToolRegistry
from tests.unit.test_worker_cancellation import EmptyArgs, OwnedProbe, await_file


class Job:
    """Inert owned job with separately observable failure/readback state."""
    def __init__(self, **kwargs):
        self.active = 0
        self.closed = False
        self.fail = None
        self.terminated = 0

    def terminate(self, **kwargs):
        self.terminated += 1
        if self.fail == "terminate":
            raise OSError("password=not-for-ledger")

    def active_process_count(self):
        if self.fail == "query":
            raise OSError("secret=not-for-ledger")
        return self.active

    def close(self):
        if self.fail == "close":
            raise OSError("token=not-for-ledger")
        self.closed = True

    @property
    def is_closed(self):
        return self.closed


class Worker:
    def __init__(self, task_id, *, absent=False, fail=False):
        self.absent, self.fail = absent, fail
        self.task_id = task_id
        self.worker_identity = {"task_id": task_id, "pid": 123, "creation_time": 456,
                                "command_class": "owned_fixture", "ownership": "PLUMA_CREATED"}
        self.calls = 0
        self.cleanup_evidence = []
        self._proc = None

    def terminate_and_join(self):
        self.calls += 1
        if self.fail:
            raise RuntimeError("api_key=not-for-ledger")

    def dispose_owned_worker(self):
        self.terminate_and_join()

    def verify_cleanup(self):
        return self.absent


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    monkeypatch.setattr(job_object, "WindowsJobObject", Job)
    result = TaskSupervisor(paths=PlumaPaths(tmp_path / "local", tmp_path / "roaming"),
                            ownership_registry=OwnershipRegistry())
    yield result
    for capsule in result._tasks.values():
        if isinstance(capsule.job_object, Job):
            capsule.job_object.fail = None
            capsule.job_object.active = 0
        if isinstance(capsule.worker_controller, Worker):
            capsule.worker_controller.fail = False
            capsule.worker_controller.absent = True
        capsule.close_resources(stopping=True)


def stop(supervisor, capsule):
    supervisor.stop_task(capsule.task_id, grace_s=0)


def test_failed_termination_retains_identity_and_blocks_rollback(supervisor, tmp_path):
    capsule = supervisor.create_task("failed-worker")
    worker = Worker(capsule.task_id, fail=True)
    capsule.worker_controller = worker
    path = tmp_path / "owned"
    path.write_text("pre-state remains")
    capsule.register_owned_resource("temp_file", ResourceOwnership.PLUMA_CREATED, str(path))
    capsule.undo_stack.append({"action": "owned_probe"})
    engine = Mock()
    supervisor._rollback_engine = engine
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert capsule.worker_controller is worker and capsule.cleanup_pending
    assert path.read_text() == "pre-state remains" and capsule.undo_stack
    engine.rollback_task.assert_not_called()
    check = next(item for item in capsule.cleanup_evidence if item.kind == "worker")
    assert check.identity["pid"] == 123 and check.identity["creation_time"] == 456
    assert check.errors == ["WORKER_TERMINATION_FAILED"]
    assert "not-for-ledger" not in capsule.model_dump_json(exclude={"cancellation_token"})


@pytest.mark.parametrize("fail", [False, True])
def test_only_positive_worker_readback_allows_release(supervisor, fail):
    capsule = supervisor.create_task("worker-readback")
    worker = Worker(capsule.task_id, absent=True, fail=fail)
    capsule.worker_controller = worker
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED and capsule.worker_controller is None
    check = next(item for item in capsule.cleanup_evidence if item.kind == "worker")
    assert check.verified and bool(check.errors) == fail


def test_successful_return_without_readback_is_residual(supervisor):
    capsule = supervisor.create_task("unknown-worker")
    capsule.worker_controller = Mock()  # truthy mocks must never establish absence
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert capsule.worker_controller is not None


@pytest.mark.parametrize("failure", ["query", "close", "live"])
def test_failed_job_cleanup_retains_handle_for_retry(supervisor, failure):
    capsule = supervisor.create_task("job-failure")
    job = capsule.job_object
    job.fail = failure
    if failure == "live":
        job.active = 1
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert capsule.job_object is job and not job.closed
    job.fail, job.active = None, 0
    capsule.close_resources(stopping=True)
    assert job.closed and capsule.job_object is None
    assert any(item.verified and item.kind == "job" for item in capsule.cleanup_evidence)
    # A later handle retry alone does not claim deferred rollback was done.
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL


def test_job_termination_error_can_resolve_via_empty_readback(supervisor):
    capsule = supervisor.create_task("job-fallback")
    capsule.job_object.fail = "terminate"
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED
    check = next(item for item in capsule.cleanup_evidence if item.kind == "job")
    assert check.verified and check.errors == ["JOB_TERMINATION_FAILED"]


def test_native_job_termination_and_close_failures_are_not_silenced(monkeypatch):
    job = WindowsJobObject()
    try:
        with monkeypatch.context() as patch:
            patch.setattr(job_object.kernel32, "TerminateJobObject", lambda *a: False)
            with pytest.raises(JobObjectError):
                job.terminate()
        assert job.active_process_count() == 0
        with monkeypatch.context() as patch:
            patch.setattr(job_object.kernel32, "CloseHandle", lambda *a: False)
            with pytest.raises(JobObjectError):
                job.close()
            assert not job.is_closed
    finally:
        job.close()


def test_registry_retains_failed_task_and_idle_controllers():
    registry = ToolRegistry()
    failed = Worker("failed", fail=True)
    idle = Worker("idle", fail=True)
    registry._worker_controllers["failed"] = failed
    registry._idle_workers.append(idle)
    try:
        with pytest.raises(RuntimeError):
            registry.cleanup_task("failed")
        assert registry._worker_controllers["failed"] is failed
        with pytest.raises(RuntimeError):
            registry.get_worker("new")
        assert registry._idle_workers == [idle]
        with pytest.raises(RuntimeError):
            registry.close()
        assert registry._worker_controllers["failed"] is failed and registry._idle_workers == [idle]
    finally:
        failed.fail = idle.fail = False
        failed.absent = idle.absent = True
        registry.close()
    assert not registry._worker_controllers and not registry._idle_workers


@pytest.mark.parametrize("no_op", [False, True])
def test_temp_cleanup_failure_requires_actual_absence(supervisor, tmp_path, monkeypatch, no_op):
    capsule = supervisor.create_task("temp-failure")
    path = tmp_path / "owned-temp"
    path.mkdir()
    resource = supervisor._registry.register_resource(capsule.task_id, "temp_dir", ResourceOwnership.PLUMA_CREATED, str(path))
    def remove(path):
        if not no_op:
            raise PermissionError("secret=not-for-ledger")
    monkeypatch.setattr(ownership.shutil, "rmtree", remove)
    stop(supervisor, capsule)
    assert path.exists() and resource.released_at is None
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert any(item.resource_id == resource.resource_id and not item.verified for item in capsule.cleanup_evidence)


@pytest.mark.parametrize("change", ["content", "identity", "missing_identity"])
def test_changed_temporary_file_is_preserved(supervisor, tmp_path, change):
    capsule = supervisor.create_task("changed-temp")
    path = tmp_path / "temp.txt"
    if change != "missing_identity":
        path.write_text("owned initial")
    resource = supervisor._registry.register_resource(capsule.task_id, "temp_file", ResourceOwnership.PLUMA_CREATED, str(path))
    if change == "identity":
        path.rename(tmp_path / "original.txt")
    path.write_text("changed content must remain")
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert path.read_text() == "changed content must remain" and resource.released_at is None


def test_owned_temp_absence_is_read_back_and_released(supervisor, tmp_path):
    capsule = supervisor.create_task("temp-success")
    path = tmp_path / "temp.txt"
    path.write_text("owned")
    resource = supervisor._registry.register_resource(capsule.task_id, "temp_file", ResourceOwnership.PLUMA_CREATED, str(path))
    stop(supervisor, capsule)
    assert not path.exists() and resource.released_at is not None
    assert capsule.state == TaskState.STOPPED
    path.write_text("new user file after ownership release")
    assert supervisor._registry.cleanup_task_resources(capsule.task_id)[0].verified
    assert path.read_text() == "new user file after ownership release"


def test_preexisting_files_and_job_handles_are_untouched(supervisor, tmp_path):
    capsule = supervisor.create_task("preexisting")
    path = tmp_path / "user.txt"
    path.write_text("user content")
    user_job = Job()
    capsule.register_owned_resource("temp_file", ResourceOwnership.PREEXISTING, str(path), {"persistent_job": user_job})
    computed = supervisor._paths.task_temp_dir(capsule.task_id)
    computed.mkdir(parents=True)
    (computed / "user-data").touch()
    stop(supervisor, capsule)
    assert path.read_text() == "user content" and (computed / "user-data").exists()
    assert user_job.terminated == 0 and not user_job.closed
    assert capsule.state == TaskState.STOPPED


def test_existing_task_directory_cannot_be_claimed(supervisor, tmp_path, monkeypatch):
    monkeypatch.setattr("pluma.config.paths.get_paths", lambda: supervisor._paths)
    path = supervisor._paths.task_temp_dir("existing")
    path.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        supervisor._registry.create_task_temp_dir("existing")
    assert path.exists() and supervisor._registry.get_owned_resources("existing") == []


def test_partial_real_file_rollback_records_residual_and_preserves_conflict(supervisor, tmp_path):
    capsule = supervisor.create_task("partial-rollback")
    restored, moved = tmp_path / "before.txt", tmp_path / "after.txt"
    moved.write_text("completed move")
    original, effect = tmp_path / "conflict-before.txt", tmp_path / "conflict-after.txt"
    original.write_text("new user content")
    effect.write_text("effect remains")
    good = {"action": "rename_file", "original_path": str(restored), "new_path": str(moved)}
    bad = {"action": "rename_file", "original_path": str(original), "new_path": str(effect)}
    capsule.undo_stack.extend([good, bad])
    backup = tmp_path / "undo-backup"
    backup.write_text("pre-state must remain")
    capsule.register_owned_resource("temp_file", ResourceOwnership.PLUMA_CREATED, str(backup))
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert restored.read_text() == "completed move" and not moved.exists()
    assert original.read_text() == "new user content" and effect.read_text() == "effect remains"
    assert capsule.undo_stack == [bad]
    assert backup.read_text() == "pre-state must remain"
    result = next(item for item in capsule.cleanup_evidence if item.kind == "rollback")
    assert result.identity["attempted"] == 2 and result.identity["succeeded"] == 1 and result.identity["failed"] == 1


def test_non_undoable_commit_is_never_claimed_reversed(supervisor):
    capsule = supervisor.create_task("external-effect")
    capsule.undo_stack.append({"action": "external_commit", "non_undoable": True})
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL and capsule.undo_stack
    assert any(item.code == "NON_UNDOABLE_EFFECT_REMAINS" for item in latest_unresolved(capsule.cleanup_evidence))


def test_terminal_pruning_keeps_failed_worker_identity(supervisor):
    supervisor._max_retained_terminal_tasks = 0
    capsule = supervisor.create_task("retain")
    worker = Worker(capsule.task_id, fail=True)
    capsule.worker_controller = worker
    stop(supervisor, capsule)
    assert supervisor.prune_terminal_tasks(keep_count=0) == 0
    assert supervisor.get_task(capsule.task_id).worker_controller is worker


def test_success_cannot_discard_worker_failure_or_temporary_prestate(supervisor, tmp_path):
    capsule = supervisor.create_task("success-cleanup-failure")
    supervisor.start_task(capsule.task_id)
    worker = Worker(capsule.task_id, fail=True)
    capsule.worker_controller = worker
    path = tmp_path / "prestate"
    path.write_text("retain")
    capsule.register_owned_resource("temp_file", ResourceOwnership.PLUMA_CREATED, str(path))
    supervisor.mark_succeeded(capsule.task_id)
    assert capsule.state == TaskState.FAILED and capsule.worker_controller is worker
    assert path.read_text() == "retain" and capsule.cleanup_pending
    assert supervisor.prune_terminal_tasks(0) == 0


def test_registered_live_process_is_unresolved_and_replacement_pid_is_read_only(supervisor):
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
    capsule = supervisor.create_task("live-owned-resource")
    try:
        resource = supervisor._registry.register_subprocess(capsule.task_id, proc.pid, ResourceOwnership.PLUMA_CREATED, "owned_fixture")
        creation = resource.metadata["creation_time"]
        assert ownership.subprocess_absent(proc.pid, creation + 1)  # old identity absent; replacement untouched
        assert proc.poll() is None
        stop(supervisor, capsule)
        assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL and resource.released_at is None
        assert proc.poll() is None  # no name/PID-based forced cleanup outside an owned job
    finally:
        proc.kill()
        proc.wait(3)
    checks = supervisor._registry.cleanup_task_resources(capsule.task_id)
    assert checks[0].verified and resource.released_at is not None


def test_repeated_stop_does_not_replace_residual_report_with_empty_success(supervisor):
    capsule = supervisor.create_task("repeat-residual")
    worker = Worker(capsule.task_id, fail=True)
    capsule.worker_controller = worker
    stop(supervisor, capsule)
    before = [item.model_dump() for item in capsule.cleanup_evidence]
    stop(supervisor, capsule)
    assert worker.calls == 1 and capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert [item.model_dump() for item in capsule.cleanup_evidence] == before


def test_no_op_snapshot_clear_retains_registry(supervisor):
    capsule = supervisor.create_task("snapshot-failure")
    class Snapshots:
        def clear(self): pass
        def __len__(self): return 1
    snapshots = Snapshots()
    capsule.snapshot_registry = snapshots
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert capsule.snapshot_registry is snapshots


def test_cancelled_preparation_keeps_failed_unpublished_cleanup(supervisor, monkeypatch, tmp_path):
    jobs = []
    class PreparingJob(Job):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.fail = "query"
            jobs.append(self)
            supervisor.stop_all_active_tasks()  # cross the captured publication generation
    monkeypatch.setattr(job_object, "WindowsJobObject", PreparingJob)
    path = str(tmp_path / "preparation.db")
    with DbConnection(path) as db:
        supervisor._ledger = ActivityLedger(db)
        with pytest.raises(TaskCancelledError):
            supervisor.create_task("cancelled-preparation")
    supervisor._ledger = None
    assert not supervisor._tasks and len(supervisor._retained_preparations) == 1
    capsule = next(iter(supervisor._retained_preparations.values()))
    assert capsule.job_object is jobs[0] and capsule.cleanup_pending
    with DbConnection(path) as db:
        query = ActivityQuery(db)
        assert query.task_by_id(capsule.task_id) is None
        report = query.cleanup_report_for_task(capsule.task_id)
        assert report and not json.loads(report["metadata_json"])["complete"]
    jobs[0].fail = None
    capsule.close_resources(stopping=True)
    assert jobs[0].closed


def test_residual_report_survives_sqlite_reopen_with_redacted_errors(supervisor, tmp_path):
    path = str(tmp_path / "ledger.db")
    with DbConnection(path) as db:
        supervisor._ledger = ActivityLedger(db)
        capsule = supervisor.create_task("persist-residual")
        supervisor._ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id,
                                                input_mode="text", command_text="Owned fixture"))
        capsule.worker_controller = Worker(capsule.task_id, fail=True)
        temp_path = tmp_path / "deferred-prestate"
        temp_path.write_text("preserve")
        resource = supervisor._registry.register_resource(capsule.task_id, "temp_file", ResourceOwnership.PLUMA_CREATED, str(temp_path))
        stop(supervisor, capsule)
    supervisor._ledger = None
    with DbConnection(path) as db:
        query = ActivityQuery(db)
        assert query.task_by_id(capsule.task_id)["final_state"] == "STOPPED_WITH_RESIDUAL"
        rows = query.resources_for_task(capsule.task_id)
        report = json.loads(rows[0]["metadata_json"])
        assert not report["complete"] and rows[0]["released_at"] is None
        worker = next(item for item in report["entries"] if item["kind"] == "worker")
        assert worker["identity"]["pid"] == 123 and worker["identity"]["creation_time"] == 456
        deferred = next(item for item in report["entries"] if item["resource_id"] == resource.resource_id)
        assert deferred["identity"]["temp_identity"] == resource.metadata["cleanup_identity"]
        assert deferred["identity"]["external_id"] == str(temp_path) and temp_path.read_text() == "preserve"
        assert "not-for-ledger" not in json.dumps(report)


def test_cleanup_persistence_failure_is_retained(supervisor):
    capsule = supervisor.create_task("ledger-failure")
    supervisor._ledger = SimpleNamespace(record_cleanup=Mock(side_effect=OSError("secret=not-for-ledger")), update_task=Mock())
    stop(supervisor, capsule)
    assert capsule.state == TaskState.STOPPED_WITH_RESIDUAL
    assert any(item.kind == "persistence" for item in latest_unresolved(capsule.cleanup_evidence))
    assert supervisor.prune_terminal_tasks(0) == 0


def test_cleanup_persistence_checks_readback_and_redacts(tmp_path, monkeypatch):
    with DbConnection(str(tmp_path / "ledger.db")) as db:
        ledger = ActivityLedger(db)
        ledger.insert_task(TaskRecord(task_id="fixture", request_id="fixture", input_mode="text", command_text="Owned fixture"))
        check = CleanupEvidence(resource_id="fixture", kind="worker", code="WORKER_CLEANUP_UNVERIFIED",
                                identity={"password": "not-for-ledger"})
        ledger.record_cleanup("fixture", [check.model_dump()])
        raw = ActivityQuery(db).resources_for_task("fixture")[0]["metadata_json"]
        assert "not-for-ledger" not in raw and "[REDACTED]" in raw
        monkeypatch.setattr(db, "execute_read_one", lambda *a: None)
        with pytest.raises(RuntimeError, match="readback"):
            ledger.record_cleanup("fixture", [check.model_dump()])


def test_cleanup_write_acknowledgement_has_a_bound():
    db = DbConnection(":memory:")
    db._open = True  # intentionally no writer: no hidden worker is launched
    began = time.monotonic()
    try:
        with pytest.raises(TimeoutError):
            db.execute_write("SELECT 1", timeout_s=0.01)
        with pytest.raises(TimeoutError):
            db.execute_transaction([("SELECT 1", ())], timeout_s=0.01)
        assert time.monotonic() - began < 0.2
    finally:
        db._open = False


@pytest.mark.parametrize("action", ["move_file", "rename_file", "create_folder", "set_volume", "mute"])
def test_rollback_no_op_success_is_rejected(tmp_path, monkeypatch, action):
    from pluma.rollback import recipes as module
    from pluma.tools import audio
    before, after = tmp_path / "before", tmp_path / "after"
    after.write_text("effect")
    if action == "move_file":
        monkeypatch.setattr(module.shutil, "move", lambda *a: None)
        undo = {"source": str(before), "destination": str(after)}
    elif action == "rename_file":
        monkeypatch.setattr(Path, "rename", lambda *a: None)
        undo = {"original_path": str(before), "new_path": str(after)}
    elif action == "create_folder":
        before.mkdir()
        monkeypatch.setattr(Path, "rmdir", lambda *a: None)
        undo = {"path": str(before), "existed_before": False}
    else:
        monkeypatch.setattr(audio, "_set_audio_endpoint_volume", lambda **kw: True)
        monkeypatch.setattr(audio, "_get_audio_endpoint_volume", lambda: {"volume": 75, "muted": True})
        undo = {"previous_volume": 20, "previous_muted": False}
    assert not RollbackRecipes().apply(action, undo).ok


def test_database_rollback_consumes_only_matching_memory_prestate(tmp_path):
    with DbConnection(str(tmp_path / "rollback.db")) as db:
        ledger = ActivityLedger(db)
        ledger.insert_task(TaskRecord(task_id="fixture", request_id="fixture", input_mode="text", command_text="Owned fixture"))
        before, after = tmp_path / "before", tmp_path / "after"
        after.write_text("owned effect")
        undo = {"action": "rename_file", "original_path": str(before), "new_path": str(after)}
        action = ledger.insert_action(ActionRecord(task_id="fixture", step_index=0, tool="rename_file", args_raw={}, risk="MEDIUM"))
        ledger.insert_undo_record(UndoRecord(action_row_id=action, undo_data=undo))
        remaining = [dict(undo), {"action": "unrecorded_prestate"}]
        result = RollbackEngine(ledger=ledger).rollback_task("fixture", memory_undo_stack=remaining)
        assert result.all_ok and remaining == [{"action": "unrecorded_prestate"}]
        assert before.read_text() == "owned effect" and not after.exists()
        assert not ActivityQuery(db).available_undo_records_for_task("fixture")


def test_undo_query_failure_is_not_an_empty_success():
    query = SimpleNamespace(available_undo_records_for_task=Mock(side_effect=OSError("not-for-ledger")))
    result = RollbackEngine(query=query).rollback_task("fixture")
    assert not result.all_ok and result.has_residual
    assert result.step_results[0].error == "UNDO_QUERY_FAILED"
    assert result.factual_summary == "Rollback records could not be verified. Residual effects are unknown."


def _close_owned_cleanup_fixture(registry, capsule, child_handle, unrelated):
    """Attempt every owned teardown even when an earlier owner rejects close."""
    import _winapi
    try:
        registry.close()
    finally:
        try:
            capsule.close_resources(stopping=True)
        finally:
            try:
                if child_handle is not None:
                    _winapi.CloseHandle(child_handle)
            finally:
                try:
                    unrelated.kill()
                finally:
                    unrelated.wait(3)


def test_fixture_close_failure_still_drains_other_owned_resources():
    calls = []
    def fail():
        calls.append('registry')
        raise RuntimeError('Injected retained cleanup')
    capsule = SimpleNamespace(close_resources=lambda **kwargs: calls.append('capsule'))
    process = SimpleNamespace(kill=lambda: calls.append('kill'), wait=lambda timeout: calls.append('wait'))
    with pytest.raises(RuntimeError, match='Injected retained cleanup'):
        _close_owned_cleanup_fixture(SimpleNamespace(close=fail), capsule, None, process)
    assert calls == ['registry', 'capsule', 'kill', 'wait']


def test_real_supervisor_cleanup_reads_worker_and_descendant_absence(tmp_path):
    import _winapi
    from tests.fixtures.policy import owned_fixture_policy
    supervisor = TaskSupervisor(paths=PlumaPaths(tmp_path / "local", tmp_path / "roaming"))
    capsule = supervisor.create_task("real-owned-cleanup")
    registry = ToolRegistry(policy_engine=owned_fixture_policy('worker_probe'))
    registry.register(ToolSpec(name="worker_probe", description="Owned fixture", args_schema=EmptyArgs,
                              risk_class=RiskClass.HIGH, timeout_s=30, executor=OwnedProbe(str(tmp_path), descendant=True),
                              verifier=lambda result: VerifyResult(ok=False, method="state", detail="Late marker absent.")))
    child_handle = None
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        with DbConnection(str(tmp_path / "ledger.db")) as db:
            supervisor._ledger = ActivityLedger(db)
            supervisor._ledger.insert_task(TaskRecord(task_id=capsule.task_id, request_id=capsule.request_id,
                                                    input_mode="text", command_text="Owned fixture"))
            with ThreadPoolExecutor(1) as pool:
                executing = pool.submit(registry.execute, "worker_probe", {}, capsule, ledger=supervisor._ledger)
                await_file(tmp_path / "entered", executing)
                worker = capsule.worker_controller
                proc = worker._proc
                child_handle = _winapi.OpenProcess(0x100000, False, int((tmp_path / "child").read_text()))
                stop(supervisor, capsule)
                result = executing.result(2)
            assert not result.ok and not result.verified and result.error_code == "TASK_CANCELLED"
            assert capsule.state == TaskState.STOPPED and not capsule.cleanup_pending
            assert capsule.worker_controller is None and capsule.job_object is None
            assert not proc.is_alive() and worker.verify_cleanup()
            assert _winapi.WaitForSingleObject(child_handle, 1000) == _winapi.WAIT_OBJECT_0
            assert unrelated.poll() is None and not (tmp_path / "late").exists()
            query = ActivityQuery(db)
            assert query.task_by_id(capsule.task_id)["final_state"] == "STOPPED"
            report = json.loads(query.resources_for_task(capsule.task_id)[0]["metadata_json"])
            assert report["complete"] and all(item["verified"] for item in report["entries"])
    finally:
        _close_owned_cleanup_fixture(registry, capsule, child_handle, unrelated)
