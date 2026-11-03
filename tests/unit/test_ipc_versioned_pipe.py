"""Authenticated native-message Python IPC round trips for the v1 resident protocol."""
import os
import sys
import time
import uuid
from types import SimpleNamespace

from pluma.core.ipc import IpcClient, IpcServer
from pluma.core.resident import ResidentCore
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection


def test_authenticated_native_pipe_submit_stop_and_readback(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    db = DbConnection(":memory:")
    db.open()
    ledger = ActivityLedger(db)
    supervisor = TaskSupervisor(ledger=ledger)

    class FixtureOrchestrator:
        def execute(self, request, capsule):
            supervisor.start_task(capsule.task_id)
            supervisor.finalize_task(capsule.task_id, TaskState.SUCCEEDED)
            return SimpleNamespace(
                final_state=TaskState.SUCCEEDED, completion_verified=True,
                terminal_persisted=True, has_residual=False,
                route=SimpleNamespace(value="FAST"),
                user_message="Fixture result verified.", duration_ms=1.0,
            )

    core = ResidentCore.__new__(ResidentCore)
    core.ledger, core.supervisor = ledger, supervisor
    core.orchestrator = FixtureOrchestrator()
    address = (rf"\\.\pipe\pluma_v1_{os.getpid()}_{uuid.uuid4().hex}" if sys.platform == "win32"
               else str(tmp_path / "pluma_v1.sock"))
    server = IpcServer(core.handle_ipc_command, address=address, require_auth=True)
    server.start()
    client = IpcClient(address=address)
    request_id = str(uuid.uuid4())
    try:
        assert server._running
        ack = client.send_command({
            "protocol_version": 1, "message_type": "submit_text",
            "request_id": request_id, "text": "fixture:read only",
        })
        assert ack["message_type"] == "submission_ack" and ack["accepted"] is True
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            result = client.send_command({
                "protocol_version": 1, "message_type": "terminal_readback",
                "request_id": request_id, "task_id": ack["task_id"],
            })
            if result.get("terminal"):
                break
            time.sleep(0.02)
        assert result["terminal"] is True
        assert result["completion_verified"] is True
        assert result["terminal_persisted"] is True
        stop_id = str(uuid.uuid4())
        stop = client.send_command({
            "protocol_version": 1, "message_type": "stop",
            "request_id": stop_id, "task_id": ack["task_id"],
        })
        assert stop["message_type"] == "stop_ack" and stop["request_id"] == stop_id
        assert len(stop["tasks"]) == 1
        assert stop["tasks"][0]["outcome"] == "terminal"
        assert stop["tasks"][0]["final_state"] == "SUCCEEDED"
    finally:
        server.stop(timeout_s=4)
        supervisor.stop_all_active_tasks()
        for thread in list(core._submission_threads.values()):
            thread.join(timeout=2)
            assert not thread.is_alive()
        db.close()
