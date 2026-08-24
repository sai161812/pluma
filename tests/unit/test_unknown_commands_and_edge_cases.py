"""tests/unit/test_unknown_commands_and_edge_cases.py — Intelligent unknown command & edge case handling tests."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from pydantic import ValidationError

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec
from pluma.tools.registry import ToolArgumentError, ToolRegistry, get_default_tool_registry
from pluma.verify.common import verify_noop


@pytest.fixture
def clean_db():
    db = DbConnection(":memory:")
    db.open()
    yield db
    db.close()


@pytest.fixture
def ledger(clean_db):
    return ActivityLedger(db=clean_db)


@pytest.fixture
def orchestrator(ledger):
    registry = get_default_tool_registry()
    supervisor = TaskSupervisor(ledger=ledger)
    router = Router()
    return Orchestrator(
        router=router,
        registry=registry,
        supervisor=supervisor,
        ledger=ledger,
    )


def test_unknown_gibberish_command_handled_intelligently(orchestrator: Orchestrator) -> None:
    """Verify that gibberish or nonsensical commands return a clear, deterministic factual summary without crashing."""
    req = PlumaRequest(input_mode=InputMode.TEXT, text="asdfghjk qwerty 12345")
    res = orchestrator.execute(req)

    assert res.final_state in ("FAILED", "BLOCKED")
    assert res.error is not None
    # User-visible message must be clear and deterministic
    assert "Cannot execute" in res.factual_summary
    assert res.duration_ms is not None and res.duration_ms >= 0


def test_empty_and_whitespace_request_rejected_at_schema_boundary() -> None:
    """Verify that empty or whitespace-only requests are rejected immediately by PlumaRequest validation."""
    with pytest.raises(ValidationError):
        PlumaRequest(input_mode=InputMode.TEXT, text="   ")

    with pytest.raises(ValidationError):
        PlumaRequest(input_mode=InputMode.TEXT, text="")


def test_unsupported_capability_rejection_by_validator() -> None:
    """Verify that when a plan requests a hallucinated/unsupported tool, PlanValidator rejects it with a clear error."""
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    # Hallucinated tool not in registry
    hallucinated_plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[
            ToolCall(tool="teleport_cursor_to_sun", arguments={}, purpose="Attempt teleportation"),
        ],
    )

    with pytest.raises(PlanValidationError) as exc_info:
        validator.validate_plan(hallucinated_plan)

    assert "teleport_cursor_to_sun" in str(exc_info.value)


def test_empty_steps_plan_rejection() -> None:
    """Verify that a plan with 0 steps is rejected by Plan validation schema."""
    with pytest.raises(ValidationError) as exc_info:
        Plan(
            route=RouteMode.SMART,
            mode=PlanMode.DIRECT,
            steps=[],
        )

    assert "at least 1 item" in str(exc_info.value).lower()


def test_unknown_command_with_mock_planner(clean_db: DbConnection, ledger: ActivityLedger) -> None:
    """Verify that when the LLM planner reports unable to plan, the orchestrator reports a clean factual failure."""
    registry = get_default_tool_registry()
    supervisor = TaskSupervisor(ledger=ledger)
    router = Router()

    # Mock planner simulating unknown command where LLM cannot find valid tool
    mock_llm = MagicMock()
    mock_llm.plan.side_effect = PlanValidationError("Unknown tool: 'make_espresso'")

    orch = Orchestrator(
        router=router,
        registry=registry,
        supervisor=supervisor,
        ledger=ledger,
        llm_manager=mock_llm,
    )

    req = PlumaRequest(input_mode=InputMode.TEXT, text="make me a double espresso")
    res = orch.execute(req)

    assert res.final_state == "FAILED"
    assert "no supported capability or tool available" in res.factual_summary
    assert res.task_id is not None

    # Activity ledger must contain the recorded failed task
    query = ActivityQuery(db=clean_db)
    task_rec = query.task_by_id(res.task_id)
    assert task_rec is not None
    assert task_rec["final_state"] == "FAILED"


def test_tool_execution_with_invalid_arguments_raises_argument_error() -> None:
    """Verify that invalid arguments (e.g. string for integer volume) raise ToolArgumentError."""
    registry = get_default_tool_registry()

    with pytest.raises(ToolArgumentError):
        registry.execute("set_volume", {"level": "invalid_string_level"})
