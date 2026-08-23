"""pluma.adapters — Windows automation adapters.

Spec §13: Win32, PowerShell, UIA, Input, and Screen adapters.
"""

from pluma.adapters.base import (
    AccessDeniedError,
    AdapterError,
    AdapterTimeoutError,
    ControlInfo,
    ElementNotFoundError,
    ElementUnavailableError,
    InputOutOfBoundsError,
    Rect,
    WindowInfo,
    WindowNotFoundError,
    WindowState,
)
from pluma.adapters.input import InputAdapter
from pluma.adapters.powershell import PowerShellAdapter
from pluma.adapters.screen import ScreenAdapter
from pluma.adapters.uia import UiaAdapter
from pluma.adapters.win32 import Win32Adapter

__all__ = [
    "AccessDeniedError",
    "AdapterError",
    "AdapterTimeoutError",
    "ControlInfo",
    "ElementNotFoundError",
    "ElementUnavailableError",
    "InputAdapter",
    "InputOutOfBoundsError",
    "PowerShellAdapter",
    "Rect",
    "ScreenAdapter",
    "UiaAdapter",
    "Win32Adapter",
    "WindowInfo",
    "WindowNotFoundError",
    "WindowState",
]
