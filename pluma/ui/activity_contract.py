"""pluma.ui.activity_contract — Activity view UI contract (stub).

Spec §19: Activity view is a functional contract; visual design is not defined here.
Implemented in Phase 5.
"""

import abc


class ActivityViewContract(abc.ABC):
    """Stub: Abstract activity view contract. Implemented in Phase 5."""

    @abc.abstractmethod
    def show_activity(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("ActivityViewContract not implemented until Phase 5.")
