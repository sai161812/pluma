"""Settings view boundary for alternate Python hosts.

Spec §19: Settings view is a functional contract; visual design is not defined here.
The production WinUI host implements navigation in MainWindow.NavigateSettings,
with SettingsPage/SettingsController and the authenticated typed settings API.
This abstract interface does not itself display a native view.
"""

import abc


class SettingsContract(abc.ABC):
    """Alternate hosts must supply their own view implementation."""

    @abc.abstractmethod
    def show_settings(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise NotImplementedError("The selected host must implement settings navigation.")
