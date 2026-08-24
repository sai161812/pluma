"""Unit tests for ActivityLedger lifecycle and query (Spec §16, §20)."""
import json
import pytest
from pluma.memory.activity import (
    ActionRecord,
    ActivityLedger,
    ActivityQuery,
    ResourceRecord,
    ScreenEventRecord,
    TaskRecord,
    UndoRecord,
)
from pluma.memory.db import DbConnection
from pluma.tools.system import execute_show_activity


@pytest.fixture
def memory_db():
    conn = DbConnection(":memory:")
    conn.open()
    yield conn
    conn.close()


def test_task_lifecycle_writes_and_queries(memory_db):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)

    task_id = "task-life-1"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-100",
        input_mode="text",
        command_text="Set volume 50",
        active_process="notepad.exe",
        active_window="Untitled - Notepad",
    ))

    t = query.task_by_id(task_id)
    assert t is not None
    assert t["command_text"] == "Set volume 50"
    assert t["active_process"] == "notepad.exe"
    assert t["active_window"] == "Untitled - Notepad"

    # Update task lifecycle
    ledger.update_task(
        task_id,
        started_at="2026-08-22T00:00:01Z",
        completed_at="2026-08-22T00:00:02Z",
        final_state="SUCCEEDED",
        route="FAST",
    )

    t2 = query.task_by_id(task_id)
    assert t2["final_state"] == "SUCCEEDED"
    assert t2["route"] == "FAST"
    assert t2["started_at"] == "2026-08-22T00:00:01Z"


def test_action_records_and_redaction(memory_db):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)

    task_id = "task-redact-1"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-200",
        input_mode="text",
        command_text="Type password",
    ))

    # Action with sensitive fields
    act_id = ledger.insert_action(ActionRecord(
        task_id=task_id,
        step_index=0,
        tool="send_text",
        args_raw={"password": "super_secret_password_123", "text": "normal_text", "token": "abc123secrettoken"},
        risk="LOW",
        adapter="native",
        verified=True,
    ))

    actions = query.actions_for_task(task_id)
    assert len(actions) == 1
    raw_sanitized = json.loads(actions[0]["args_json_sanitized"])
    sanitized_args = raw_sanitized["args"]

    assert sanitized_args["password"] == "[REDACTED]"
    assert sanitized_args["token"] == "[REDACTED]"
    assert sanitized_args["text"] == "normal_text"
    assert actions[0]["verified"] == 1


def test_resource_tracking(memory_db):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)

    task_id = "task-res-1"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-300",
        input_mode="text",
        command_text="Run command",
    ))

    res_id = "res-subproc-1"
    ledger.insert_resource(ResourceRecord(
        id=res_id,
        task_id=task_id,
        resource_type="subprocess",
        ownership="PLUMA_CREATED",
        external_id="12345",
        metadata={"cmd": "powershell.exe"},
    ))

    resources = query.resources_for_task(task_id)
    assert len(resources) == 1
    assert resources[0]["id"] == res_id
    assert resources[0]["external_id"] == "12345"
    assert resources[0]["released_at"] is None

    # Mark released
    ledger.release_resource(res_id, released_at="2026-08-22T00:00:10Z")
    resources2 = query.resources_for_task(task_id)
    assert resources2[0]["released_at"] == "2026-08-22T00:00:10Z"


def test_screen_events_metadata(memory_db):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)

    task_id = "task-screen-1"
    ledger.insert_task(TaskRecord(
        task_id=task_id,
        request_id="req-400",
        input_mode="text",
        command_text="Click button",
    ))

    row_id = ledger.insert_screen_event(ScreenEventRecord(
        task_id=task_id,
        snapshot_id="snap-001",
        source="UIA",
        target_label="Save Button",
        control_type="Button",
        bounds={"left": 100, "top": 200, "width": 50, "height": 30},
        confidence=1.0,
        active_window_signature="notepad.exe|Untitled - Notepad",
    ))
    assert row_id is not None

    events = query.screen_events_for_task(task_id)
    assert len(events) == 1
    assert events[0]["target_label"] == "Save Button"
    assert events[0]["source"] == "UIA"
    assert events[0]["snapshot_id"] == "snap-001"


def test_show_activity_executor_with_query(memory_db):
    ledger = ActivityLedger(memory_db)
    query = ActivityQuery(memory_db)

    ledger.insert_task(TaskRecord(
        task_id="t1",
        request_id="r1",
        input_mode="text",
        command_text="Mute",
        final_state="SUCCEEDED",
    ))
    ledger.insert_task(TaskRecord(
        task_id="t2",
        request_id="r2",
        input_mode="text",
        command_text="Volume 30",
        final_state="SUCCEEDED",
    ))

    class DummyContext:
        def __init__(self, q):
            self.query = q

    res = execute_show_activity({"limit": 5}, task_context=DummyContext(query))
    assert res.ok
    assert res.data["count"] == 2
    assert "Retrieved 2 recent Activity records" in res.factual_message
