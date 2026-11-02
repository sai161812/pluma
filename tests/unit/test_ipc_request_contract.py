"""Versioned resident submit/ack/readback tests with an owned in-memory ledger."""
import threading
from collections import OrderedDict
from types import SimpleNamespace

import pytest

from pluma.core.resident import ResidentCore
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
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
    invalid_history = core.handle_ipc_command({
        "protocol_version": 1, "message_type": "history_query",
        "request_id": "9fb62f64-4eb4-42b3-b268-8c586a90da12", "limit": 101,
    })
    assert invalid_history["error_code"] == "INVALID_REQUEST"
    invalid_settings = core.handle_ipc_command({
        "protocol_version": 1, "message_type": "settings_query", "request_id": "not-a-uuid",
    })
    assert invalid_settings["error_code"] == "INVALID_REQUEST"


def test_settings_query_exposes_only_allowlisted_configuration(resident_fixture):
    core, _, _ = resident_fixture
    core.config = {
        "agent": {"text_hotkey": "alt+space", "stop_hotkey": "ctrl+alt+esc",
                  "max_plan_steps": 8, "default_tool_timeout_seconds": 15},
        "runtime": {"model_idle_unload_seconds": 30, "stt_idle_unload_seconds": 20,
                    "ocr_idle_unload_seconds": 10, "allow_short_warm_grace": True},
        "voice": {"required": True, "activation_default": "push_to_talk",
                  "wake_phrase_enabled": False, "save_audio": False,
                  "model_path": r"C:\private\models\whisper.ggml"},
        "perception": {"persist_screenshots": False, "ocr_enabled": True, "uia_first": True},
        "brain": {"runtime": "llama_cpp", "model_profile": "fixture-profile",
                  "model_path": r"C:\private\models\local.gguf"},
        "policy": {"confirm_high_risk": True, "redact_sensitive_logs": True,
                   "api_token": "private-settings-sentinel"},
        "memory": {"activity_view_enabled": True},
    }
    request_id = "210f74c3-f231-47fd-85cf-ea5b88c63c84"
    reply = core.handle_ipc_command({"protocol_version": 1, "message_type": "settings_query",
                                    "request_id": request_id})
    assert reply["message_type"] == "settings_snapshot"
    assert reply["submission_stop_fence"] is True
    assert reply["request_id"] == request_id
    assert reply["model_profile"] == "fixture-profile"
    assert reply["planner_model_path"] == r"C:\private\models\local.gguf"
    assert reply["stt_model_path"] == r"C:\private\models\whisper.ggml"
    assert "model_path" not in reply and "api_token" not in reply
    assert "private-settings-sentinel" not in str(reply)


def test_history_query_projects_redacted_task_and_action_records(resident_fixture):
    core, ledger, _ = resident_fixture
    task_id = "a30d93be-1110-4d54-9fd2-4bf03f9d595c"
    request_id = "9fb62f64-4eb4-42b3-b268-8c586a90da12"
    ledger.insert_task(TaskRecord(
        task_id=task_id, request_id=request_id, input_mode="text",
        command_text="open the owned fixture", created_at="2026-10-27T00:00:00+00:00",
        final_state="SUCCEEDED", route="FAST",
    ))
    action_id = ledger.insert_action(ActionRecord(
        task_id=task_id, step_index=0, tool="open_file", risk="LOW",
        args_raw={"path": r"C:\owned\fixture.txt", "token": "private-history-sentinel"},
        started_at="2026-10-27T00:00:01+00:00", ended_at="2026-10-27T00:00:02+00:00",
        duration_ms=1000.0, result_data={"opened": True}, verified=True,
    ))
    later_action_id = ledger.insert_action(ActionRecord(
        task_id=task_id, step_index=2, tool="read_file", risk="READ",
        args_raw={"path": r"C:\owned\fixture.txt"},
        started_at="2026-10-27T00:00:04+00:00",
    ))
    middle_action_id = ledger.insert_action(ActionRecord(
        task_id=task_id, step_index=1, tool="inspect_file", risk="READ",
        args_raw={"path": r"C:\owned\fixture.txt"},
        started_at="2026-10-27T00:00:03+00:00",
    ))
    # Owned in-memory legacy/corrupt data verifies that the IPC projection
    # redacts even if a prior row did not pass through today's write sanitizer.
    ledger._db.execute_write(
        "UPDATE tasks SET command_text = ? WHERE task_id = ?",
        ("paste private-history-command-payload", task_id),
    )
    ledger._db.execute_write(
        "UPDATE actions SET args_json_sanitized = ? WHERE id = ?",
        ('{"tool":"open_file","args":{"token":"private-history-sentinel"}}', action_id),
    )
    reply = core.handle_ipc_command({"protocol_version": 1, "message_type": "history_query",
                                    "request_id": "b8e32d47-bffc-4658-86d9-1e5522d4a1c9",
                                    "task_id": task_id})
    assert reply["message_type"] == "history_reply"
    assert reply["tasks"][0]["task_id"] == task_id
    assert reply["tasks"][0]["command_text"] == "[REDACTED CLIPBOARD COMMAND]"
    assert reply["actions"][0]["action_id"] == action_id
    assert [item["action_id"] for item in reply["actions"]] == [
        action_id, middle_action_id, later_action_id,
    ]
    assert [item["step_index"] for item in reply["actions"]] == [0, 1, 2]
    assert reply["actions"][0]["verified"] is True
    assert "private-history-sentinel" not in str(reply)
    assert reply["actions"][0]["arguments"]["args"]["token"] == "[REDACTED]"
    recent = core.handle_ipc_command({"protocol_version": 1, "message_type": "history_query",
                                     "request_id": "45aa5295-f1d4-413e-8e07-3439c9834c80",
                                     "limit": 10})
    assert [item["task_id"] for item in recent["tasks"]] == [task_id]
    bounded = core.handle_ipc_command({"protocol_version": 1, "message_type": "history_query",
                                      "request_id": "f35a8979-5c93-41c5-b2b2-fd307e77d5a5",
                                      "task_id": task_id, "limit": 2})
    assert bounded["error_code"] == "HISTORY_TOO_LARGE"
    missing = core.handle_ipc_command({"protocol_version": 1, "message_type": "history_query",
                                      "request_id": "cbbfdc78-c9d6-455a-9e29-56cb604951ac",
                                      "task_id": "1a55e945-4815-4c0e-9291-8ffef9cae048"})
    assert missing["error_code"] == "TASK_NOT_FOUND"


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
