"""Presentation only: owned SQLite/registry fixtures, no desktop operations."""
import json
from uuid import uuid4

import pytest

from tests.unit.test_ipc_request_contract import resident_fixture
from pluma.memory.activity import ActionRecord, ActivityQuery, TaskRecord


def setup(ledger, **values):
    task, request = str(uuid4()), str(uuid4())
    ledger.insert_task(TaskRecord(task, request, "text", "Owned presentation fixture"))
    action = ledger.insert_action(ActionRecord(task, 0, values.pop("tool", "fixture_read"), {}, "READ", **values))
    return task, request, action


def query(core, task, action, **fields):
    return core.handle_ipc_command(dict(protocol_version=1, message_type="action_detail_query",
        request_id=str(uuid4()), task_id=task, action_id=action, **fields))


def test_exact_detail_and_legacy_wire_stay_separate(resident_fixture):
    core, ledger, _ = resident_fixture
    task, request, action = setup(ledger, factual_message="Read owned résumé 文件.",
        error_detail={"code": "READ_FAILED", "error": "PRIVATE_ERROR_BODY"},
        result_data={"private": "PRIVATE_RESULT_BODY"})
    before = ActivityQuery(ledger._db).event_batch(None)["next_sequence"]
    detail = query(core, task, action)
    assert detail["message_type"] == "action_detail"
    assert (detail["task_id"], detail["task_request_id"], detail["action_id"]) == (task, request, action)
    assert detail["factual_message"] == "Read owned résumé 文件." and detail["error_code"] == "READ_FAILED"
    assert "PRIVATE_" not in json.dumps(detail)
    page = core.handle_ipc_command(dict(protocol_version=1, message_type="activity_query", request_id=str(uuid4()), task_id=task))
    assert "factual_message" not in page["actions"][0]  # E88 strict clients retain their original envelope.
    assert ActivityQuery(ledger._db).event_batch(None)["next_sequence"] == before
    other, _, _ = setup(ledger)
    assert query(core, other, action)["error_code"] == "ACTION_NOT_FOUND"


@pytest.mark.parametrize("fields", [{"action_id": 0}, {"action_id": True}, {"action_id": 2**63},
    {"task_id": "bad"}, {"unexpected": "private"}])
def test_invalid_detail_request(resident_fixture, fields):
    core, ledger, _ = resident_fixture
    task, _, action = setup(ledger)
    request = dict(protocol_version=1, message_type="action_detail_query", request_id=str(uuid4()), task_id=task, action_id=action)
    request.update(fields)
    assert core.handle_ipc_command(request)["error_code"] == "INVALID_REQUEST"


@pytest.mark.parametrize("tool,message", [("clipboard_get", "PRIVATE_CLIPBOARD_VALUE"),
    ("paste_text", "PRIVATE_CLIPBOARD_VALUE"), ("fixture_read", "PRIVATE_CLIPBOARD_VALUE " + "x" * 1500 + " clipboard")])
def test_redaction_precedes_bounds_and_never_persists_clipboard(resident_fixture, tool, message):
    core, ledger, _ = resident_fixture
    task, _, action = setup(ledger, tool=tool, factual_message=message)
    saved = ActivityQuery(ledger._db).actions_for_task(task)[0]["presentation_json"]
    detail = query(core, task, action)
    assert "PRIVATE_CLIPBOARD_VALUE" not in saved + json.dumps(detail)
    assert "REDACTED" in detail["factual_message"]


def test_unicode_bound_secret_redaction_and_missing_history(resident_fixture):
    core, ledger, _ = resident_fixture
    task, _, action = setup(ledger, factual_message="password=PRIVATE_PASSWORD " + "文件" * 800)
    message = query(core, task, action)["factual_message"]
    assert "PRIVATE_PASSWORD" not in message
    task, _, action = setup(ledger, factual_message="文件" * 800)
    message = query(core, task, action)["factual_message"]
    assert len(message.encode("utf-8")) <= 1024 and message.endswith("…")
    old, _, legacy = setup(ledger)
    detail = query(core, old, legacy)
    assert detail["factual_message"] is None and detail["error_code"] is None and detail["policy_reason"] is None


def test_secret_shaped_error_identity_is_withheld_on_write_and_read(resident_fixture):
    core, ledger, _ = resident_fixture
    synthetic = "AKIA1234567890123456"
    task, _, action = setup(ledger, error_detail={"code": synthetic})
    row = ActivityQuery(ledger._db).actions_for_task(task)[0]
    assert synthetic not in row["presentation_json"] + row["error_json"]
    assert query(core, task, action)["error_code"] is None
    encoded = json.dumps(dict(version=1, factual_message=None, error_code=synthetic, policy_reason=None))
    ledger._db.execute_write("UPDATE actions SET presentation_json=? WHERE id=?", (encoded, action))
    assert query(core, task, action)["error_code"] is None


@pytest.mark.parametrize("encoded", ["{", "x" * 14001,
    json.dumps({"version": 1, "factual_message": None, "error_code": "not a code", "policy_reason": None}),
    json.dumps({"version": True, "factual_message": None, "error_code": None, "policy_reason": None})])
def test_malformed_saved_detail_fails_closed(resident_fixture, encoded):
    core, ledger, _ = resident_fixture
    task, _, action = setup(ledger)
    ledger._db.execute_write("UPDATE actions SET presentation_json=? WHERE id=?", (encoded, action))
    assert query(core, task, action)["error_code"] == "ACTION_DETAIL_UNAVAILABLE"


def test_reason_requires_actual_saved_denial_and_detail_updates_emit_event(resident_fixture):
    core, ledger, _ = resident_fixture
    task, _, action = setup(ledger, approval_state="DENY", factual_message="Blocked by policy.",
        policy_reason="Tool is forbidden by its configured risk tier.", error_detail={"code": "POLICY_DENIED"})
    assert query(core, task, action)["policy_reason"] == "Tool is forbidden by its configured risk tier."
    ledger._db.execute_write("UPDATE actions SET approval_state='ALLOW' WHERE id=?", (action,))
    assert query(core, task, action)["error_code"] == "ACTION_DETAIL_UNAVAILABLE"
    before = ActivityQuery(ledger._db).event_batch(None)["next_sequence"]
    ledger._db.execute_write("UPDATE actions SET presentation_json=NULL WHERE id=?", (action,))
    assert ActivityQuery(ledger._db).event_batch(None)["next_sequence"] == before + 1


def test_actual_registry_result_and_policy_reason_are_durable(resident_fixture, tmp_path):
    from pydantic import BaseModel
    from pluma.tools.base import ToolSpec, ToolResult, VerifyResult, RiskClass
    from pluma.tools.registry import ToolRegistry
    from pluma.core.task_supervisor import TaskState
    from pluma.policy.engine import PolicyEngine
    core, ledger, supervisor = resident_fixture
    owned = tmp_path / "owned.txt"
    owned.write_text("owned fixture", encoding="utf-8")
    class Args(BaseModel):
        pass
    capsule = supervisor.create_task(str(uuid4()))
    ledger.insert_task(TaskRecord(capsule.task_id, capsule.request_id, "text", "Read owned fixture"))
    supervisor.start_task(capsule.task_id)
    registry = ToolRegistry(policy_engine=PolicyEngine())
    def forbidden(args, context):
        raise AssertionError("Denied executor was entered")
    registry.register(ToolSpec(name="fixture_read", description="Owned read", args_schema=Args,
        risk_class=RiskClass.READ, timeout_s=5, executor=lambda args, ctx: ToolResult.success("fixture_read",
            {"length": len(owned.read_bytes())}, "Read owned fixture."),
        verifier=lambda result: VerifyResult(ok=result.data["length"] == owned.stat().st_size,
            method="owned_readback", detail="Owned file length independently read back.")))
    registry.register(ToolSpec(name="fixture_denied", description="Owned refusal", args_schema=Args,
        risk_class=RiskClass.DENY, timeout_s=5, executor=forbidden,
        verifier=lambda result: VerifyResult(ok=False, method="not_executed", detail="Execution is forbidden.")))
    try:
        read = registry.execute("fixture_read", {}, task_context=capsule, ledger=ledger)
        denied = registry.execute("fixture_denied", {}, task_context=capsule, ledger=ledger, step_index=1)
        assert read.ok and read.verified and not denied.ok and denied.error_code == "POLICY_DENIED"
        rows = ActivityQuery(ledger._db).actions_for_task(capsule.task_id)
        details = [query(core, capsule.task_id, row["id"]) for row in rows]
        assert details[0]["factual_message"] == read.factual_message == "Read owned fixture."
        assert details[1]["factual_message"] == denied.factual_message
        assert details[1]["error_code"] == denied.error_code
        assert details[1]["policy_reason"] and denied.error == "Blocked by policy: " + details[1]["policy_reason"]
        assert json.loads(rows[1]["presentation_json"])["policy_reason"] == details[1]["policy_reason"]
    finally:
        registry.close()
        supervisor.finalize_task(capsule.task_id, TaskState.FAILED)


def test_prepared_mutation_finalizes_presentation_atomically(resident_fixture):
    core, ledger, _ = resident_fixture
    task, _, _ = setup(ledger)
    pending = {"action": "owned_fixture_inverse"}
    record = ActionRecord(task, 1, "fixture_mutation", {}, "LOW")
    action = ledger.prepare_mutation(record, pending)
    before = ActivityQuery(ledger._db).event_batch(None)["next_sequence"]
    final = ActionRecord(task, 1, "fixture_mutation", {}, "LOW", verified=True,
                         factual_message="Owned mutation postcondition read back.")
    ledger.finish_mutation(action, final, pending)
    assert query(core, task, action)["factual_message"] == final.factual_message
    assert ActivityQuery(ledger._db).actions_for_task(task)[-1]["verified"] == 1
    assert ActivityQuery(ledger._db).event_batch(None)["next_sequence"] == before + 1
