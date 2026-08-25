"""tests/unit/test_brain_validator.py — Phase 9: PlanValidator unit tests."""

from __future__ import annotations

import json
import pytest

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.tools.registry import get_default_tool_registry


def test_validate_plan_valid() -> None:
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[
            ToolCall(
                tool="create_folder",
                arguments={"path": "C:\\temp\\test_folder"},
                purpose="Create target directory",
            )
        ],
    )

    validated = validator.validate_plan(plan)
    assert validated == plan


def test_validate_plan_empty_steps_fails() -> None:
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    # Parsing empty steps should raise PlanValidationError
    raw_json = '{"route": "SMART", "mode": "direct", "steps": []}'
    with pytest.raises(PlanValidationError, match="Plan structure invalid|at least one step"):
        validator.parse_and_validate_json(raw_json)


def test_validate_plan_invented_tool_rejected() -> None:
    """Verify hallucinated/invented tools are rejected (Acceptance Test F-03)."""
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[
            ToolCall(
                tool="non_existent_magic_tool",
                arguments={"foo": "bar"},
                purpose="Hallucinated tool",
            )
        ],
    )

    with pytest.raises(PlanValidationError, match="Unknown or unpermitted tool"):
        validator.validate_plan(plan)


def test_validate_plan_argument_schema_mismatch() -> None:
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    # rename_file requires path and new_name
    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[
            ToolCall(
                tool="rename_file",
                arguments={"wrong_key": "abc"},
                purpose="Rename file with wrong schema",
            )
        ],
    )

    with pytest.raises(PlanValidationError, match="Argument schema validation failed"):
        validator.validate_plan(plan)


def test_parse_and_validate_json_markdown_fences() -> None:
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    raw_json = """```json
    {
      "route": "SMART",
      "mode": "direct",
      "steps": [
        {
          "tool": "list_files",
          "arguments": {"path": "C:\\\\Windows"},
          "purpose": "List directory"
        }
      ]
    }
    ```"""

    plan = validator.parse_and_validate_json(raw_json)
    assert plan.route == RouteMode.SMART
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "list_files"


def test_validate_plan_exceeds_max_steps() -> None:
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    # 4 steps exceeding custom max_steps=2
    steps = [
        ToolCall(tool="list_files", arguments={"path": f"C:\\\\test{i}"}, purpose="test")
        for i in range(4)
    ]
    plan = Plan(route=RouteMode.SMART, mode=PlanMode.MULTI_STEP, steps=steps)

    with pytest.raises(PlanValidationError, match="exceeds maximum allowed"):
        validator.validate_plan(plan, max_steps=2)
