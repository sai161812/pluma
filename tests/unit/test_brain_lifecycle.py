"""tests/unit/test_brain_lifecycle.py — Phase 9: LlmLifecycleManager unit tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock
import pytest

from pluma.brain.interface import PlannerCancelledError
from pluma.brain.lifecycle import LlmLifecycleManager, LlmLifecycleState
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core.cancellation import CancellationToken


def test_llm_lifecycle_cold_at_init() -> None:
    manager = LlmLifecycleManager(idle_unload_seconds=0.2)
    assert manager.state == LlmLifecycleState.COLD


def test_llm_lifecycle_warm_after_planning() -> None:
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "direct", "steps": '
        '[{"tool": "list_files", "arguments": {"path": "C:\\\\"}, "purpose": "List root"}]}'
    )

    manager = LlmLifecycleManager(
        custom_backend=mock_backend,
        idle_unload_seconds=0.5,
    )

    plan = manager.plan("List files in root")
    assert plan.route == RouteMode.SMART
    assert len(plan.steps) == 1
    assert manager.state == LlmLifecycleState.WARM


def test_llm_lifecycle_idle_unload() -> None:
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "direct", "steps": '
        '[{"tool": "list_files", "arguments": {"path": "C:\\\\"}, "purpose": "List root"}]}'
    )

    # 0.1 second idle unload
    manager = LlmLifecycleManager(
        custom_backend=mock_backend,
        idle_unload_seconds=0.1,
    )

    manager.plan("List files in root")
    assert manager.state == LlmLifecycleState.WARM

    # Wait for idle timeout
    time.sleep(0.25)
    assert manager.state == LlmLifecycleState.COLD


def test_llm_lifecycle_shutdown() -> None:
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "direct", "steps": '
        '[{"tool": "list_files", "arguments": {"path": "C:\\\\"}, "purpose": "List root"}]}'
    )

    manager = LlmLifecycleManager(
        custom_backend=mock_backend,
        idle_unload_seconds=10.0,
    )

    manager.plan("List files in root")
    assert manager.state == LlmLifecycleState.WARM

    manager.shutdown()
    assert manager.state == LlmLifecycleState.COLD


def test_llm_lifecycle_cancellation() -> None:
    mock_backend = MagicMock()
    manager = LlmLifecycleManager(custom_backend=mock_backend)

    token = CancellationToken()
    token.cancel()

    with pytest.raises(PlannerCancelledError):
        manager.plan("List files in root", cancellation_token=token)
