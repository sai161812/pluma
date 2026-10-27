"""Owned in-memory evidence, no desktop or privileged operations."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from tests.unit.test_ipc_request_contract import resident_fixture
from pluma.core.cleanup import CleanupEvidence
from pluma.core.ipc_contracts import parse_versioned_request
from pluma.memory.activity import ActionRecord, ActivityQuery, TaskRecord, UndoRecord


def wire(task, **fields):
    return dict(protocol_version=1, message_type="activity_query", request_id=str(uuid4()), task_id=task, **fields)


def task(ledger):
    value = str(uuid4())
    ledger.insert_task(TaskRecord(value, str(uuid4()), "text", "paste PRIVATE_ACTIVITY_PAYLOAD"))
    return value


@pytest.mark.parametrize("fields", [dict(limit=0), dict(limit=101), dict(limit=True), dict(after_action_id=-1),
    dict(after_action_id=True), dict(after_action_id=2**63), dict(task_id="bad"), dict(extra="private")])
def test_strict_request_bounds(resident_fixture, fields):
    core, ledger, _ = resident_fixture
    request = wire(task(ledger)); request.update(fields)
    assert core.handle_ipc_command(request)["error_code"] == "INVALID_REQUEST"


def test_read_only_pagination_beyond_old_history_cap(resident_fixture):
    core, ledger, _ = resident_fixture
    owned = task(ledger)
    other = task(ledger)
    ids = []
    for index in range(105):
        ids.append(ledger.insert_action(ActionRecord(owned, 104-index, "fixture_read", {"text": "PRIVATE_ACTIVITY_PAYLOAD"},
            "READ", verified=True, result_data={"private": "PRIVATE_ACTIVITY_PAYLOAD"})))
    ledger.insert_action(ActionRecord(other, 0, "fixture_other", {}, "READ"))
    legacy = dict(protocol_version=1, message_type="history_query", request_id=str(uuid4()), task_id=owned, limit=100)
    assert core.handle_ipc_command(legacy)["error_code"] == "HISTORY_TOO_LARGE"
    before = ActivityQuery(ledger._db).event_batch(None)["next_sequence"]
    seen, after = [], 0
    while True:
        reply = core.handle_ipc_command(wire(owned, after_action_id=after, limit=17))
        assert reply["message_type"] == "activity_page"
        assert len(reply["actions"]) <= 17
        assert "PRIVATE_ACTIVITY_PAYLOAD" not in json.dumps(reply)
        assert not ({"command_text", "arguments", "result", "worker_terminated"} & reply.keys())
        seen.extend(a["action_id"] for a in reply["actions"])
        after = reply["next_action_id"]
        if not reply["has_more"]:
            break
    assert seen == ids  # stable ID order, never confused with step order
    empty = core.handle_ipc_command(wire(owned, after_action_id=after))
    assert empty["actions"] == [] and empty["next_action_id"] == after and not empty["has_more"]
    assert ActivityQuery(ledger._db).event_batch(None)["next_sequence"] == before


def test_empty_unknown_and_undo_facts(resident_fixture):
    core, ledger, _ = resident_fixture
    owned = task(ledger)
    assert core.handle_ipc_command(wire(owned))["actions"] == []
    assert core.handle_ipc_command(wire(str(uuid4())))["error_code"] == "TASK_NOT_FOUND"
    action = ledger.insert_action(ActionRecord(owned, 0, "fixture_denied", {}, "DENY", approval_state="DENY",
        error_detail={"code": "DENIED", "text": "PRIVATE_ACTIVITY_PAYLOAD"}))
    ledger.insert_undo(UndoRecord(action, {"private": "PRIVATE_ACTIVITY_PAYLOAD"}))
    ledger.mark_rollback_result(action, ok=False, result={"private": "PRIVATE_ACTIVITY_PAYLOAD"})
    reply = core.handle_ipc_command(wire(owned))
    fact = reply["actions"][0]
    assert fact["policy_denied"] and fact["error_recorded"] and not fact["verified"]
    assert fact["undo_available"] and fact["rollback_attempted"] and fact["rollback_ok"] is False
    assert "PRIVATE_ACTIVITY_PAYLOAD" not in json.dumps(reply)


def test_cleanup_uses_latest_evidence_not_resource_release(resident_fixture):
    core, ledger, _ = resident_fixture
    owned = task(ledger)
    assert core.handle_ipc_command(wire(owned))["cleanup"] is None
    ledger.record_cleanup(owned, [CleanupEvidence(resource_id="private-id", kind="worker", code="PENDING").model_dump()])
    assert core.handle_ipc_command(wire(owned))["cleanup"] == dict(complete=False, unresolved_count=1)
    ledger.record_cleanup(owned, [
        CleanupEvidence(resource_id="private-id", kind="worker", code="PENDING").model_dump(),
        CleanupEvidence(resource_id="private-id", kind="worker", code="WORKER_ABSENCE_VERIFIED", verified=True,
            identity={"pid": 555, "password": "PRIVATE_ACTIVITY_PAYLOAD"}).model_dump()])
    reply = core.handle_ipc_command(wire(owned))
    assert reply["cleanup"] == dict(complete=True, unresolved_count=0)
    assert "private-id" not in json.dumps(reply) and "555" not in json.dumps(reply)


@pytest.mark.parametrize("encoded", ['{', json.dumps({"version": 1, "complete": True, "entries": [
    {"resource_id": "x", "kind": "worker", "code": "PENDING", "verified": False}]}),
    json.dumps({"version": 1, "complete": True, "entries": [], "extra": "x" * 66000})], ids=["malformed", "contradictory", "oversized"])
def test_malformed_or_contradictory_cleanup_fails_closed(resident_fixture, encoded):
    core, ledger, _ = resident_fixture
    owned = task(ledger)
    ledger._db.execute_write("INSERT INTO cleanup_reports(task_id,recorded_at,metadata_json) VALUES (?,?,?)",
                             (owned, "2026-10-27T00:00:00Z", encoded))
    assert core.handle_ipc_command(wire(owned))["error_code"] == "ACTIVITY_UNAVAILABLE"


def test_stop_does_not_wait_for_activity_read(resident_fixture, monkeypatch):
    core, ledger, _ = resident_fixture
    owned = task(ledger)
    entered, release = threading.Event(), threading.Event()
    original = ActivityQuery.activity_page
    def blocked(self, *args):
        entered.set()
        assert release.wait(3)
        return original(self, *args)
    monkeypatch.setattr(ActivityQuery, "activity_page", blocked)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(core.handle_ipc_command, wire(owned))
        try:
            assert entered.wait(2)
            stop = core.handle_ipc_command(dict(protocol_version=1, message_type="stop", request_id=str(uuid4())))
            assert stop["message_type"] == "stop_ack" and not release.is_set()
        finally:
            release.set()
        assert future.result(3)["message_type"] == "activity_page"
