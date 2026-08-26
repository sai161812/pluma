"""pluma.adapters.uia — UI Automation (UIA) adapter.

Spec §13, §14, §17: Wraps Windows UI Automation (via pywinauto) behind a
clean interface. Lazily imports pywinauto inside methods to ensure the
resident core stays lightweight at startup.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from pluma.adapters.base import (
    AdapterError,
    AdapterTimeoutError,
    ControlInfo,
    ElementNotFoundError,
    ElementUnavailableError,
    Rect,
    WindowNotFoundError,
)
from pluma.adapters.win32 import Win32Adapter

logger = logging.getLogger(__name__)


def _get_pywinauto() -> Any:
    """Lazily import and return the pywinauto module."""
    try:
        import pywinauto  # type: ignore[import-not-found]
        return pywinauto
    except ImportError as exc:
        raise AdapterError(f"pywinauto is not installed: {exc}")


class UiaAdapter:
    """Adapter for inspecting and interacting with UI elements via UI Automation."""

    def __init__(self) -> None:
        self._win32 = Win32Adapter()

    def _get_app_window(self, hwnd: int) -> Any:
        """Connect to window handle via pywinauto uia backend."""
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")
        pwa = _get_pywinauto()
        try:
            app = pwa.Application(backend="uia").connect(handle=hwnd)
            return app.window(handle=hwnd)
        except Exception as exc:
            logger.debug("Failed to connect to window HWND %d via UIA: %s", hwnd, exc)
            raise WindowNotFoundError(f"Window HWND {hwnd} not accessible via UIA: {exc}")

    def find_control(
        self,
        hwnd: int,
        *,
        auto_id: Optional[str] = None,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        timeout_s: float = 3.0,
    ) -> ControlInfo:
        """Find a single control element within a window tree.

        Raises:
            ElementNotFoundError: If no matching control is found.
            AdapterTimeoutError: If search exceeds timeout_s.
            WindowNotFoundError: If hwnd is invalid.
        """
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")

        win = self._get_app_window(hwnd)
        kwargs: Dict[str, Any] = {}
        if auto_id:
            kwargs["auto_id"] = auto_id
        if name:
            kwargs["title"] = name
        if control_type:
            kwargs["control_type"] = control_type

        t0 = time.perf_counter()
        try:
            elem = win.child_window(**kwargs)
            if not elem.exists(timeout=timeout_s):
                raise ElementNotFoundError(
                    f"Control not found: auto_id={auto_id}, name={name}, type={control_type}"
                )

            wrapper = elem.wrapper_object()
            rect_obj = wrapper.rectangle()
            rect = Rect(
                left=rect_obj.left,
                top=rect_obj.top,
                right=rect_obj.right,
                bottom=rect_obj.bottom,
            )

            return ControlInfo(
                automation_id=getattr(wrapper.element_info, "automation_id", "") or "",
                name=getattr(wrapper.element_info, "name", "") or "",
                control_type=getattr(wrapper.element_info, "control_type", "") or "",
                class_name=getattr(wrapper.element_info, "class_name", "") or "",
                is_enabled=bool(wrapper.is_enabled()),
                is_visible=bool(wrapper.is_visible()),
                rect=rect,
                handle=getattr(wrapper.element_info, "handle", None),
            )

        except ElementNotFoundError:
            raise
        except Exception as exc:
            if time.perf_counter() - t0 >= timeout_s:
                raise AdapterTimeoutError(f"UIA search timed out after {timeout_s}s: {exc}")
            raise ElementNotFoundError(f"UIA element lookup failed: {exc}")

    def invoke_control(
        self,
        hwnd: int,
        *,
        auto_id: Optional[str] = None,
        name: Optional[str] = None,
        control_type: Optional[str] = None,
        timeout_s: float = 3.0,
    ) -> bool:
        """Invoke/click a control element within a window tree."""
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")

        win = self._get_app_window(hwnd)
        kwargs: Dict[str, Any] = {}
        if auto_id:
            kwargs["auto_id"] = auto_id
        if name:
            kwargs["title"] = name
        if control_type:
            kwargs["control_type"] = control_type

        try:
            elem = win.child_window(**kwargs)
            if not elem.exists(timeout=timeout_s):
                raise ElementNotFoundError(
                    f"Control not found for invoke: auto_id={auto_id}, name={name}"
                )

            wrapper = elem.wrapper_object()
            if not wrapper.is_enabled():
                raise ElementUnavailableError(f"Control is disabled: {name or auto_id}")

            # Try invoke pattern first, fallback to click
            if hasattr(wrapper, "invoke"):
                wrapper.invoke()
            else:
                wrapper.click_input()
            return True

        except (ElementNotFoundError, ElementUnavailableError):
            raise
        except Exception as exc:
            raise AdapterError(f"Failed to invoke control: {exc}")

    def set_control_text(
        self,
        hwnd: int,
        text: str,
        auto_id: Optional[str] = None,
        name: Optional[str] = None,
        timeout_s: float = 3.0,
        clear_existing: bool = True,
    ) -> bool:
        """Set the text value of an editable control element."""
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")

        win = self._get_app_window(hwnd)
        kwargs: Dict[str, Any] = {}
        if auto_id:
            kwargs["auto_id"] = auto_id
        if name:
            kwargs["title"] = name

        try:
            elem = win.child_window(**kwargs)
            if not elem.exists(timeout=timeout_s):
                raise ElementNotFoundError(f"Edit control not found: {name or auto_id}")

            wrapper = elem.wrapper_object()
            if not wrapper.is_enabled():
                raise ElementUnavailableError(f"Edit control is disabled: {name or auto_id}")

            if hasattr(wrapper, "set_edit_text"):
                wrapper.set_edit_text(text)
            elif hasattr(wrapper, "set_text"):
                wrapper.set_text(text)
            else:
                prefix = "^a{BACKSPACE}" if clear_existing else ""
                wrapper.type_keys(prefix + text, with_spaces=True)
            return True

        except (ElementNotFoundError, ElementUnavailableError):
            raise
        except Exception as exc:
            raise AdapterError(f"Failed to set control text: {exc}")

    def get_control_tree(self, hwnd: int, max_depth: int = 2) -> List[ControlInfo]:
        """Inspect and return a list of top-level child controls."""
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")

        win = self._get_app_window(hwnd)
        controls: List[ControlInfo] = []

        try:
            children = win.children()
            for child in children[:50]:  # Limit to 50 items to avoid stalling
                try:
                    rect_obj = child.rectangle()
                    rect = Rect(
                        left=rect_obj.left,
                        top=rect_obj.top,
                        right=rect_obj.right,
                        bottom=rect_obj.bottom,
                    )
                    info = ControlInfo(
                        automation_id=getattr(child.element_info, "automation_id", "") or "",
                        name=getattr(child.element_info, "name", "") or "",
                        control_type=getattr(child.element_info, "control_type", "") or "",
                        class_name=getattr(child.element_info, "class_name", "") or "",
                        is_enabled=bool(child.is_enabled()),
                        is_visible=bool(child.is_visible()),
                        rect=rect,
                        handle=getattr(child.element_info, "handle", None),
                    )
                    controls.append(info)
                except Exception:
                    continue
            return controls
        except Exception as exc:
            logger.debug("Failed to get control tree for HWND %d: %s", hwnd, exc)
            return []
