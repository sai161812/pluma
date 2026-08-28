import os
import sys
import time
import uuid
from typing import Any, Dict

from pluma.core.ipc import IpcClient, IpcServer


def dummy_handler(request: Dict[str, Any]) -> Dict[str, Any]:
    if request.get("command") == "echo":
        return {"status": "ok", "echo": request.get("payload")}
    if request.get("command") == "error":
        raise ValueError("Simulated error")
    return {"status": "unknown"}


def test_ipc_roundtrip() -> None:
    uid = uuid.uuid4().hex[:8]
    address = rf"\\.\pipe\pluma_ipc_test_{os.getpid()}_{uid}" if sys.platform == "win32" else f"/tmp/pluma_ipc_test_{os.getpid()}_{uid}.sock"
    server = IpcServer(command_handler=dummy_handler, address=address)
    server.start()

    
    try:
        # Give it a moment to bind
        time.sleep(0.2)
        
        client = IpcClient(address=address)
        
        # Test 1: Echo
        resp = client.send_command({"command": "echo", "payload": "hello"})
        assert resp["status"] == "ok"
        assert resp["echo"] == "hello"
        
        # Test 2: Error handling
        resp = client.send_command({"command": "error"})
        assert resp["status"] == "error"
        assert "Simulated error" in resp["message"]
        
    finally:
        server.stop()


def test_ipc_no_server() -> None:
    # If server isn't running, client should return a clear error dict
    client = IpcClient()
    # Ensure it's using a unique/random pipe name so it definitely misses
    client.address += "_nonexistent"
    
    resp = client.send_command({"command": "echo"})
    assert resp["status"] == "error"
