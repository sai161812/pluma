"""pluma.ui.settings_contract — Settings UI contract (stub).

Spec §19: Settings view is a functional contract; visual design is not defined here.
Implemented in Phase 14.
"""

import abc


class SettingsContract(abc.ABC):
    """Stub: Abstract settings view contract. Implemented in Phase 14."""

    @abc.abstractmethod
    def show_settings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("SettingsContract not implemented until Phase 14.")
