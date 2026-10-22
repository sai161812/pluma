"""Explicit confirmation for named inert/owned test operations only."""
from pluma.policy.engine import PolicyEngine
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse


def owned_fixture_policy(*tool_names):
    allowed = frozenset(tool_names)

    def confirm(request):
        return ConfirmationResponse(approved=request.tool_name in allowed,
                                    reason='Explicit owned test fixture approval.')

    return PolicyEngine(confirmation_contract=CallbackConfirmationContract(confirm))
