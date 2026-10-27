"""Owned authenticated IPC fixture using the production transport/handler."""
from pathlib import Path
import json
import os
import sys
import threading
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["LOCALAPPDATA"] = sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else "status"
saturate_status = len(sys.argv) > 4 and sys.argv[4] == "saturate"

from pluma.core.ipc import IpcServer


def status(request):
    if request != {"command": "status"}:
        raise ValueError("Only the read-only status fixture is registered.")
    return {"status": "ok", "running": True, "active_tasks": 2, "voice_enabled": True,
            "padding": "x" * 24000}


db = None
release_status = threading.Event()
event_lock = threading.Lock()


def report_event(value):
    with event_lock:
        sys.stdout.write(value + "\n")
        sys.stdout.flush()


if mode == "versioned":
    from pluma.core.resident import ResidentCore
    from pluma.core.task_supervisor import TaskState, TaskSupervisor
    from pluma.config.loader import load_config
    from pluma.memory.activity import ActivityLedger
    from pluma.memory.db import DbConnection

    db = DbConnection(":memory:")
    db.open()
    ledger = ActivityLedger(db)
    supervisor = TaskSupervisor(ledger=ledger)

    class FixtureOrchestrator:
        def execute(self, request, capsule):
            supervisor.start_task(capsule.task_id)
            if request.text == "fixture:hold":
                report_event("TASK_ENTERED")
                if not capsule.cancellation_token.wait_for_cancel(8):
                    raise TimeoutError("Owned fixture wait expired.")
                capsule.cancellation_token.raise_if_cancelled()
            supervisor.finalize_task(capsule.task_id, TaskState.SUCCEEDED)
            return SimpleNamespace(
                final_state=TaskState.SUCCEEDED, completion_verified=True,
                terminal_persisted=True, has_residual=False,
                route=SimpleNamespace(value="FAST"),
                user_message="Fixture result verified.", duration_ms=1.0,
            )

    core = ResidentCore.__new__(ResidentCore)
    core.ledger = ledger
    core.supervisor = supervisor
    core.orchestrator = FixtureOrchestrator()
    core.config = load_config(Path(sys.argv[2]) / "no-user-settings.json")
    core.config["brain"]["model_path"] = r"C:\fixture\planner.gguf"
    core.config["voice"]["model_path"] = r"C:\fixture\whisper.ggml"

    def handler(request):
        if request == {"command": "status"}:
            if saturate_status:
                report_event("STATUS_ENTERED")
                release_status.wait(8)
            return status(request)
        if request.get("message_type") == "stop":
            release_status.set()
        return core.handle_ipc_command(request)
elif mode == "status":
    handler = status
else:
    raise ValueError("Unsupported owned IPC fixture mode.")

server = IpcServer(handler, address="\\\\.\\pipe\\" + sys.argv[1], require_auth=True)
try:
    server.start()
    if not server._running:
        raise RuntimeError("Fixture pipe did not start.")
    if any(name in sys.modules for name in ("torch", "whisper", "llama_cpp", "paddleocr")):
        raise RuntimeError("An IPC fixture imported a heavy inference runtime.")
    print("READY", flush=True)
    for line in sys.stdin:
        if line.strip() == "stop":
            break
finally:
    # Release any test-only blocking handler before asking the production IPC
    # server to drain its owned client threads.
    release_status.set()
    try:
        server.stop(timeout_s=4.0)
    except Exception:
        with server._clients_lock:
            remaining = [(thread.name, thread.is_alive(), type(conn).__name__)
                         for thread, conn in server._clients.items()]
        print(f"IPC_FIXTURE_REMAINING_OWNERS {remaining!r}", flush=True)
        raise
    if db is not None:
        supervisor.stop_all_active_tasks()
        for thread in list(getattr(core, "_submission_threads", {}).values()):
            thread.join(timeout=2)
            if thread.is_alive():
                raise RuntimeError("Owned fixture task did not exit.")
        db.close()
