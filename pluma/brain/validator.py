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
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
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
        permitted_tool_specs: Optional[List[Dict[str, Any]]] = None,
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
            cleaned = re.sub(r"\n?```$", "", cleaned)
            cleaned = cleaned.strip()

        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as json_err:
            raise PlanValidationError(
                f"Model output is not valid JSON: {json_err}. Raw text: {raw_text[:200]!r}"
            ) from json_err

        if not isinstance(payload, dict):
            raise PlanValidationError(
                f"Expected JSON object with 'steps', got {type(payload).__name__}."
            )

        try:
            plan = Plan.model_validate(payload)
        except ValidationError as val_err:
            raise PlanValidationError(f"Plan structure invalid: Schema validation failed: {val_err}") from val_err

        return self.validate_plan(
            plan,
            registry=registry,
            permitted_tool_specs=permitted_tool_specs,
            max_steps=max_steps,
        )

    # Alias for convenience
    validate = parse_and_validate_json
