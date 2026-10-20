"""pluma.policy.engine — Deterministic policy evaluation engine.

Spec §14, §15:
- Evaluates every ToolCall before execution against risk rules.
- Autonomously allows READ and LOW risk operations.
- Intercepts HIGH risk operations and requires explicit user confirmation.
- Strictly blocks RESTRICTED operations.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
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

        # 2. READ and LOW do not require material-operation approval.
        if risk in (RiskClass.READ, RiskClass.LOW):
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

        # Without a trusted exact-call intent proof, MEDIUM requires explicit
        # approval too. Natural language and planner arguments cannot grant it.
        if risk in (RiskClass.MEDIUM, RiskClass.HIGH):
            if self.confirmation_contract is None:
                return PolicyEvaluationResult(PolicyDecision.REQUIRE_CONFIRMATION, risk,
                    "Explicit approval is required for this operation.", requires_confirmation=True)
            if not isinstance(task_id, str) or not task_id.strip():
                return PolicyEvaluationResult(PolicyDecision.DENY, risk,
                    "Operation denied because no task identity was supplied.")
            try:
                args = deepcopy(arguments)
                encoded = json.dumps(args, sort_keys=True, ensure_ascii=False, allow_nan=False)
                request = ConfirmationRequest(task_id=task_id, tool_name=tool_name,
                    arguments=args, risk_class=risk,
                    reason="Explicit approval of this exact operation is required.",
                    prompt_message=f"Allow {tool_name.replace('_', ' ')} with these arguments?")
                response = self.confirmation_contract.request_confirmation(request)
                intact = (request.task_id == task_id and request.tool_name == tool_name
                    and request.risk_class == risk and json.dumps(request.arguments,
                        sort_keys=True, ensure_ascii=False, allow_nan=False) == encoded)
                if intact and isinstance(response, ConfirmationResponse) and response.approved is True:
                    return PolicyEvaluationResult(PolicyDecision.ALLOW, risk,
                        "User approved this exact operation.")
            except Exception:
                return PolicyEvaluationResult(PolicyDecision.DENY, risk,
                    "Operation denied because approval could not be verified.")
            return PolicyEvaluationResult(PolicyDecision.DENY, risk, "User denied the operation or approval was invalid.")

        # Fail-closed for any unclassified or unknown risk
        logger.error("Policy fail-closed for unclassified risk '%s' on tool '%s'.", risk, tool_name)
        return PolicyEvaluationResult(
            decision=PolicyDecision.DENY,
            risk_class=risk if isinstance(risk, RiskClass) else RiskClass.DENY,
            reason=f"Operation denied under fail-closed security policy (risk={risk}).",
        )
