"""pluma.ui.confirmations — User confirmation functional contract.

Spec §14, §15, §19:
Confirmation dialogs are functional contracts; visual UI design is decoupled.
High-risk and material operations request explicit user confirmation before execution.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from pluma.tools.base import RiskClass


@dataclass(frozen=True)
class ConfirmationRequest:
    """Request data for user confirmation prior to tool execution."""
    task_id: str
    tool_name: str
    arguments: Dict[str, Any]
    risk_class: RiskClass
    reason: str
    prompt_message: str
    target_summary: Optional[str] = None


@dataclass(frozen=True)
class ConfirmationResponse:
    """Outcome of a user confirmation request."""
    approved: bool
    reason: Optional[str] = None
    remember_for_session: bool = False


class ConfirmationContract(abc.ABC):
    """Abstract functional confirmation contract interface."""

    @abc.abstractmethod
    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationResponse:
        """Prompt user to confirm or deny an action. Blocks until answered."""
        raise NotImplementedError


class AutoApproveConfirmationContract(ConfirmationContract):
    """Confirmation handler that automatically approves all requests (for testing/automation)."""

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationResponse:
        return ConfirmationResponse(approved=True, reason="Auto-approved by policy test contract.")


class AutoDenyConfirmationContract(ConfirmationContract):
    """Confirmation handler that automatically denies all requests."""

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationResponse:
        return ConfirmationResponse(approved=False, reason="Auto-denied by policy safety contract.")


class CallbackConfirmationContract(ConfirmationContract):
    """Confirmation handler delegating to a custom callback function."""

    def __init__(self, callback: Callable[[ConfirmationRequest], ConfirmationResponse]) -> None:
        self._callback = callback

    def request_confirmation(self, request: ConfirmationRequest) -> ConfirmationResponse:
        return self._callback(request)


# Aliases for convenience
AutoApproveConfirmation = AutoApproveConfirmationContract
AutoDenyConfirmation = AutoDenyConfirmationContract
CallbackConfirmation = CallbackConfirmationContract
