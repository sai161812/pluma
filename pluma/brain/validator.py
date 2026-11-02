"""pluma.brain.validator — Strict second-pass Plan validator.

Spec §10, §20.2: "Validate planner output against schema. Reject invented
tools or unpermitted calls before execution."
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional

from pydantic import ValidationError

from pluma.brain.schemas import MAX_PLAN_STEPS_HARD_CAP, Plan, ToolCall
from pluma.tools.registry import ToolArgumentError, ToolRegistry

logger = logging.getLogger(__name__)


class PlanValidationError(ValueError):
    """Raised when a Plan fails structural, registry, or argument schema validation."""


class PlanValidator:
    """Performs strict validation of Plan instances and raw model JSON output."""

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        max_steps: int = 8,
    ) -> None:
        if (isinstance(max_steps, bool) or not isinstance(max_steps, int)
                or max_steps < 1 or max_steps > MAX_PLAN_STEPS_HARD_CAP):
            raise ValueError(
                f"max_steps must be an integer from 1 to {MAX_PLAN_STEPS_HARD_CAP}."
            )
        self._registry = registry
        self.max_steps = max_steps

    def validate_plan(
        self,
        plan: Plan,
        registry: Optional[ToolRegistry] = None,
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
        max_steps: Optional[int] = None,
    ) -> Plan:
        """Validate an instantiated Plan against registry tools and schemas.

        Raises:
            PlanValidationError: If validation fails.
        """
        target_registry = registry or self._registry
        if target_registry is None:
            raise ValueError("A ToolRegistry must be provided to validate plan tools.")

        # 1. Step count check
        configured_max = self.max_steps if max_steps is None else max_steps
        if (isinstance(configured_max, bool) or not isinstance(configured_max, int)
                or configured_max < 1 or configured_max > MAX_PLAN_STEPS_HARD_CAP):
            raise PlanValidationError(
                f"Maximum plan steps must be from 1 to {MAX_PLAN_STEPS_HARD_CAP}."
            )
        effective_max = min(configured_max, MAX_PLAN_STEPS_HARD_CAP)
        if not plan.steps:
            raise PlanValidationError("Plan must contain at least one step.")
        if len(plan.steps) > effective_max:
            raise PlanValidationError(
                f"Plan step count ({len(plan.steps)}) exceeds maximum allowed ({effective_max})."
            )

        # Permitted tools whitelist check
        allowed_names: Optional[set[str]] = None
        if permitted_tool_specs is not None:
            allowed_names = {
                spec.get("name") if isinstance(spec, dict) else getattr(spec, "name", str(spec))
                for spec in permitted_tool_specs
            }

        # 2. Per-step tool & argument checks
        for idx, step in enumerate(plan.steps):
            tool_name = step.tool
            if not target_registry.contains(tool_name):
                raise PlanValidationError(
                    f"Step {idx + 1}: Unknown or unpermitted tool '{tool_name}' proposed by planner."
                )

            if allowed_names is not None and tool_name not in allowed_names:
                raise PlanValidationError(
                    f"Step {idx + 1}: Tool '{tool_name}' is not in permitted_tool_specs for this planning call."
                )

            # Use the execution boundary's complete registered schema contract.
            # Never replace JSON Schema with a required-key-only fallback, or
            # include Pydantic input values in a planner-facing failure.
            try:
                target_registry.validate_call(tool_name, step.arguments)
            except ToolArgumentError:
                raise PlanValidationError(
                    f"Step {idx + 1} ({tool_name}): Argument schema validation failed."
                ) from None

        return plan

    def parse_and_validate_json(
        self,
        raw_text: str,
        registry: Optional[ToolRegistry] = None,
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
        max_steps: Optional[int] = None,
    ) -> Plan:
        """Parse raw JSON output from the model, handling markdown fences, and validate.

        Raises:
            PlanValidationError: If parsing or validation fails.
        """
        cleaned = raw_text.strip()
        # Strip markdown code blocks if the model wrapped output in ```json ... ```
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            # Never copy raw model text into errors; it may echo sensitive context.
            raise PlanValidationError("Model output is not valid JSON.") from None

        if not isinstance(payload, dict):
            raise PlanValidationError(
                f"Expected JSON object with 'steps', got {type(payload).__name__}."
            )

        try:
            plan = Plan.model_validate(payload)
        except ValidationError:
            # Pydantic errors can include offending values, so keep this factual and fixed.
            raise PlanValidationError("Plan structure invalid: schema validation failed.") from None

        return self.validate_plan(
            plan,
            registry=registry,
            permitted_tool_specs=permitted_tool_specs,
            max_steps=max_steps,
        )

    # Alias for convenience
    validate = parse_and_validate_json
