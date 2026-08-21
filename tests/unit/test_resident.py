"""tests.unit.test_resident — Tests for ResidentCore lifecycle."""

import sys

from pluma.core.resident import ResidentCore


def test_resident_core_lifecycle() -> None:
    address = r"\\.\pipe\pluma_ipc_test_resident" if sys.platform == "win32" else "/tmp/pluma_ipc_test_resident.sock"
    core = ResidentCore()
    core.ipc.address = address
    core.start()
    
    try:
        # Check it answers IPC
        from pluma.core.ipc import IpcClient
        client = IpcClient(address=address)
        resp = client.send_command({"command": "status"})
        assert resp["status"] == "ok"
        
        # Test stop via IPC
        resp = client.send_command({"command": "stop_all"})
        assert resp["status"] == "ok"
        assert "stopped" in resp["message"]
        
    finally:
        core.stop()


def test_resident_core_no_ml_modules_loaded() -> None:
    """Gate test: Ensure no ML runtimes are loaded merely because ResidentCore starts."""
    address = r"\\.\pipe\pluma_ipc_test_resident_2" if sys.platform == "win32" else "/tmp/pluma_ipc_test_resident_2.sock"
    core = ResidentCore()
    core.ipc.address = address
    core.start()
    try:
        assert "whisper" not in sys.modules
        assert "llama_cpp" not in sys.modules
        assert "paddleocr" not in sys.modules
        assert "torch" not in sys.modules
    finally:
        core.stop()
