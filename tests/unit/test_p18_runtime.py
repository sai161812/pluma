"""Owned capsule and executor fixtures; never personal desktop state."""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pydantic import BaseModel

from tests.unit.test_ipc_request_contract import resident_fixture
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import TaskRecord
from pluma.tools.base import ToolSpec, ToolResult, VerifyResult, RiskClass
from pluma.tools.registry import ToolRegistry


def query(core, **fields):
    return core.handle_ipc_command(dict(protocol_version=1, message_type="runtime_query", request_id=str(uuid4()), **fields))


def capsule(ledger, supervisor):
    cap = supervisor.create_task(str(uuid4()))
    ledger.insert_task(TaskRecord(cap.task_id, cap.request_id, "text", "Owned runtime fixture"))
    supervisor.start_task(cap.task_id)
    return cap


def test_live_snapshot_is_not_saved_completion_or_a_command(resident_fixture):
    core, ledger, supervisor = resident_fixture
    assert query(core)["tasks"] == []
    cap = capsule(ledger, supervisor)
    cap.live_presentation.plan(3); cap.live_presentation.select(2)
    first = query(core)["tasks"][0]
    assert first["state"] == "RUNNING" and first["tool"] is None
    assert (first["step"], first["total"], first["plan_revision"]) == (2, 3, 1)
    cap.live_presentation.plan(1); cap.live_presentation.select(1)
    second = query(core)["tasks"][0]
    assert (second["step"], second["total"], second["plan_revision"]) == (1, 1, 2)
    assert not ({"command_text", "result", "success", "purpose"} & second.keys())
    supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    assert query(core)["tasks"] == []  # Disappearance is not the terminal evidence API.


@pytest.mark.parametrize("fields", [{"extra": "private"}, {"request_id": "bad"}])
def test_runtime_query_strict(resident_fixture, fields):
    core, _, _ = resident_fixture
    request = dict(protocol_version=1, message_type="runtime_query", request_id=str(uuid4()))
    request.update(fields)
    assert core.handle_ipc_command(request)["error_code"] == "INVALID_REQUEST"


def test_executor_entry_and_stop_are_observed_without_inventing_execution(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    entered = threading.Event()
    class Args(BaseModel):
        pass
    def execute(args, context):
        entered.set()
        assert context.cancellation_token.wait_for_cancel(4)
        context.cancellation_token.raise_if_cancelled()
    registry = ToolRegistry()
    registry.register(ToolSpec(name="fixture_wait", description="Owned cancellable wait", args_schema=Args,
        risk_class=RiskClass.READ, timeout_s=5, executor=execute,
        verifier=lambda result: VerifyResult(ok=False, method="stopped", detail="No success is claimed.")))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(registry.execute, "fixture_wait", {}, task_context=cap, ledger=ledger)
            assert entered.wait(2)
            live = query(core)["tasks"][0]
            assert live["phase"] == "EXECUTING" and live["tool"] == "fixture_wait" and live["tool_elapsed_ms"] >= 0
            stop = core.handle_ipc_command(dict(protocol_version=1, message_type="stop", request_id=str(uuid4()), task_id=cap.task_id))
            assert stop["message_type"] == "stop_ack" and not future.result(3).ok
            assert query(core)["tasks"] == []
    finally:
        cap.cancellation_token.cancel()
        registry.close()


@pytest.mark.parametrize("tool", ["clipboard_set", "paste_text", "type_text", "fixture_read"])
def test_live_arguments_are_redacted_and_utf8_bounded(resident_fixture, tool):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    args = {"password": "PRIVATE_RUNTIME_VALUE"} if tool == "fixture_read" else {"text": "PRIVATE_RUNTIME_VALUE"}
    generation = cap.live_presentation.dispatch(tool, "LOW", args)
    reply = query(core)
    assert "PRIVATE_RUNTIME_VALUE" not in json.dumps(reply)
    assert reply["tasks"][0]["phase"] == "DISPATCHING" and reply["tasks"][0]["tool_elapsed_ms"] is None
    cap.live_presentation.complete(generation)
    supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


def test_latch_dominates_live_phase_and_bad_counts_fail_closed(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    cap.cancellation_token.cancel()
    assert query(core)["tasks"][0]["state"] == "STOPPING"
    cap.live_presentation.plan(1); cap.live_presentation.select(2)
    assert query(core)["error_code"] == "RUNTIME_UNAVAILABLE"
    supervisor.stop_task(cap.task_id)


def test_snapshot_cannot_block_priority_stop(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    cap.live_presentation.lock.acquire()
    try:
        assert query(core)["error_code"] == "RUNTIME_UNAVAILABLE"
    finally:
        cap.live_presentation.lock.release()
    supervisor.stop_task(cap.task_id)


def test_nested_tool_completion_restores_only_a_still_owned_parent(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    live = cap.live_presentation
    parent = live.dispatch("run_routine", "LOW", {}); live.entered(parent)
    child = live.dispatch("fixture_read", "READ", {}); live.entered(child)
    assert query(core)["tasks"][0]["tool"] == "fixture_read"
    live.complete(child)
    assert query(core)["tasks"][0]["tool"] == "run_routine"
    live.complete(parent)
    assert query(core)["tasks"][0]["tool"] is None
    supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


class WorkerArgs(BaseModel):
    pass


def owned_worker_wait(args, context):
    import time
    from pluma.tools.base import ToolResult
    end = time.monotonic() + 5
    while time.monotonic() < end:
        context.cancellation_token.raise_if_cancelled()
        time.sleep(.01)
    return ToolResult.failure("fixture_worker", "Owned wait expired.")


def verify_owned_wait(result):
    return VerifyResult(ok=False, method="owned_wait", detail="No success is claimed.")


def test_actual_process_entry_and_stop_cleanup_readback(resident_fixture):
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    registry = ToolRegistry()
    registry.register(ToolSpec(name="fixture_worker", description="Owned native worker", args_schema=WorkerArgs,
        risk_class=RiskClass.READ, process_isolated=True, timeout_s=6, executor=owned_worker_wait,
        verifier=verify_owned_wait))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(registry.execute, "fixture_worker", {}, task_context=cap, ledger=ledger)
            end = time.monotonic() + 4
            while time.monotonic() < end:
                if future.done():
                    assert False, "Owned worker returned before entry: " + str(future.result().error_code)
                frame = query(core)
                node = frame["tasks"][0]
                if node["phase"] == "EXECUTING":
                    break
                time.sleep(.01)
            assert node["phase"] == "EXECUTING" and node["tool_elapsed_ms"] is not None
            assert cap.worker_controller.worker_identity["task_id"] == cap.task_id
            supervisor.stop_task(cap.task_id)
            assert not future.result(3).ok and query(core)["tasks"] == []
            evidence = [item for item in cap.cleanup_evidence if item.kind == "worker"]
            assert evidence and evidence[-1].verified and evidence[-1].code == "WORKER_ABSENCE_VERIFIED"
            assert evidence[-1].identity["ownership"] == "PLUMA_CREATED" and type(evidence[-1].identity["exit_code"]) is int
            proof = query(core)["terminations"]
            assert len(proof) == 1 and proof[0]["pid"] == evidence[-1].identity["pid"]
    finally:
        cap.cancellation_token.cancel()
        registry.close()


def test_verification_readback_requires_matching_saved_proof(resident_fixture):
    from pluma.memory.activity import ActionRecord
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    record = ActionRecord(cap.task_id, 0, "invoke_control", {}, "READ", verified=True,
        verification_detail={"ok": True, "method": "owned_readback", "detail": "Verified owned fixture.", "duration_ms": 1})
    action = ledger.insert_action(record)
    def verify():
        return core.handle_ipc_command(dict(protocol_version=1, message_type="action_verification_query",
            request_id=str(uuid4()), task_id=cap.task_id, action_id=action))
    value = verify()
    assert value["verified"] is True and value["method"] == "owned_readback"
    ledger._db.execute_write("UPDATE actions SET verified=0 WHERE id=?", (action,))
    assert verify()["error_code"] == "VERIFICATION_UNAVAILABLE"
    supervisor.finalize_task(cap.task_id, TaskState.FAILED)


def test_worker_feedback_requires_owned_verified_identity(resident_fixture):
    from pluma.core.cleanup import CleanupEvidence
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    identity = dict(task_id=cap.task_id, ownership="PLUMA_CREATED", command_class="tool_worker",
                    pid=321, creation_time=123456, exit_code=1)
    for change in ({"ownership": "EXTERNAL"}, {"task_id": str(uuid4())},
                   {"command_class": "external"}, {"exit_code": None}):
        cap.cleanup_evidence = [CleanupEvidence(resource_id="fixture", kind="worker", verified=True,
            code="WORKER_ABSENCE_VERIFIED", identity={**identity, **change})]
        assert query(core)["terminations"] == []
    cap.cleanup_evidence = [CleanupEvidence(resource_id="fixture", kind="worker", verified=False,
        code="WORKER_ABSENCE_VERIFIED", identity=identity)]
    assert query(core)["terminations"] == []
    cap.cleanup_evidence.clear()
    supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)


def test_real_rollback_publishes_selected_inverse_before_owned_file_restore(resident_fixture, tmp_path, monkeypatch):
    from pluma.memory.activity import ActionRecord, UndoRecord, ActivityQuery
    from pluma.rollback.engine import RollbackEngine
    core, ledger, supervisor = resident_fixture
    cap = capsule(ledger, supervisor)
    original, moved = tmp_path / "original.txt", tmp_path / "moved.txt"
    moved.write_text("Owned inverse fixture", encoding="utf-8")
    action = ledger.insert_action(ActionRecord(cap.task_id, 0, "move_file", {}, "MEDIUM"))
    ledger.insert_undo_record(UndoRecord(action, {"action": "move_file", "source": str(original), "destination": str(moved)}))
    engine = RollbackEngine(ledger=ledger)
    engine.task_resolver = supervisor.get_task
    apply = engine._apply
    observed = []
    def checked_apply(task_id, recipe, state):
        observed.append(query(core)["tasks"][0])
        assert moved.exists() and not original.exists()
        return apply(task_id, recipe, state)
    monkeypatch.setattr(engine, "_apply", checked_apply)
    cap.state = TaskState.ROLLING_BACK
    result = engine.rollback_task(cap.task_id)
    assert result.all_ok and original.read_text(encoding="utf-8") == "Owned inverse fixture" and not moved.exists()
    assert (observed[0]["rollback_step"], observed[0]["rollback_total"], observed[0]["rollback_recipe"]) == (1, 1, "move_file")
    assert ActivityQuery(ledger._db).undo_record_for_action(action)["rollback_ok"] == 1
    supervisor.finalize_task(cap.task_id, TaskState.STOPPED)
