"""pluma.perception.uia_snapshot — UIA snapshot builder.

Spec §8.1, §8.2: UI Automation is the primary perception method.
Extracts semantic ScreenElement controls with window-relative bounding boxes
and creates an immutable ScreenSnapshot with TTL.
Boundary: Zero pywinauto imported at module level.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from pluma.adapters.base import WindowNotFoundError
from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo
from pluma.perception.element_refs import (
    BoundingBox,
    ElementSource,
    ScreenElement,
    ScreenSnapshot,
)

logger = logging.getLogger(__name__)


def _map_invocation_capability(control_type: Optional[str]) -> Optional[str]:
    """Determine standard invocation capability from UIA control type."""
    if not control_type:
        return "click"
    
    ctype = control_type.lower()
    if any(k in ctype for k in ("button", "menuitem", "hyperlink", "tabitem", "listitem")):
        return "invoke"
    elif any(k in ctype for k in ("edit", "document", "text")):
        return "set_value"
    elif any(k in ctype for k in ("checkbox", "radiobutton", "switch")):
        return "toggle"
    elif any(k in ctype for k in ("combobox", "treeitem", "expander")):
        return "expand_collapse"
    return "click"


class UiaSnapshotBuilder:
    """Builds ScreenSnapshot instances from active window UI Automation control trees."""

    def __init__(
        self,
        context: Optional[ActiveWindowContext] = None,
        custom_extractor: Optional[Callable[[int], List[Dict[str, Any]]]] = None,
    ) -> None:
        self._context = context or ActiveWindowContext()
        self._custom_extractor = custom_extractor

    def _extract_controls_via_pywinauto(self, hwnd: int, win_rect: BoundingBox) -> List[ScreenElement]:
        """Traverse UIA tree using pywinauto and extract semantic ScreenElement items."""
        elements: List[ScreenElement] = []
        try:
            import pywinauto  # type: ignore[import-not-found]
            app = pywinauto.Application(backend="uia").connect(handle=hwnd)
            win = app.window(handle=hwnd)

            # Discover children
            descendants = win.descendants()
            for w in descendants:
                try:
                    if not w.is_visible():
                        continue

                    rect_obj = w.rectangle()
                    # Skip empty rectangles
                    if rect_obj.width() <= 0 or rect_obj.height() <= 0:
                        continue

                    # Calculate window-relative coordinates
                    rel_left = rect_obj.left - win_rect.left
                    rel_top = rect_obj.top - win_rect.top
                    rel_right = rect_obj.right - win_rect.left
                    rel_bottom = rect_obj.bottom - win_rect.top

                    name = getattr(w.element_info, "name", "") or ""
                    auto_id = getattr(w.element_info, "automation_id", "") or ""
                    control_type = getattr(w.element_info, "control_type", "") or ""
                    class_name = getattr(w.element_info, "class_name", "") or ""
                    is_enabled = bool(w.is_enabled())

                    label = name or auto_id or control_type or ""
                    inv_cap = _map_invocation_capability(control_type)

                    elem = ScreenElement(
                        snapshot_id="",  # Will be populated by capture()
                        source=ElementSource.UIA,
                        label=label,
                        control_type=control_type,
                        bounds=BoundingBox(
                            left=rel_left,
                            top=rel_top,
                            right=rel_right,
                            bottom=rel_bottom,
                        ),
                        confidence=1.0,
                        invocation_capability=inv_cap,
                        uia_automation_id=auto_id or None,
                        metadata={
                            "class_name": class_name,
                            "is_enabled": is_enabled,
                            "handle": getattr(w.element_info, "handle", None),
                        },
                    )
                    elements.append(elem)
                except Exception as child_exc:
                    logger.debug("Failed extracting child control in window %d: %s", hwnd, child_exc)
        except ImportError:
            logger.warning("pywinauto is not installed; returning empty UIA control tree.")
        except Exception as exc:
            logger.debug("UIA tree extraction failed for window %d: %s", hwnd, exc)
        return elements

    def capture(
        self,
        hwnd: Optional[int] = None,
        ttl_seconds: float = 3.0,
        include_ocr: bool = False,
        ocr_if_no_controls: bool = False,
        ocr_manager: Optional[Any] = None,
        window_capture: Optional[Any] = None,
    ) -> ScreenSnapshot:
        """Capture a point-in-time ScreenSnapshot for the specified or active window."""
        active_info: Optional[ActiveWindowInfo] = None
        if hwnd is None:
            active_info = self._context.get_active_window()
            if not active_info.is_valid or not active_info.hwnd:
                raise WindowNotFoundError("No active foreground window found for snapshot capture.")
            hwnd = active_info.hwnd
            win_rect = active_info.rect
            process_name = active_info.process_name
            window_title = active_info.window_title
            dpi_scale = active_info.dpi_scale
        else:
            w_info = self._context.get_window_info(hwnd)
            win_rect = w_info.rect if w_info.is_valid else BoundingBox(left=0, top=0, right=1920, bottom=1080)
            process_name = w_info.process_name if w_info.is_valid else self._context.get_process_name(hwnd)
            window_title = w_info.window_title if w_info.is_valid else f"HWND:{hwnd}"
            dpi_scale = w_info.dpi_scale if w_info.is_valid else self._context.get_dpi_scale(hwnd)

        snapshot_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=max(0.1, ttl_seconds))

        # Extract controls
        raw_elements: List[ScreenElement] = []
        if self._custom_extractor:
            custom_items = self._custom_extractor(hwnd)
            for item in custom_items:
                bounds_dict = item.get("bounds", {"left": 0, "top": 0, "right": 100, "bottom": 30})
                elem = ScreenElement(
                    snapshot_id=snapshot_id,
                    source=ElementSource.UIA,
                    label=item.get("label", ""),
                    control_type=item.get("control_type", "Button"),
                    bounds=BoundingBox(**bounds_dict),
                    confidence=float(item.get("confidence", 1.0)),
                    invocation_capability=item.get("invocation_capability", "invoke"),
                    uia_automation_id=item.get("uia_automation_id"),
                    metadata=item.get("metadata", {}),
                )
                raw_elements.append(elem)
        else:
            unassigned_elements = self._extract_controls_via_pywinauto(hwnd, win_rect)
            for el in unassigned_elements:
                # Re-bind with correct snapshot_id
                elem = ScreenElement(
                    element_id=el.element_id,
                    snapshot_id=snapshot_id,
                    source=el.source,
                    label=el.label,
                    control_type=el.control_type,
                    bounds=el.bounds,
                    confidence=el.confidence,
                    invocation_capability=el.invocation_capability,
                    uia_automation_id=el.uia_automation_id,
                    metadata=el.metadata,
                )
                raw_elements.append(elem)

        # Optional OCR fallback pass
        ocr_elements: List[ScreenElement] = []
        should_run_ocr = include_ocr or (ocr_if_no_controls and len(raw_elements) == 0)
        if should_run_ocr:
            try:
                from pluma.perception.capture import WindowCapture
                from pluma.perception.ocr_lifecycle import OcrLifecycleManager
                
                cap = window_capture or WindowCapture()
                omgr = ocr_manager or OcrLifecycleManager()
                
                img_bytes = cap.capture_window(hwnd)
                ocr_res = omgr.run_ocr(img_bytes)
                for word in ocr_res.words:
                    ocr_el = ScreenElement(
                        snapshot_id=snapshot_id,
                        source=ElementSource.OCR,
                        label=word.text,
                        control_type="StaticText",
                        bounds=word.bounds,
                        confidence=word.confidence,
                        invocation_capability="click",
                    )
                    ocr_elements.append(ocr_el)
            except Exception as ocr_exc:
                logger.debug("OCR fallback pass failed for window %d: %s", hwnd, ocr_exc)

        pid = None
        window_class = None
        creation_time_ns = None
        if active_info is not None:
            pid = active_info.pid or None
            window_class = active_info.class_name or None
            if pid:
                creation_time_ns = self._context.get_process_creation_time_ns(pid)
        elif hwnd is not None:
            w_info = self._context.get_window_info(hwnd)
            pid = w_info.pid if w_info.is_valid else None
            window_class = w_info.class_name if w_info.is_valid else None
            if pid:
                creation_time_ns = self._context.get_process_creation_time_ns(pid)

        return ScreenSnapshot(
            snapshot_id=snapshot_id,
            created_at=now,
            expires_at=expires_at,
            active_process=process_name,
            active_window_title=window_title,
            window_rect=win_rect,
            dpi_scale=dpi_scale,
            hwnd=hwnd,
            pid=pid,
            process_creation_time_ns=creation_time_ns,
            window_class=window_class,
            controls=raw_elements,
            ocr_words=ocr_elements,
            image_ref=None,
        )



# Alias for backward compatibility
UiaSnapshot = UiaSnapshotBuilder
