"""pluma.ui.confirmations — User confirmation UI contract (stub).

Spec §19: Confirmation dialogs are functional contracts; visual design is not defined here.
Implemented in Phase 11.
"""

import abc


class ConfirmationContract(abc.ABC):
    """Stub: Abstract confirmation dialog contract. Implemented in Phase 11."""

    @abc.abstractmethod
    def request_confirmation(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("ConfirmationContract not implemented until Phase 11.")
