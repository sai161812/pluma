"""tests/unit/test_brain_llama_cpp_adapter.py — Phase 9: LlamaCppAdapter unit tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
import pytest

from pluma.brain.interface import PlannerCancelledError, PlannerError
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import CancellationToken


def test_llama_cpp_not_imported_at_module_level() -> None:
    """Verify that importing pluma.brain does NOT import llama_cpp."""
    import pluma.brain
    import pluma.brain.llama_cpp_adapter
    import pluma.brain.lifecycle
    assert "llama_cpp" not in sys.modules, "llama_cpp must not be imported at module level"


def test_llama_cpp_adapter_plan_success() -> None:
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "direct", "steps": '
        '[{"tool": "create_folder", "arguments": {"path": "C:\\\\docs"}, "purpose": "Create folder"}]}'
    )

    adapter = LlamaCppAdapter(custom_backend=mock_backend)
    plan = adapter.plan("Create folder C:\\docs")

    assert isinstance(plan, Plan)
    assert plan.route == RouteMode.SMART
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "create_folder"
    assert plan.steps[0].arguments["path"] == "C:\\docs"
    mock_backend.generate.assert_called_once()


def test_llama_cpp_adapter_complex_file_command() -> None:
    """Complex file command produces multi-step plan with file schemas only (Acceptance Test F-02)."""
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "multi_step", "steps": ['
        '{"tool": "find_file", "arguments": {"pattern": "report.pdf", "directory": "C:\\\\downloads"}, "purpose": "Find file"},'
        '{"tool": "move_file", "arguments": {"source": "C:\\\\downloads\\\\report.pdf", "destination": "C:\\\\archive\\\\report.pdf"}, "purpose": "Move file"}'
        ']}'
    )

    adapter = LlamaCppAdapter(custom_backend=mock_backend)
    plan = adapter.plan(
        "Find report.pdf in downloads and move it to archive",
        route=RouteMode.SMART,
    )

    assert plan.mode == PlanMode.MULTI_STEP
    assert len(plan.steps) == 2
    assert plan.steps[0].tool == "find_file"
    assert plan.steps[1].tool == "move_file"
    system_prompt = mock_backend.generate.call_args.kwargs["system_prompt"]
    assert "- find_file(" in system_prompt
    assert "- move_file(" in system_prompt
    assert "- open_app(" not in system_prompt
    assert "- focus_window(" not in system_prompt
    assert "- open_url(" not in system_prompt
    assert "- download_status(" not in system_prompt


def test_llama_cpp_adapter_invalid_output_raises_error() -> None:
    mock_backend = MagicMock()
    mock_backend.generate.return_value = "This is not valid JSON"

    adapter = LlamaCppAdapter(custom_backend=mock_backend)
    with pytest.raises(PlannerError, match="validation failed"):
        adapter.plan("Do something")


def test_backend_timeout_error_is_not_misreported_as_inference_deadline() -> None:
    class Backend:
        def generate(self, **kwargs):
            raise TimeoutError("fixture backend timeout")

    adapter = LlamaCppAdapter(custom_backend=Backend(), inference_timeout_s=1.0)
    with pytest.raises(PlannerError, match="Model generation failed"):
        adapter.plan("Do something")


def test_llama_cpp_adapter_cancellation() -> None:
    mock_backend = MagicMock()
    adapter = LlamaCppAdapter(custom_backend=mock_backend)

    token = CancellationToken()
    token.cancel()

    with pytest.raises(PlannerCancelledError):
        adapter.plan("Do something", cancellation_token=token)

    mock_backend.generate.assert_not_called()
