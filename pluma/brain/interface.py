"""pluma.brain.interface — Planner abstract interface.

Spec §10: Planner.plan(command, context, permitted_tool_specs,
screen_snapshot=None, prior_step_results=None, cancellation_token=None) -> Plan

The planner may propose ONLY registered ToolCalls.
It must never import pywinauto, Win32, PowerShell, OCR or shell libraries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from pluma.brain.schemas import Plan
    from pluma.core.cancellation import CancellationToken
    from pluma.perception.element_refs import ScreenSnapshot


class PlannerError(RuntimeError):
    """Raised when the planner cannot produce a valid plan."""


class PlannerTimeoutError(PlannerError):
    """Raised when local model inference exceeds wall-clock timeout."""


class PlannerCancelledError(PlannerError):
    """Raised when planning is cancelled via CancellationToken."""


class PlannerInterface(ABC):
    """Abstract planner interface. Concrete implementations in Phase 9."""

    @abstractmethod
    def plan(
        self,
        command: str,
        context: Dict[str, Any],
        permitted_tool_specs: List[Dict[str, Any]],
        screen_snapshot: Optional["ScreenSnapshot"] = None,
        prior_step_results: Optional[List[Dict[str, Any]]] = None,
        cancellation_token: Optional["CancellationToken"] = None,
    ) -> "Plan":
        """Produce a validated Plan for *command*.

        Args:
            command: The normalised text command.
            context: Minimal relevant context (active process, window, etc.).
            permitted_tool_specs: Only the tool schemas relevant to this route.
            screen_snapshot: Optional snapshot for SCREEN/DEEP routes.
            prior_step_results: Results from earlier steps in multi-step plans.
            cancellation_token: Optional cancellation token to abort planning.

        Returns:
            A validated Plan. Raises PlannerError on failure.
        """
        ...
