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
    REQUIRE_ELEVATION = "REQUIRE_ELEVATION"
    DENY = "DENY"


@dataclass(frozen=True)
class PolicyEvaluationResult:
    """Detailed outcome of policy engine evaluation."""
    decision: PolicyDecision
    risk_class: RiskClass
    reason: str
    requires_confirmation: bool = False
    requires_elevation: bool = False

    @property
    def is_allowed(self) -> bool:
        """True if operation is permitted to execute without further confirmation."""
        return self.decision == PolicyDecision.ALLOW

    @property
    def allowed(self) -> bool:
        """Alias for is_allowed."""
        return self.is_allowed


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

        # 1. RESTRICTED & DENY: Strictly forbidden
        if risk in (RiskClass.RESTRICTED, RiskClass.DENY):
            logger.warning("Policy DENIED tool '%s': forbidden under %s risk tier.", tool_name, risk.value)
            return PolicyEvaluationResult(
                decision=PolicyDecision.DENY,
                risk_class=risk,
                reason=f"Tool '{tool_name}' is forbidden under {risk.value} risk policy.",
            )

        # 2. READ, LOW, MEDIUM: Safe to execute autonomously (MEDIUM captures undo)
        if risk in (RiskClass.READ, RiskClass.LOW, RiskClass.MEDIUM):
            return PolicyEvaluationResult(
                decision=PolicyDecision.ALLOW,
                risk_class=risk,
                reason=f"Operation allowed under {risk.value} risk tier.",
            )

        # 3. ADMIN: Requires single-operation elevation broker
        if risk == RiskClass.ADMIN:
            logger.info("Policy intercepted ADMIN tool '%s': requires elevation broker.", tool_name)
            return PolicyEvaluationResult(
                decision=PolicyDecision.REQUIRE_ELEVATION,
                risk_class=risk,
                reason=f"Tool '{tool_name}' requires single-operation elevation broker.",
                requires_elevation=True,
            )

        # 4. HIGH: Material state changes requiring confirmation
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

        # Fail-closed for any unclassified or unknown risk
        logger.error("Policy fail-closed for unclassified risk '%s' on tool '%s'.", risk, tool_name)
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            risk_class=risk if isinstance(risk, RiskClass) else RiskClass.DENY,
            reason=f"Operation denied under fail-closed security policy (risk={risk}).",
        )
