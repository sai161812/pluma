"""Versioned resident submit/ack/readback tests with an owned in-memory ledger."""
import threading
from collections import OrderedDict
from types import SimpleNamespace

import pytest

from pluma.core.resident import ResidentCore
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection


@pytest.fixture
def resident_fixture():
    db = DbConnection(":memory:")
    db.open()
    ledger = ActivityLedger(db)
    supervisor = TaskSupervisor(ledger=ledger)
    core = ResidentCore.__new__(ResidentCore)
    core.ledger = ledger
    core.supervisor = supervisor
    core.orchestrator = None
    core._submission_lock = threading.RLock()
    core._submission_records = OrderedDict()
    core._submission_threads = {}
    yield core, ledger, supervisor
    for thread in list(core._submission_threads.values()):
        thread.join(timeout=2)
        assert not thread.is_alive()
    db.close()


def _request(request_id, text="safe fixture request"):
    return {"protocol_version": 1, "message_type": "submit_text",
            "request_id": request_id, "text": text}


def _readback(request_id, task_id):
    return {"protocol_version": 1, "message_type": "terminal_readback",
            "request_id": request_id, "task_id": task_id}


def test_versioned_submission_ack_readback_and_duplicate_safety(resident_fixture):
    core, ledger, supervisor = resident_fixture
    entered, release = threading.Event(), threading.Event()

    class FixtureOrchestrator:
        def execute(self, request, capsule):
            supervisor.start_task(capsule.task_id)
            entered.set()
            assert release.wait(2)
            supervisor.finalize_task(capsule.task_id, TaskState.SUCCEEDED)
            return SimpleNamespace(
                final_state=TaskState.SUCCEEDED, completion_verified=True,
                terminal_persisted=True, has_residual=False,
                route=SimpleNamespace(value="FAST"),
                user_message="Fixture result verified.", duration_ms=3.0,
            )

    core.orchestrator = FixtureOrchestrator()
    request_id = "9fb62f64-4eb4-42b3-b268-8c586a90da12"
    ack = core.handle_ipc_command(_request(request_id))
    assert ack["message_type"] == "submission_ack" and ack["accepted"] is True
    task_id = ack["task_id"]
    assert entered.wait(1)
    pending = core.handle_ipc_command(_readback(request_id, task_id))
    assert pending["terminal"] is False
    assert pending["completion_verified"] is False

    assert core.handle_ipc_command(_request(request_id)) == {
        **ack, "message": "The request was already accepted."
    }
    changed = core.handle_ipc_command(_request(request_id, "different request"))
    assert changed["accepted"] is False and changed["error_code"] == "REQUEST_ID_REUSED"

    thread = core._submission_threads[task_id]
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    terminal = core.handle_ipc_command(_readback(request_id, task_id))
    assert terminal["terminal"] is True
    assert terminal["completion_verified"] is True
    assert terminal["terminal_persisted"] is True
    assert terminal["final_state"] == "SUCCEEDED"

    # Simulate a resident restart: durable request IDs are refused rather than
    # risking an automatic replay of a side effect whose caller may have timed out.
    core._submission_records.clear()
    durable = core.handle_ipc_command(_readback(request_id, task_id))
    assert durable["terminal"] is True
    assert durable["terminal_persisted"] is True
    assert durable["completion_verified"] is False
    replay = core.handle_ipc_command(_request(request_id))
    assert replay["accepted"] is False and replay["error_code"] == "REQUEST_ID_REPLAY"


def test_versioned_contract_rejects_unknown_version_and_malformed_fields(resident_fixture):
    core, _, _ = resident_fixture
    unsupported = core.handle_ipc_command({**_request("9fb62f64-4eb4-42b3-b268-8c586a90da12"), "protocol_version": 2})
    assert unsupported["error_code"] == "UNSUPPORTED_PROTOCOL_VERSION"
    malformed = core.handle_ipc_command({**_request("not-a-uuid"), "extra": "refuse"})
    assert malformed["error_code"] == "INVALID_REQUEST"


def test_inflight_submission_does_not_block_independent_stop(resident_fixture):
    core, _, supervisor = resident_fixture
    entered, release = threading.Event(), threading.Event()

    class BlockingOrchestrator:
        def execute(self, request, capsule):
            supervisor.start_task(capsule.task_id)
            entered.set()
            release.wait(2)
            capsule.cancellation_token.raise_if_cancelled()
            raise AssertionError("STOP did not latch before the executor resumed")

    core.orchestrator = BlockingOrchestrator()
    request_id = "0dd1ba67-c216-48af-a00f-1baa57f6ca3e"
    ack = core.handle_ipc_command(_request(request_id))
    assert ack["accepted"] is True and entered.wait(1)
    stop_ack = core.handle_ipc_command({
        "protocol_version": 1, "message_type": "stop",
        "request_id": "5b018d04-83d1-4ff7-967c-2834aab37d45",
        "task_id": ack["task_id"],
    })
    assert stop_ack["message_type"] == "stop_ack"
    assert stop_ack["request_id"] == "5b018d04-83d1-4ff7-967c-2834aab37d45"
    capsule = supervisor.get_task(ack["task_id"])
    assert capsule.cancellation_token.is_cancelled
    thread = core._submission_threads[ack["task_id"]]
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert capsule.terminal_ready.is_set()
    assert capsule.state in {TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL}
    terminal = core.handle_ipc_command(_readback(request_id, ack["task_id"]))
    assert terminal["terminal"] is True
    assert terminal["completion_verified"] is False
