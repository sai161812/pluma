"""pluma.policy.engine — Deterministic policy evaluation engine.

Spec §14, §15:
- Evaluates every ToolCall before execution against risk rules.
- Autonomously allows READ and LOW risk operations.
- Intercepts HIGH risk operations and requires explicit user confirmation.
- Strictly blocks RESTRICTED operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any, Dict, Optional

from pluma.policy.rules import PolicyRules
from pluma.tools.base import RiskClass
from pluma.ui.confirmations import ConfirmationContract, ConfirmationRequest, ConfirmationResponse

logger = logging.getLogger(__name__)


class PolicyDecision(str, Enum):
    """Outcomes of a policy evaluation."""
    ALLOW = "ALLOW"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    DENY = "DENY"


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Detailed outcome of policy engine evaluation."""
    decision: PolicyDecision
    risk_class: RiskClass
    reason: str
    requires_confirmation: bool = False
    requires_elevation: bool = False


class PolicyEngine:
    """Deterministic policy evaluation engine."""

    def __init__(
        self,
        rules: Optional[PolicyRules] = None,
        confirmation_contract: Optional[ConfirmationContract] = None,
    ) -> None:
        self.rules = rules or PolicyRules()
        self.confirmation_contract = confirmation_contract

    def evaluate(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        default_risk: RiskClass = RiskClass.LOW,
        task_id: Optional[str] = None,
    ) -> PolicyEvaluationResult:
        """Evaluate a tool invocation against policy rules and confirmation boundaries."""
        risk = self.rules.classify(tool_name, arguments, default_risk=default_risk)

        # 1. RESTRICTED: Strictly forbidden
        if risk == RiskClass.RESTRICTED:
            logger.warning("Policy DENIED tool '%s': targets restricted system operation.", tool_name)
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                risk_class=risk,
                reason=f"Tool '{tool_name}' targets a protected system path or forbidden operation.",
            )

        # 2. READ & LOW: Safe to execute autonomously
        if risk in (RiskClass.READ, RiskClass.LOW):
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                risk_class=risk,
                reason=f"Operation auto-allowed under {risk.value} risk class.",
            )

        # 3. HIGH: Material state changes requiring confirmation
        if risk == RiskClass.HIGH:
            if self.confirmation_contract is not None:
                req = ConfirmationRequest(
                    task_id=task_id or "task-unknown",
                    tool_name=tool_name,
                    arguments=arguments,
                    risk_class=risk,
                    reason=f"High-risk operation: '{tool_name}' creates material state changes.",
                    prompt_message=f"Allow PLUMA to execute '{tool_name}'?",
                )
                logger.info("Requesting user confirmation for high-risk tool '%s'...", tool_name)
                response = self.confirmation_contract.request_confirmation(req)
                if response.approved:
                    logger.info("User APPROVED execution of tool '%s'.", tool_name)
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.ALLOW,
                        risk_class=risk,
                        reason="User approved high-risk operation.",
                    )
                else:
                    logger.warning("User DENIED execution of tool '%s'.", tool_name)
                    return PolicyEvaluationResult(
                        decision=PolicyDecision.DENY,
                        risk_class=risk,
                        reason=f"User denied high-risk operation: {response.reason or 'User cancelled'}.",
                    )

            # If no confirmation contract attached, flag as requiring confirmation
            return PolicyEvaluationResult(
                decision=PolicyDecision.REQUIRE_CONFIRMATION,
                risk_class=risk,
                reason=f"Tool '{tool_name}' is high-risk and requires user confirmation.",
                requires_confirmation=True,
            )

        # Fallback to allow if unspecified
        return PolicyEvaluationResult(
            decision=PolicyDecision.ALLOW,
            risk_class=risk,
            reason="Allowed by default policy.",
        )
