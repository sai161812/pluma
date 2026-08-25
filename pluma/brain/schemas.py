"""pluma.brain.schemas — Plan and ToolCall Pydantic models.

These are the contracts between the planner and the executor. The planner
may only output Plans that satisfy these schemas. The orchestrator validates
the plan output a second time (spec §10: "validate planner output against
schema. Reject invented tools...") before passing anything to the executor.

Spec §20.2 Plan constraints enforced here:
  - tool must exist in registry (checked by the orchestrator after creation)
  - arguments must validate (checked by the orchestrator via ToolRegistry)
  - target_ref must belong to a current snapshot (checked by the orchestrator)
  - max steps is bounded (max_steps field + validator)
  - every step re-checks task.stop_latch before starting (orchestrator, not here)

No OS-automation, ML, or adapter code in this module.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


# Maximum plan steps allowed. Matches config key `agent.max_plan_steps`.
# The loader will enforce the configured value at runtime; this constant
# is the hard cap — the config value must be <= this.
MAX_PLAN_STEPS_HARD_CAP = 20


class RouteMode(str, Enum):
    """Which execution path a command takes.

    Spec §9 routes:
      FAST   — deterministic, no LLM, no OCR.
      SCREEN — UIA ± targeted OCR, no LLM if target is unambiguous.
      SMART  — small local planner + file/system tools.
      DEEP   — UIA + targeted OCR + local planner + bounded multi-step.
    """
    FAST = "FAST"
    SCREEN = "SCREEN"
    SMART = "SMART"
    DEEP = "DEEP"


class PlanMode(str, Enum):
    """Whether the plan has a single step or multiple."""
    DIRECT = "direct"
    MULTI_STEP = "multi_step"


class ToolCall(BaseModel):
    """One step in a Plan: a validated reference to a registered tool.

    Spec §20.2 ToolCall fields:
      tool, arguments, target_ref?, purpose

    The planner may propose only registered ToolCalls (checked by the
    orchestrator using ToolRegistry.validate_call()).
    """

    model_config = {"frozen": True}

    tool: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Registered tool name. Must match ToolSpec.name exactly.",
    )
    arguments: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool arguments. Validated against ToolSpec.args_schema before execution.",
    )
    target_ref: Optional[str] = Field(
        default=None,
        description=(
            "Reference to a ScreenElement from the current ScreenSnapshot. "
            "Must belong to a non-expired snapshot — checked by the orchestrator."
        ),
    )
    purpose: str = Field(
        min_length=1,
        max_length=128,
        description=(
            "Short machine-facing reason for this step. Not shown to the user. "
            "Used for plan tracing and debugging only."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_invented_fields(cls, data: Any) -> Any:
        """Reject any fields not declared in this model.

        This catches planner output that injects extra keys hoping to bypass
        validation. Pydantic by default ignores extra fields; we forbid them.
        """
        if isinstance(data, dict):
            allowed = {"tool", "arguments", "target_ref", "purpose"}
            extra = set(data.keys()) - allowed
            if extra:
                raise ValueError(
                    f"ToolCall contains unexpected fields: {extra!r}. "
                    "Planner output must match the declared schema exactly."
                )
        return data


class Plan(BaseModel):
    """A validated sequence of ToolCall steps for one task.

    Spec §20.2 Plan fields: task_id, route, mode, steps[].
    """

    model_config = {"frozen": True}

    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()), min_length=1)
    route: Optional[RouteMode] = None
    mode: PlanMode = Field(default=PlanMode.DIRECT)
    steps: List[ToolCall] = Field(min_length=1)

    @model_validator(mode="after")
    def _enforce_step_limit(self) -> "Plan":
        """Reject plans that exceed the hard step cap.

        The configurable max_plan_steps (default 8) is enforced at runtime
        by the orchestrator using the loaded config value. This validator
        enforces the absolute ceiling regardless of config.
        """
        if len(self.steps) > MAX_PLAN_STEPS_HARD_CAP:
            raise ValueError(
                f"Plan for task {self.task_id!r} has {len(self.steps)} steps "
                f"which exceeds the hard cap of {MAX_PLAN_STEPS_HARD_CAP}."
            )
        return self

    @model_validator(mode="after")
    def _direct_plan_has_one_step(self) -> "Plan":
        """A DIRECT plan must have exactly one step."""
        if self.mode == PlanMode.DIRECT and len(self.steps) != 1:
            raise ValueError(
                f"A DIRECT plan must have exactly 1 step, got {len(self.steps)}."
            )
        return self


class PlanValidationError(ValueError):
    """Raised when the orchestrator's second-pass plan validation fails.

    Separate from Pydantic ValidationError so callers can distinguish
    schema-level from semantic-level failures.
    """
