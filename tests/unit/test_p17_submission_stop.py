"""P17 STOP fences an uncertain UI request before or during resident admission."""
import threading
from uuid import uuid4

import pytest

from tests.unit.test_ipc_request_contract import resident_fixture
from pluma.memory.activity import ActivityQuery


def submit(request_id):
    return dict(protocol_version=1, message_type="submit_text", request_id=request_id, text="owned queued fixture")


def stop(request_id):
    return dict(protocol_version=1, message_type="stop", request_id=str(uuid4()), submission_request_id=request_id)


def test_stop_before_queued_admission_never_starts_executor(resident_fixture):
    core, _, supervisor = resident_fixture
    core.orchestrator = object()  # admission must refuse before any execute lookup
    request = str(uuid4())
    reply = core.handle_ipc_command(stop(request))
    assert reply["message_type"] == "stop_ack"
    refused = core.handle_ipc_command(submit(request))
    assert refused["accepted"] is False
    assert refused["error_code"] == "SUBMISSION_STOPPED"
    assert not supervisor.get_active_tasks()
    assert not core._submission_threads


def test_stop_does_not_wait_for_submission_history_io(resident_fixture, monkeypatch):
    core, ledger, supervisor = resident_fixture
    core.orchestrator = object()
    entered, release = threading.Event(), threading.Event()
    original = ledger.insert_task

    def blocked(record):
        entered.set()
        assert release.wait(3)
        original(record)

    monkeypatch.setattr(ledger, "insert_task", blocked)
    request = str(uuid4())
    result = []
    worker = threading.Thread(target=lambda: result.append(core.handle_ipc_command(submit(request))))
    worker.start()
    try:
        assert entered.wait(2)
        # If this waits for the submission lock, release remains blocked and
        # the original reproduction cannot return before the fixture deadline.
        reply = core.handle_ipc_command(stop(request))
        assert reply["message_type"] == "stop_ack"
        assert not release.is_set()
    finally:
        release.set(); worker.join(3)
    assert not worker.is_alive()
    assert result[0]["accepted"] is False
    assert result[0]["error_code"] == "SUBMISSION_STOPPED"
    assert not core._submission_threads
    row = ActivityQuery(ledger._db).task_by_request_id(request)
    capsule = supervisor.get_task(row["task_id"])
    # STOP interrupted the first history insert. Keep the resulting residual
    # history evidence rather than inventing a clean cancellation outcome.
    assert row["final_state"] == capsule.state.value == "STOPPED_WITH_RESIDUAL"
    assert capsule.terminal_ready.is_set()
    assert not supervisor.get_active_tasks()


@pytest.mark.parametrize("value", ["bad", "", 1, "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"])
def test_submission_fence_validates_identity_before_stop(resident_fixture, value):
    core, _, _ = resident_fixture
    assert core.handle_ipc_command(stop(value))["error_code"] == "INVALID_REQUEST"


def test_submission_fence_capacity_never_evicts_stopped_identity(resident_fixture):
    core, _, _ = resident_fixture
    core.orchestrator = object()
    core._submission_state()
    stopped = {str(uuid4()) for _ in range(256)}
    core._stopped_submission_ids.update(stopped)
    assert core.handle_ipc_command(stop(str(uuid4())))["message_type"] == "stop_ack"
    assert core._stopped_submission_ids == stopped
    assert core._submission_admission_paused is True
    assert core.handle_ipc_command(submit(str(uuid4())))["accepted"] is False


def test_submission_fence_cannot_be_combined_with_unrelated_task_scope(resident_fixture):
    core, _, _ = resident_fixture
    request = stop(str(uuid4()))
    request["task_id"] = str(uuid4())
    assert core.handle_ipc_command(request)["error_code"] == "INVALID_REQUEST"
