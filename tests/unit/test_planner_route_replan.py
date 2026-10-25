from __future__ import annotations

import json

from pluma.brain.lifecycle import LlmLifecycleManager
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
from pluma.brain.schemas import RouteMode
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.task_supervisor import TaskSupervisor
from pluma.tools.registry import ToolRegistry, register_default_tools


def test_smart_failure_replan_keeps_same_route_tool_whitelist(tmp_path) -> None:
    fixture_dir = tmp_path / "planner-files"
    fixture_dir.mkdir()
    missing_path = fixture_dir / "missing.txt"
    (fixture_dir / "present.txt").write_text("owned fixture\n", encoding="utf-8")

    first = {
        "route": "SMART",
        "mode": "direct",
        "steps": [{
            "tool": "file_info",
            "arguments": {"path": str(missing_path)},
            "purpose": "Observe the known missing fixture",
        }],
    }
    recovery = {
        "route": "SMART",
        "mode": "direct",
        "steps": [{
            "tool": "list_folder",
            "arguments": {"path": str(fixture_dir)},
            "purpose": "Recover with a bounded directory observation",
        }],
    }

    class FixtureBackend:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def generate(self, **kwargs) -> str:
            self.calls.append(kwargs)
            return json.dumps(first if len(self.calls) == 1 else recovery)

    registry = ToolRegistry()
    register_default_tools(registry)
    backend = FixtureBackend()
    adapter = LlamaCppAdapter(custom_backend=backend, registry=registry)
    manager = LlmLifecycleManager(adapter=adapter, registry=registry)

    class SmartRouter:
        @staticmethod
        def route(_request):
            return RouteResult(route=RouteMode.SMART, reason="P13 file replan fixture")

    supervisor = TaskSupervisor()
    orchestrator = Orchestrator(
        registry=registry,
        supervisor=supervisor,
        router=SmartRouter(),
        llm_manager=manager,
    )
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=(f"First inspect the nonexistent file {missing_path}; when it is not found, "
              f"recover by listing the existing folder {fixture_dir}."),
    )

    try:
        result = orchestrator.execute(request)
        assert result.final_state == "SUCCEEDED"
        assert result.replan_count == 1
        assert [step.tool for step in result.steps] == ["file_info", "list_folder"]
        assert not result.steps[0].result.ok
        assert result.steps[1].result.ok and result.steps[1].result.verified
        assert len(backend.calls) == 2
        for call in backend.calls:
            prompt_tools = call["system_prompt"]
            assert "- file_info(" in prompt_tools
            assert "- list_folder(" in prompt_tools
            assert "- run_powershell(" not in prompt_tools
            assert "- open_url(" not in prompt_tools
        assert "PRIOR STEP RESULTS" in backend.calls[1]["prompt"]
        assert "file_info -> ok=False" in backend.calls[1]["prompt"]
    finally:
        manager.shutdown()
