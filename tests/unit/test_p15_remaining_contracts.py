"""P15 contracts: owned capsules/in-memory ledger, no desktop operations."""
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import hmac
import os
from multiprocessing.connection import Client, wait
import time
from uuid import uuid4

import pytest

from pluma.core.ipc_contracts import parse_versioned_request
from pluma.core.resident import ResidentCore
from pluma.core.ipc import IpcServer
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import (ActionRecord, ActivityLedger, ActivityQuery, TaskRecord,
                                   UndoRecord, ResourceRecord, ScreenEventRecord)
from pluma.memory.db import DbConnection
from pluma.policy.engine import PolicyEngine
from pluma.tools.base import RiskClass
from pluma.ui.confirmations import ConfirmationRequest
from pluma.ui.ipc_confirmations import IpcConfirmationBroker


def uid():
    return str(uuid4())


def wire(kind, **fields):
    return dict(protocol_version=1, message_type=kind, request_id=uid(), **fields)


@pytest.fixture
def exchange():
    with DbConnection(":memory:") as db:
        ledger = ActivityLedger(db)
        supervisor = TaskSupervisor(ledger=ledger)
        broker = IpcConfirmationBroker(supervisor.get_task, timeout_s=0.4)
        core = ResidentCore.__new__(ResidentCore)
        core.ledger, core.supervisor, core.confirmation_broker = ledger, supervisor, broker
        client = uid()
        assert core.handle_ipc_command(wire("confirmation_query", client_id=client))["confirmations"] == []
        yield core, broker, ledger, supervisor, client
        broker.close()
        supervisor.stop_all_active_tasks()


def begin(exchange):
    core, broker, ledger, supervisor, client = exchange
    cap = supervisor.create_task_capsule(request_id=uid())
    ledger.insert_task(TaskRecord(cap.task_id, cap.request_id, "text", "Owned P15 fixture"))
    supervisor.start_task(cap.task_id)
    req = ConfirmationRequest(cap.task_id, "fixture_probe", {"password": "private-p15-sentinel"},
                              RiskClass.HIGH, "Exact approval", "Allow this owned fixture read?")
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(broker.request_confirmation, req)
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        items = core.handle_ipc_command(wire("confirmation_query", client_id=client))["confirmations"]
        if items:
            return cap, req, items[0], pool, future
        time.sleep(0.005)
    pool.shutdown(wait=True)
    raise AssertionError("Confirmation was never published.")


@pytest.mark.parametrize("approved", [True, False])
def test_exact_decision_is_consumed_once_and_redacted(exchange, approved):
    core, _, _, _, client = exchange
    cap, _, item, pool, future = begin(exchange)
    try:
        assert "private-p15-sentinel" not in json.dumps(item)
        message = wire("confirmation_decision", client_id=client, task_id=cap.task_id,
                       confirmation_id=item["confirmation_id"], binding=item["binding"], approved=approved)
        reply = core.handle_ipc_command(message)
        assert reply["accepted"] is True and reply["approved"] is approved
        assert future.result(1).approved is approved
        assert core.handle_ipc_command(message)["error_code"] == "CONFIRMATION_NOT_PENDING"
    finally:
        pool.shutdown(wait=True)


@pytest.mark.parametrize("fault", ["task", "binding", "client", "stop", "disconnect", "timeout", "close", "changed"])
def test_stale_or_unowned_decisions_never_approve(exchange, fault):
    core, broker, _, _, client = exchange
    cap, req, item, pool, future = begin(exchange)
    message = wire("confirmation_decision", client_id=client, task_id=cap.task_id,
                   confirmation_id=item["confirmation_id"], binding=item["binding"], approved=True)
    try:
        if fault in {"task", "client"}:
            message[fault + "_id"] = uid()
        elif fault == "binding":
            message["binding"] = "0" * 64
        elif fault == "stop":
            cap.cancellation_token.cancel()
        elif fault == "disconnect":
            reply = core.handle_ipc_command(wire("confirmation_disconnect", client_id=client))
            assert reply["denied_count"] == 1
        elif fault == "timeout":
            assert future.result(1).approved is False
        elif fault == "close":
            broker.close()
        elif fault == "changed":
            req.arguments["password"] = "changed"
        reply = core.handle_ipc_command(message)
        if fault in {"task", "client", "binding"}:
            assert reply["error_code"] == "CONFIRMATION_MISMATCH"
            broker.disconnect(client)
        elif fault != "changed":
            assert reply["accepted"] is False
        assert future.result(1).approved is False
        assert broker._pending == {}
    finally:
        broker.close()
        pool.shutdown(wait=True)


def test_policy_exact_call_uses_broker_and_no_client_denies_immediately(exchange):
    core, broker, _, supervisor, client = exchange
    cap = supervisor.create_task_capsule(request_id=uid())
    engine = PolicyEngine(confirmation_contract=broker)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(engine.evaluate, "fixture_probe", {"value": 3}, RiskClass.HIGH, cap.task_id)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            items = broker.pending(client)
            if items:
                break
            time.sleep(0.005)
        item = items[0]
        ack = core.handle_ipc_command(wire("confirmation_decision", client_id=client, task_id=cap.task_id,
            confirmation_id=item["confirmation_id"], binding=item["binding"], approved=True))
        assert ack["accepted"] and future.result(1).allowed
    broker.disconnect(client)
    assert not engine.evaluate("fixture_probe", {}, RiskClass.HIGH, cap.task_id).allowed


def test_confirmation_capacity_and_client_expiry_fail_closed(exchange):
    core, broker, _, _, client = exchange
    broker._capacity = 1
    cap, request, _, pool, future = begin(exchange)
    try:
        assert not broker.request_confirmation(request).approved  # no second owned slot
        broker._clients[client] = time.monotonic() - 1  # injected lost-client lease
        broker.pending(uid())
        assert future.result(1).approved is False
        assert broker._pending == {}
        for _ in range(15):
            broker.pending(uid())
        reply = core.handle_ipc_command(wire("confirmation_query", client_id=uid()))
        assert reply["error_code"] == "CONTRACT_UNAVAILABLE"
        broker.close()
        assert not broker.is_available
    finally:
        broker.close()
        pool.shutdown(wait=True)


def test_disconnect_counts_unclaimed_calls_when_last_client_leaves(exchange):
    _, broker, _, supervisor, client = exchange
    cap = supervisor.create_task_capsule(request_id=uid())
    request = ConfirmationRequest(cap.task_id, "fixture_probe", {}, RiskClass.HIGH, "Fixture", "Allow fixture?")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(broker.request_confirmation, request)
        deadline = time.monotonic() + 0.3
        while time.monotonic() < deadline:
            with broker._lock:
                if broker._pending:
                    break
            time.sleep(0.002)
        assert broker.disconnect(client) == 1
        assert future.result(1).approved is False


@pytest.mark.parametrize("fields", [
    {"message_type": "confirmation_decision", "approved": "yes"},
    {"message_type": "events_query", "after_sequence": True},
    {"message_type": "events_query", "limit": 101},
    {"message_type": "events_query", "after_sequence": 1},
    {"message_type": []},
])
def test_new_messages_fail_closed_on_malformed_input(fields):
    with pytest.raises(ValueError):
        parse_versioned_request(dict(protocol_version=1, request_id=uid(), **fields))


def test_event_journal_order_rollback_privacy_replay_and_overflow(tmp_path):
    path = str(tmp_path / "events.db")
    with DbConnection(path) as db:
        ledger, query = ActivityLedger(db), ActivityQuery(db)
        first = query.event_batch(None)
        assert first["reset_required"] and first["next_sequence"] == 0
        stream = first["stream_id"]
        task_id, request_id = uid(), uid()
        ledger.insert_task(TaskRecord(task_id, request_id, "text", "paste private-event-sentinel"))
        ledger.update_task(task_id, route="FAST")
        action = ledger.insert_action(ActionRecord(task_id, 0, "fixture_read", {"password": "private-event-sentinel"}, "READ"))
        batch = query.event_batch(stream, 0)
        assert [e["kind"] for e in batch["events"]] == ["task_recorded", "task_changed", "action_recorded"]
        assert [e["sequence"] for e in batch["events"]] == [1, 2, 3]
        assert batch["events"][-1]["record_id"] == action
        assert "private-event-sentinel" not in json.dumps(batch)
        assert query.event_batch(stream, 0) == batch  # same cursor replays exact immutable facts
        assert query.event_batch(stream, 3)["events"] == []
        with pytest.raises(Exception):
            db.execute_transaction([
                ("UPDATE tasks SET route='SMART' WHERE task_id=?", (task_id,)),
                ("INSERT INTO no_such_table VALUES (1)", ()),
            ])
        assert query.event_batch(stream, 3)["events"] == []  # rolled-back writes have no event
        for i in range(520):
            ledger.update_task(task_id, error_code=str(i))
        assert db.execute_read_one("SELECT COUNT(*) FROM ui_events")[0] == 512
        reset = query.event_batch(stream, 0)
        assert reset["reset_required"] and reset["events"] == []
        assert query.event_batch(stream, reset["next_sequence"])["events"] == []
        assert query.event_batch(uid(), 0)["reset_required"]
        assert query.event_batch(stream, reset["last_sequence"] + 1)["reset_required"]
    with DbConnection(path) as db:
        resumed = ActivityQuery(db).event_batch(stream, reset["last_sequence"])
        assert not resumed["reset_required"] and resumed["events"] == []


def test_concurrent_commits_and_page_bound_have_one_total_order(exchange):
    _, _, ledger, _, _ = exchange
    query = ActivityQuery(ledger._db)
    stream = query.event_batch(None)["stream_id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: ledger.insert_task(TaskRecord(uid(), uid(), "text", "fixture")), range(120)))
    batch = query.event_batch(stream, 0, 100)
    assert batch["has_more"] and len(batch["events"]) == 100
    tail = query.event_batch(stream, batch["next_sequence"], 100)
    assert not tail["has_more"] and len(tail["events"]) == 20
    assert [x["sequence"] for x in batch["events"] + tail["events"]] == list(range(1, 121))


def test_each_projection_source_names_committed_records(exchange):
    _, _, ledger, _, _ = exchange
    query = ActivityQuery(ledger._db)
    stream = query.event_batch(None)["stream_id"]
    task_id = uid()
    ledger.insert_task(TaskRecord(task_id, uid(), "text", "Owned records"))
    action_id = ledger.insert_action(ActionRecord(task_id, 0, "fixture_read", {}, "READ"))
    ledger.insert_undo_record(UndoRecord(action_id, {"private_fixture": "never projected"}))
    ledger.mark_rollback_result(action_id, True, {"fixture": "readback"})
    ledger.mark_undo_consumed(action_id)
    record = ResourceRecord(uid(), task_id, "fixture", "PLUMA_CREATED")
    ledger.insert_resource(record)
    ledger.release_resource(record.id)
    screen_id = ledger.insert_screen_event(ScreenEventRecord(task_id, uid(), "UIA", target_label="private screen fixture"))
    ledger.record_cleanup(task_id, [])
    kinds = [event["kind"] for event in query.event_batch(stream)["events"]]
    assert kinds.count("rollback_changed") == 3
    assert kinds.count("resource_changed") == 3  # resource create/release plus cleanup mirror
    assert "screen_recorded" in kinds and "cleanup_recorded" in kinds
    encoded = json.dumps(query.event_batch(stream))
    assert "never projected" not in encoded and "private screen fixture" not in encoded
    assert any(e["kind"] == "screen_recorded" and e["record_id"] == screen_id
               for e in query.event_batch(stream)["events"])


@pytest.mark.parametrize("raw", [
    b'{"command":"echo","command":"stop"}',
    b'{"command":"echo","payload":{"approved":false,"approved":true}}',
    b'{"command":"echo","payload":NaN}',
])
def test_authenticated_malformed_json_never_dispatches(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    seen = []
    address = rf"\\.\pipe\pluma_p15_malformed_{os.getpid()}_{uuid4().hex}"
    server = IpcServer(lambda request: seen.append(request) or {"status": "ok"}, address=address)
    server.start()
    try:
        with Client(address) as conn:
            assert wait([conn], 2)
            challenge = conn.recv_bytes()
            conn.send_bytes(hmac.new(server._secret, challenge, hashlib.sha256).digest())
            assert wait([conn], 2) and conn.recv_bytes() == b"AUTH_OK"
            conn.send_bytes(raw)
            assert wait([conn], 2)
            reply = json.loads(conn.recv_bytes())
            assert reply["status"] == "error" and seen == []
    finally:
        server.stop(timeout_s=4)
