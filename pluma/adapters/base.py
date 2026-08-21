"""pluma.adapters.base — Base interfaces and typed errors for automation adapters.

Spec §13, §14: Adapters wrap OS, shell, UIA, input, and screen capture behind
clean interfaces with bounded timeouts, privilege-aware error mapping, and zero
module-level heavy/ML dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Error hierarchy (Spec §14, §24)
# ---------------------------------------------------------------------------

class AdapterError(Exception):
    """Base error for all adapter operations. Must contain a factual message."""

    def __init__(self, message: str, error_code: str = "ADAPTER_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class AccessDeniedError(AdapterError):
    """Raised when an operation is denied due to insufficient OS privileges / UAC."""

    def __init__(self, message: str = "Access denied: insufficient privileges") -> None:
        super().__init__(message, error_code="ACCESS_DENIED")


class ElementNotFoundError(AdapterError):
    """Raised when a requested UIA control cannot be found in the visual tree."""

    def __init__(self, message: str = "Target control not found") -> None:
        super().__init__(message, error_code="ELEMENT_NOT_FOUND")


class ElementUnavailableError(AdapterError):
    """Raised when a control exists but cannot be interacted with (disabled/hidden)."""

    def __init__(self, message: str = "Target control is disabled or offscreen") -> None:
        super().__init__(message, error_code="ELEMENT_UNAVAILABLE")


class AdapterTimeoutError(AdapterError):
    """Raised when an adapter operation exceeds its bounded execution timeout."""

    def __init__(self, message: str = "Adapter operation timed out") -> None:
        super().__init__(message, error_code="TIMEOUT")


class WindowNotFoundError(AdapterError):
    """Raised when a window handle or title does not match any open window."""

    def __init__(self, message: str = "Window not found") -> None:
        super().__init__(message, error_code="WINDOW_NOT_FOUND")


class InputOutOfBoundsError(AdapterError):
    """Raised when coordinates fall outside the target window or screen geometry."""

    def __init__(self, message: str = "Input coordinates outside target boundaries") -> None:
        super().__init__(message, error_code="OUT_OF_BOUNDS")


# ---------------------------------------------------------------------------
# Common Data Models
# ---------------------------------------------------------------------------

class WindowState(str, Enum):
    """Window display state."""
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    HIDDEN = "hidden"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Rect:
    """Bounding rectangle for windows and UI elements."""
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom


@dataclass(frozen=True)
class WindowInfo:
    """Metadata describing a top-level or child window."""
    hwnd: int
    title: str
    class_name: str
    pid: int
    is_visible: bool
    is_enabled: bool
    rect: Rect
    state: WindowState


@dataclass(frozen=True)
class ControlInfo:
    """Metadata describing a UI Automation control element."""
    automation_id: str
    name: str
    control_type: str
    class_name: str
    is_enabled: bool
    is_visible: bool
    rect: Optional[Rect] = None
    handle: Optional[int] = None
