"""Owned status-only fixture using the production IPC server; never starts ResidentCore."""
from pathlib import Path
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ["LOCALAPPDATA"] = sys.argv[2]

from pluma.core.ipc import IpcServer


def status(request):
    if request != {"command": "status"}:
        raise ValueError("Only the read-only status fixture is registered.")
    return {"status": "ok", "running": True, "active_tasks": 2, "voice_enabled": True,
            "padding": "x" * 24000}


server = IpcServer(status, address="\\\\.\\pipe\\" + sys.argv[1], require_auth=True)
try:
    server.start()
    if not server._running:
        raise RuntimeError("Fixture pipe did not start.")
    if any(name in sys.modules for name in ("torch", "whisper", "llama_cpp", "paddleocr")):
        raise RuntimeError("Status-only fixture imported a heavy inference runtime.")
    print("READY", flush=True)
    for line in sys.stdin:
        if line.strip() == "stop":
            break
finally:
    server.stop()
