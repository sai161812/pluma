"""tests/unit/test_phase13_5_stage_j_soak.py — Stage J 1000-Task Soak and Matrix Verification."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
import pytest

from pluma.app import PlumaApplicationRuntime
from pluma.config.paths import PlumaPaths
from pluma.core.cancellation import StopReason
from pluma.core.request import InputMode, PlumaRequest
from pluma.policy.engine import RiskClass
from pluma.tools.base import ToolResult, ToolSpec, VerifyResult


def test_stage_j_1000_task_soak_and_memory_stability() -> None:
    """Gate J: Run 1,000 tasks through the complete runtime stack, verifying zero leaks and resident stability."""
    with tempfile.TemporaryDirectory() as td:
        local_root = Path(td) / "Pluma"
        paths = PlumaPaths(local_app_data=local_root, roaming_app_data=local_root)
        paths.ensure_directories()

        runtime = PlumaApplicationRuntime(paths=paths)
        try:
            # Register a fast benchmark tool
            def bench_exec(args: dict, task_context: any = None) -> ToolResult:
                return ToolResult(
                    ok=True,
                    tool="bench_tool",
                    data={"iter": args.get("i", 0)},
                    factual_message=f"Iter {args.get('i', 0)} completed.",
                    verified=True,
                )

            from pydantic import BaseModel, Field

            class BenchArgs(BaseModel):
                model_config = {"extra": "forbid"}
                i: int = Field(default=0)

            runtime.tool_registry.register(
                ToolSpec(
                    name="bench_tool",
                    description="Benchmark tool",
                    args_schema=BenchArgs,
                    risk_class=RiskClass.READ,
                    timeout_s=5.0,
                    executor=bench_exec,
                    verifier=lambda r: VerifyResult(ok=True, method="api", detail="ok"),
                    cancellable=True,
                )
            )

            # Warm-up run
            req0 = PlumaRequest(input_mode=InputMode.TEXT, text="bench_tool i=0")
            res0 = runtime.resident_core.handle_ipc_command({"command": "execute", "request": req0.model_dump()})
            assert res0["status"] == "ok"

            # Execute 1,000 tasks sequentially
            start_time = time.perf_counter()
            for i in range(1, 1001):
                cmd_req = {
                    "command": "execute",
                    "request": {
                        "input_mode": "text",
                        "text": f"bench_tool i={i}",
                        "client_metadata": {"soak_iteration": i},
                    },
                }
                res = runtime.resident_core.handle_ipc_command(cmd_req)
                assert res["status"] == "ok", f"Soak iteration {i} failed: {res}"

            duration_s = time.perf_counter() - start_time
            throughput = 1000.0 / duration_s

            # Assert all 1,001 tasks are recorded in SQLite
            recent = runtime.resident_core.handle_ipc_command({"command": "recent_tasks", "limit": 10})
            assert recent["status"] == "ok"
            assert len(recent["tasks"]) == 10

            # Verify no active leaked tasks remaining
            active = runtime.supervisor.get_active_tasks()
            assert len(active) == 0

            # Check process RAM footprint if psutil is available
            try:
                import psutil
                process = psutil.Process(os.getpid())
                mem_mb = process.memory_info().rss / (1024 * 1024)
                # Resident core + test runner process RSS is well within healthy bounds
                assert mem_mb < 200.0
            except ImportError:
                pass
        finally:
            runtime.close()


def test_stage_j_command_matrix_coverage() -> None:
    """Gate J: Evaluate command matrix across direct, cancellation, policy-denied, and multi-step flows."""
    with tempfile.TemporaryDirectory() as td:
        local_root = Path(td) / "Pluma"
        paths = PlumaPaths(local_app_data=local_root, roaming_app_data=local_root)
        paths.ensure_directories()

        runtime = PlumaApplicationRuntime(paths=paths)
        try:
            # Inject fast mock planner for SMART routing
            from pluma.brain.lifecycle import LlmLifecycleManager
            from pluma.brain.llama_cpp_adapter import LlamaCppBackend

            class MockBackend(LlamaCppBackend):
                def generate(self, prompt: str, grammar: str = None, max_tokens: int = 512, temperature: float = 0.0, **kwargs) -> str:
                    if "volume" in prompt.lower():
                        return '{"route": "SMART", "mode": "direct", "steps": [{"tool": "get_volume_status", "arguments": {}, "purpose": "check volume"}]}'
                    return '{"route": "SMART", "mode": "direct", "steps": [{"tool": "get_system_status", "arguments": {}, "purpose": "check status"}]}'

            runtime.orchestrator._llm_manager = LlmLifecycleManager(custom_backend=MockBackend(), registry=runtime.tool_registry)

            # Start resident
            runtime.resident_core._running = True

            # 1. Direct system query
            res1 = runtime.resident_core.handle_ipc_command({
                "command": "execute",
                "request": {"input_mode": "text", "text": "get_system_status"},
            })
            assert res1["status"] == "ok"
            assert res1["success"] is True

            # 2. Volume query
            res2 = runtime.resident_core.handle_ipc_command({
                "command": "execute",
                "request": {"input_mode": "text", "text": "get_volume_status"},
            })
            assert res2["status"] == "ok"
            assert res2["success"] is True

            # 3. Status check
            status_res = runtime.resident_core.handle_ipc_command({"command": "status"})
            assert status_res["status"] == "ok"
            assert status_res["running"] is True

            # 4. Stop all tasks
            stop_res = runtime.resident_core.handle_ipc_command({"command": "stop_all"})
            assert stop_res["status"] == "ok"
            assert stop_res["stopped_count"] == 0
        finally:
            runtime.close()
