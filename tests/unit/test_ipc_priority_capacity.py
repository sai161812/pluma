"""STOP keeps one authenticated IPC handler available under normal saturation."""
import os
import sys
import threading
import time
import uuid

from pluma.core.ipc import IpcClient, IpcServer


def test_authenticated_stop_uses_reserved_handler_when_31_requests_are_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    address = (rf"\\.\pipe\pluma_priority_{os.getpid()}_{uuid.uuid4().hex}" if sys.platform == "win32"
               else str(tmp_path / "pluma_priority.sock"))
    entered = 0
    entered_lock = threading.Lock()
    all_entered = threading.Event()
    release = threading.Event()
    stopped = threading.Event()
    replies = []

    def handle(request):
        nonlocal entered
        if request.get("command") == "slow":
            with entered_lock:
                entered += 1
                if entered == 31:
                    all_entered.set()
            if not release.wait(8):
                raise TimeoutError("Owned saturation fixture did not release.")
            return {"status": "ok", "kind": "released"}
        if request.get("command") == "stop":
            stopped.set()
            release.set()
            return {"status": "ok", "kind": "stop"}
        return {"status": "error", "message": "Unknown fixture request."}

    server = IpcServer(handle, address=address, require_auth=True, read_timeout_s=10)
    workers = [threading.Thread(
        target=lambda: replies.append(IpcClient(address=address).send_command({"command": "slow"}, timeout=12)),
        name=f"OwnedIpcClient-{index}") for index in range(31)]
    server.start()
    try:
        assert server._running
        for worker in workers:
            worker.start()
        assert all_entered.wait(7), f"only {entered} ordinary requests entered their owned handlers"
        started = time.monotonic()
        receipt = IpcClient(address=address).send_command({"command": "stop"}, timeout=3)
        elapsed = time.monotonic() - started
        assert receipt == {"status": "ok", "kind": "stop"}
        assert stopped.is_set()
        assert elapsed < 2.5
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=4)
        server.stop(timeout_s=4)
    assert all(not worker.is_alive() for worker in workers)
    assert len(replies) == 31
    assert all(reply == {"status": "ok", "kind": "released"} for reply in replies)
