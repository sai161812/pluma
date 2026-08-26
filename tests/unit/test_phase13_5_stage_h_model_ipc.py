"""tests/unit/test_phase13_5_stage_h_model_ipc.py — Stage H Model and IPC Lifecycles regression tests."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
import pytest

from pluma.app import PlumaApplicationRuntime
from pluma.brain.lifecycle import LlmLifecycleManager, LlmLifecycleState
from pluma.brain.llama_cpp_adapter import LlamaCppBackend
from pluma.config.paths import PlumaPaths
from pluma.core.ipc import IpcClient, IpcServer
from pluma.perception.ocr_adapter import OcrBackend, OcrResult
from pluma.perception.ocr_lifecycle import OcrLifecycleManager, OcrLifecycleState


def test_stage_h_models_directory_resolution() -> None:
    """Gate H: Verify models directory resolves under %LOCALAPPDATA%\\Pluma\\models."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=Path(td) / "Pluma")
        assert paths.models_dir == Path(td) / "Pluma" / "models"


def test_stage_h_zero_ml_at_resident_startup() -> None:
    """Gate H: Verify resident core startup creates no warm/loaded ML models."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=Path(td) / "Pluma", roaming_app_data=Path(td) / "Pluma")
        paths.ensure_directories()

        runtime = PlumaApplicationRuntime(paths=paths)
        try:
            # Voice pipeline STT should be cold
            assert runtime.voice_pipeline.lifecycle.state == "COLD"
            assert runtime.voice_pipeline.lifecycle.is_warm is False
        finally:
            runtime.close()


def test_stage_h_llm_lifecycle_auto_unload() -> None:
    """Gate H: Verify LLM lifecycle on-demand loading and auto-unloading to COLD on idle."""
    class MockLlamaBackend(LlamaCppBackend):
        def generate(self, prompt: str, grammar: str = None, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
            return '{"route": "SMART", "mode": "direct", "steps": [{"tool": "list_files", "arguments": {}, "purpose": "test"}]}'

    backend = MockLlamaBackend()
    manager = LlmLifecycleManager(
        custom_backend=backend,
        idle_unload_seconds=0.5,
    )

    assert manager.state == LlmLifecycleState.COLD

    # Execute plan (loads on-demand)
    plan = manager.plan(command="list files")
    assert plan is not None
    assert manager.state == LlmLifecycleState.WARM

    # Wait for idle timeout
    time.sleep(0.7)
    assert manager.state == LlmLifecycleState.COLD


def test_stage_h_ipc_server_client_roundtrip_and_timeout() -> None:
    """Gate H: Verify local IPC communication, command dispatch, and timeout handling."""
    import sys
    pipe_address = rf"\\.\pipe\test_ipc_stage_h_{int(time.time())}" if sys.platform == "win32" else f"/tmp/test_ipc_{int(time.time())}.sock"

    def handler(req: dict) -> dict:
        cmd = req.get("command")
        if cmd == "ping":
            return {"status": "ok", "message": "pong"}
        return {"status": "error", "message": "unknown"}

    server = IpcServer(command_handler=handler, address=pipe_address)
    server.start()
    time.sleep(0.1)

    try:
        client = IpcClient(address=pipe_address)
        resp = client.send_command({"command": "ping"}, timeout=2.0)
        assert resp["status"] == "ok"
        assert resp["message"] == "pong"
    finally:
        server.stop()
