"""pluma.brain.validator — Strict second-pass Plan validator.

Spec §10, §20.2: "Validate planner output against schema. Reject invented
tools or unpermitted calls before execution."
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from pydantic import BaseModel, ValidationError

from pluma.brain.schemas import MAX_PLAN_STEPS_HARD_CAP, Plan, ToolCall
from pluma.tools.registry import ToolRegistry, UnknownToolError

logger = logging.getLogger(__name__)


class PlanValidationError(ValueError):
    """Raised when a Plan fails structural, registry, or argument schema validation."""


class PlanValidator:
    """Performs strict validation of Plan instances and raw model JSON output."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self._registry = registry

    def validate_plan(
        self,
        plan: Plan,
        registry: Optional[ToolRegistry] = None,
        max_steps: int = MAX_PLAN_STEPS_HARD_CAP,
    ) -> Plan:
        """Validate an instantiated Plan against registry tools and schemas.

        Raises:
            PlanValidationError: If validation fails.
        """
        target_registry = registry or self._registry
        if target_registry is None:
            raise ValueError("A ToolRegistry must be provided to validate plan tools.")

        # 1. Step count check
        effective_max = min(max_steps, MAX_PLAN_STEPS_HARD_CAP)
        if not plan.steps:
            raise PlanValidationError("Plan must contain at least one step.")
        if len(plan.steps) > effective_max:
            raise PlanValidationError(
                f"Plan step count ({len(plan.steps)}) exceeds maximum allowed ({effective_max})."
            )

        # 2. Per-step tool & argument checks
        for idx, step in enumerate(plan.steps):
            tool_name = step.tool
            if not target_registry.contains(tool_name):
                raise PlanValidationError(
                    f"Step {idx + 1}: Unknown or unpermitted tool '{tool_name}' proposed by planner."
                )

            tool_spec = target_registry.lookup(tool_name)
            schema = tool_spec.args_schema

            # Validate arguments against Pydantic schema
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                try:
                    schema.model_validate(step.arguments)
                except ValidationError as val_err:
                    raise PlanValidationError(
                        f"Step {idx + 1} ({tool_name}): Argument schema validation failed: {val_err}"
                    ) from val_err
            elif isinstance(schema, dict):
                # Dict schema fallback check if required keys present
                required_keys = schema.get("required", [])
                for req in required_keys:
                    if req not in step.arguments:
                        raise PlanValidationError(
                            f"Step {idx + 1} ({tool_name}): Missing required argument '{req}'."
                        )

        return plan

    def parse_and_validate_json(
        self,
        raw_text: str,
        registry: Optional[ToolRegistry] = None,
        max_steps: int = MAX_PLAN_STEPS_HARD_CAP,
    ) -> Plan:
        """Parse raw JSON output from the model, handling markdown fences, and validate.

        Raises:
            PlanValidationError: If parsing or validation fails.
        """
        cleaned = raw_text.strip()
        # Strip markdown code blocks if the model wrapped output in ```json ... ```
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as dec_err:
            raise PlanValidationError(f"Failed to parse planner output as JSON: {dec_err}") from dec_err

        if not isinstance(data, dict):
            raise PlanValidationError("Planner output must be a JSON object.")

        try:
            plan = Plan.model_validate(data)
        except ValidationError as pydantic_err:
            raise PlanValidationError(f"Plan structure invalid: {pydantic_err}") from pydantic_err

        return self.validate_plan(plan, registry=registry, max_steps=max_steps)

    # Alias for convenience
    validate = parse_and_validate_json
