"""pluma.tools.ui — UI interaction tools via Windows UI Automation.

Spec §12, §14, §15: UI interactions are registered ToolSpecs.
pywinauto and UiaAdapter are imported lazily inside executors to protect the
resident core startup footprint.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from pluma.adapters.base import ControlInfo, ElementNotFoundError, ElementUnavailableError, WindowNotFoundError
from pluma.adapters.uia import UiaAdapter
from pluma.perception.context import ActiveWindowContext
from pluma.perception.uia_snapshot import UiaSnapshotBuilder
from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import verify_noop
from pluma.verify.screen import ScreenVerifier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class InspectActiveWindowArgs(BaseModel):
    """Arguments for inspect_active_window."""
    model_config = {"extra": "forbid"}
    include_controls: bool = Field(default=True, description="Whether to include semantic controls.")
    max_controls: int = Field(default=50, description="Maximum number of controls to return.")


class ClickElementArgs(BaseModel):
    """Arguments for click_element."""
    model_config = {"extra": "forbid"}
    name: Optional[str] = Field(default=None, description="Name or title text of the target UI element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of the target element.")
    control_type: Optional[str] = Field(default=None, description="UIA control type (e.g. 'Button', 'MenuItem').")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND. If omitted, uses active window.")
    snapshot_id: Optional[str] = Field(default=None, description="Snapshot ID this click is grounded in.")
    target_ref: Optional[str] = Field(default=None, description="Semantic reference string from UI snapshot.")

    @model_validator(mode="after")
    def _require_identifier(self) -> "ClickElementArgs":
        if not self.name and not self.auto_id and not self.control_type and not self.target_ref:
            raise ValueError("At least one of 'name', 'auto_id', 'control_type', or 'target_ref' must be specified.")
        return self


class TypeIntoElementArgs(BaseModel):
    """Arguments for type_into_element."""
    model_config = {"extra": "forbid"}
    text: str = Field(description="Text to type or set into the target element.")
    name: Optional[str] = Field(default=None, description="Name or label of the target editable element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of the editable element.")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND. If omitted, uses active window.")
    clear_existing: bool = Field(default=True, description="Clear existing text before typing.")
    snapshot_id: Optional[str] = Field(default=None, description="Snapshot ID this typing action is grounded in.")
    target_ref: Optional[str] = Field(default=None, description="Semantic reference string from UI snapshot.")


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_inspect_active_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Inspect the active foreground window and return its semantic controls."""
    context = ActiveWindowContext()
    active_info = context.get_active_window()

    if not active_info.is_valid or not active_info.hwnd:
        return ToolResult(
            ok=False,
            tool="inspect_active_window",
            data={},
            factual_message="No active foreground window found to inspect.",
            verified=False,
            error="No active window found.",
        )

    builder = UiaSnapshotBuilder(context=context)
    try:
        snapshot = builder.capture(hwnd=active_info.hwnd, ttl_seconds=5.0)
        controls_summary = [
            {
                "label": c.label,
                "control_type": c.control_type,
                "auto_id": c.uia_automation_id,
                "bounds": c.bounds.model_dump(),
                "capability": c.invocation_capability,
            }
            for c in snapshot.controls[: args.get("max_controls", 50)]
        ]

        return ToolResult(
            ok=True,
            tool="inspect_active_window",
            data={
                "hwnd": active_info.hwnd,
                "process_name": active_info.process_name,
                "window_title": active_info.window_title,
                "control_count": len(snapshot.controls),
                "controls": controls_summary,
            },
            factual_message=(
                f"Active window: '{active_info.window_title}' ({active_info.process_name}, "
                f"HWND {active_info.hwnd}), {len(snapshot.controls)} controls discovered."
            ),
            verified=True,
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            tool="inspect_active_window",
            data={"hwnd": active_info.hwnd},
            factual_message=f"Failed to inspect active window: {exc}",
            verified=False,
            error=str(exc),
        )


def execute_click_element(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Invoke or click a target UI element using UI Automation."""
    if task_context and hasattr(task_context, "cancellation_token") and task_context.cancellation_token.is_cancelled:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message="Task cancelled before click could execute.",
            verified=False, error="TASK_CANCELLED",
        )

    name = args.get("name")
    auto_id = args.get("auto_id")
    control_type = args.get("control_type")
    hwnd = args.get("hwnd")
    snapshot_id = args.get("snapshot_id")

    # --- Snapshot grounding FIRST (before any window/hardware access) ---
    # Reject invented, expired, or unverifiable snapshot references immediately.
    if snapshot_id:
        snapshot_registry = getattr(task_context, "snapshot_registry", None)
        if snapshot_registry is not None:
            from pluma.perception.snapshot_registry import SnapshotNotFoundError
            from pluma.perception.element_refs import StaleSnapshotError
            try:
                snapshot_registry.resolve(snapshot_id)
            except SnapshotNotFoundError as e:
                return ToolResult(
                    ok=False, tool="click_element", data=args,
                    factual_message=f"Snapshot grounding failed: {e}",
                    verified=False, error=str(e),
                )
            except StaleSnapshotError as e:
                return ToolResult(
                    ok=False, tool="click_element", data=args,
                    factual_message=f"Snapshot grounding failed: {e}",
                    verified=False, error=str(e),
                )
        else:
            # No registry on task_context — cannot verify provenance of snapshot_id
            return ToolResult(
                ok=False, tool="click_element", data=args,
                factual_message=(
                    f"Snapshot grounding rejected: no snapshot registry on task_context. "
                    f"snapshot_id={snapshot_id!r} cannot be verified."
                ),
                verified=False, error="NO_SNAPSHOT_REGISTRY",
            )

    context = ActiveWindowContext()
    if hwnd is None:
        active = context.get_active_window()
        if not active.is_valid or not active.hwnd:
            return ToolResult(
                ok=False,
                tool="click_element",
                data=args,
                factual_message="Cannot click element: no active foreground window found.",
                verified=False,
                error="No active window.",
            )
        hwnd = active.hwnd
    else:
        # Verify foreground active window focus matches target hwnd
        active = context.get_active_window()
        if active.is_valid and active.hwnd and active.hwnd != hwnd:
            logger.debug("Active window HWND %d differs from target HWND %d", active.hwnd, hwnd)


    adapter = UiaAdapter()
    verifier = ScreenVerifier(uia_adapter=adapter)

    try:
        adapter.invoke_control(
            hwnd=hwnd,
            auto_id=auto_id,
            name=name,
            control_type=control_type,
            timeout_s=3.0,
        )

        v_res = verifier.verify_control_invoked(hwnd=hwnd, auto_id=auto_id, name=name)
        target_label = name or auto_id or control_type or "unknown"

        return ToolResult(
            ok=True,
            tool="click_element",
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "control_type": control_type, "snapshot_id": snapshot_id},
            factual_message=f"Clicked UI element '{target_label}' in window HWND {hwnd}.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except (ElementNotFoundError, ElementUnavailableError, WindowNotFoundError) as known_exc:
        return ToolResult(
            ok=False,
            tool="click_element",
            data=args,
            factual_message=f"Failed to click element: {known_exc}",
            verified=False,
            error=str(known_exc),
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            tool="click_element",
            data=args,
            factual_message=f"Error clicking UI element: {exc}",
            verified=False,
            error=str(exc),
        )


def execute_type_into_element(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Set or type text into a target editable UI element."""
    if task_context and hasattr(task_context, "cancellation_token") and task_context.cancellation_token.is_cancelled:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="Task cancelled before typing could execute.",
            verified=False, error="TASK_CANCELLED",
        )

    text = args["text"]
    name = args.get("name")
    auto_id = args.get("auto_id")
    hwnd = args.get("hwnd")
    clear_existing = args.get("clear_existing", True)
    snapshot_id = args.get("snapshot_id")

    # --- Snapshot grounding FIRST (before any window/hardware access) ---
    if snapshot_id:
        snapshot_registry = getattr(task_context, "snapshot_registry", None)
        if snapshot_registry is not None:
            from pluma.perception.snapshot_registry import SnapshotNotFoundError
            from pluma.perception.element_refs import StaleSnapshotError
            try:
                snapshot_registry.resolve(snapshot_id)
            except SnapshotNotFoundError as e:
                return ToolResult(
                    ok=False, tool="type_into_element", data=args,
                    factual_message=f"Snapshot grounding failed: {e}",
                    verified=False, error=str(e),
                )
            except StaleSnapshotError as e:
                return ToolResult(
                    ok=False, tool="type_into_element", data=args,
                    factual_message=f"Snapshot grounding failed: {e}",
                    verified=False, error=str(e),
                )
        else:
            return ToolResult(
                ok=False, tool="type_into_element", data=args,
                factual_message=(
                    f"Snapshot grounding rejected: no snapshot registry on task_context. "
                    f"snapshot_id={snapshot_id!r} cannot be verified."
                ),
                verified=False, error="NO_SNAPSHOT_REGISTRY",
            )

    context = ActiveWindowContext()
    if hwnd is None:
        active = context.get_active_window()
        if not active.is_valid or not active.hwnd:
            return ToolResult(
                ok=False,
                tool="type_into_element",
                data={"name": name, "auto_id": auto_id},
                factual_message="Cannot type: no active foreground window found.",
                verified=False,
                error="No active window.",
            )
        hwnd = active.hwnd
    else:
        active = context.get_active_window()

    adapter = UiaAdapter()
    verifier = ScreenVerifier(uia_adapter=adapter)

    try:
        adapter.set_control_text(
            hwnd=hwnd,
            text=text,
            auto_id=auto_id,
            name=name,
            timeout_s=3.0,
            clear_existing=clear_existing,
        )

        v_res = verifier.verify_control_text(
            hwnd=hwnd,
            expected_text=text,
            auto_id=auto_id,
            name=name,
        )
        target_label = name or auto_id or "editable element"

        return ToolResult(
            ok=True,
            tool="type_into_element",
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "text_length": len(text), "snapshot_id": snapshot_id},
            factual_message=f"Typed text into '{target_label}' in window HWND {hwnd}.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except (ElementNotFoundError, ElementUnavailableError, WindowNotFoundError) as known_exc:
        return ToolResult(
            ok=False,
            tool="type_into_element",
            data={"name": name, "auto_id": auto_id},
            factual_message=f"Failed to type into element: {known_exc}",
            verified=False,
            error=str(known_exc),
        )
    except Exception as exc:
        return ToolResult(
            ok=False,
            tool="type_into_element",
            data={"name": name, "auto_id": auto_id},
            factual_message=f"Error typing into UI element: {exc}",
            verified=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# ToolSpecs
# ---------------------------------------------------------------------------

INSPECT_ACTIVE_WINDOW_SPEC = ToolSpec(
    name="inspect_active_window",
    description="Inspect the foreground active window and return discovered semantic controls.",
    args_schema=InspectActiveWindowArgs,
    risk_class=RiskClass.READ,
    timeout_s=5.0,
    executor=execute_inspect_active_window,
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.UIA, AdapterPriority.NATIVE_API],
    cancellable=True,
)

CLICK_ELEMENT_SPEC = ToolSpec(
    name="click_element",
    description="Click or invoke a semantic UI element by name, automation ID, or control type.",
    args_schema=ClickElementArgs,
    risk_class=RiskClass.LOW,
    timeout_s=5.0,
    executor=execute_click_element,
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.UIA, AdapterPriority.KEYBOARD, AdapterPriority.RAW_COORDINATE],
    cancellable=True,
)

TYPE_INTO_ELEMENT_SPEC = ToolSpec(
    name="type_into_element",
    description="Type or set text value into an editable UI control.",
    args_schema=TypeIntoElementArgs,
    risk_class=RiskClass.LOW,
    timeout_s=5.0,
    executor=execute_type_into_element,
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.UIA, AdapterPriority.KEYBOARD],
    cancellable=True,
)


# ---------------------------------------------------------------------------
# click_ocr_text — OCR-grounded coordinate-based click (Phase 8 fallback)
# ---------------------------------------------------------------------------

class ClickOcrTextArgs(BaseModel):
    """Arguments for click_ocr_text."""
    model_config = {"extra": "forbid"}
    text: str = Field(description="Visible text string to locate and click on screen via OCR.")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND. If omitted, uses active window.")
    min_confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Minimum OCR confidence required to accept a text target.",
    )
    region: Optional[Dict[str, int]] = Field(
        default=None,
        description="Window-relative region {'left', 'top', 'right', 'bottom'} to restrict OCR scan.",
    )

    @model_validator(mode="after")
    def _require_text(self) -> "ClickOcrTextArgs":
        if not self.text or not self.text.strip():
            raise ValueError("'text' must not be empty for click_ocr_text.")
        return self


def execute_click_ocr_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Locate visible text via OCR and click the matched screen coordinate.

    Flow:
    1. Resolve active window HWND and verify foreground focus.
    2. Capture window/region image (ephemeral bytes — discarded immediately).
    3. Run OCR via OcrLifecycleManager.
    4. Find matching text words at or above min_confidence.
    5. Reject if zero or multiple ambiguous matches (Spec §E-03, §E-08).
    6. Translate window-relative center coordinates to desktop absolute.
    7. Click via InputAdapter.
    8. Discard image bytes; return ToolResult.
    """
    from pluma.adapters.base import WindowNotFoundError
    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture, CaptureError
    from pluma.perception.element_refs import BoundingBox
    from pluma.perception.freshness import FreshnessChecker, WindowMismatchError
    from pluma.perception.ocr_lifecycle import OcrLifecycleManager

    text_query = args["text"]
    hwnd = args.get("hwnd")
    min_confidence = args.get("min_confidence", 0.5)
    raw_region = args.get("region")

    # 1. Resolve active window
    context = ActiveWindowContext()
    if hwnd is None:
        active_info = context.get_active_window()
        if not active_info.is_valid or not active_info.hwnd:
            return ToolResult(
                ok=False,
                tool="click_ocr_text",
                data=args,
                factual_message="Cannot perform OCR click: no active foreground window found.",
                verified=False,
                error="No active window.",
            )
        hwnd = active_info.hwnd
        window_rect = active_info.rect
    else:
        try:
            from pluma.adapters.win32 import Win32Adapter
            w32 = Win32Adapter()
            if w32.is_window(hwnd):
                r = w32.get_window_rect(hwnd)
                window_rect = BoundingBox(left=r.left, top=r.top, right=r.right, bottom=r.bottom)
            else:
                active_info = context.get_active_window()
                window_rect = active_info.rect if active_info.is_valid else BoundingBox(left=0, top=0, right=1920, bottom=1080)
        except Exception:
            window_rect = BoundingBox(left=0, top=0, right=1920, bottom=1080)

    # 2. Parse optional region
    region: Optional[BoundingBox] = None
    if raw_region:
        try:
            region = BoundingBox(
                left=int(raw_region["left"]),
                top=int(raw_region["top"]),
                right=int(raw_region["right"]),
                bottom=int(raw_region["bottom"]),
            )
        except (KeyError, TypeError, ValueError) as e:
            return ToolResult(
                ok=False, tool="click_ocr_text", data=args,
                factual_message=f"Invalid region specification: {e}",
                verified=False, error=str(e),
            )

    # 3. Capture ephemeral image bytes
    image_bytes: Optional[bytes] = None
    try:
        capture = WindowCapture()
        if region is not None:
            image_bytes = capture.capture_region(region, hwnd=hwnd)
        else:
            image_bytes = capture.capture_window(hwnd)
    except Exception as cap_exc:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Screen capture failed: {cap_exc}",
            verified=False, error=str(cap_exc),
        )

    # 4. Run OCR (image_bytes discarded after recognition)
    try:
        from pluma.perception.ocr_lifecycle import get_default_ocr_lifecycle_manager
        ocr_manager = get_default_ocr_lifecycle_manager()
        ocr_result = ocr_manager.run_ocr(image_bytes)
    except Exception as ocr_exc:
        image_bytes = None  # Discard on error
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"OCR recognition failed: {ocr_exc}",
            verified=False, error=str(ocr_exc),
        )
    finally:
        image_bytes = None  # Explicitly discard ephemeral bytes

    # 5. Find matching words
    matches = ocr_result.find_words(text_query, min_confidence=min_confidence)

    if len(matches) == 0:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=(
                f"OCR found no text matching '{text_query}' "
                f"(min_confidence={min_confidence:.2f}) in window HWND {hwnd}."
            ),
            verified=False,
            error="OCR_NO_MATCH",
        )

    if len(matches) > 1:
        # Ambiguous duplicate labels — refuse to guess (Acceptance Test E-03)
        labels = [m.text for m in matches]
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=(
                f"Ambiguous OCR result: {len(matches)} matches for '{text_query}': "
                f"{labels}. Clarify which target to click."
            ),
            verified=False,
            error="OCR_AMBIGUOUS",
        )

    target_word = matches[0]
    word_bounds = target_word.bounds

    # Apply region offset if scanning a sub-region
    offset_left = region.left if region else 0
    offset_top = region.top if region else 0

    # Window-relative center of the matched word
    center_x_window_rel = word_bounds.center_x + offset_left
    center_y_window_rel = word_bounds.center_y + offset_top

    # Convert to desktop-absolute coordinates
    desktop_abs_x = window_rect.left + center_x_window_rel
    desktop_abs_y = window_rect.top + center_y_window_rel

    # 6. Click via InputAdapter
    try:
        input_adapter = InputAdapter()
        input_adapter.mouse_click(desktop_abs_x, desktop_abs_y)
    except Exception as click_exc:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Mouse click failed at ({desktop_abs_x}, {desktop_abs_y}): {click_exc}",
            verified=False, error=str(click_exc),
        )

    return ToolResult(
        ok=True,
        tool="click_ocr_text",
        data={
            "hwnd": hwnd,
            "text": text_query,
            "matched_text": target_word.text,
            "confidence": round(target_word.confidence, 3),
            "window_rel_x": center_x_window_rel,
            "window_rel_y": center_y_window_rel,
            "desktop_x": desktop_abs_x,
            "desktop_y": desktop_abs_y,
        },
        factual_message=(
            f"Clicked OCR-matched text '{target_word.text}' "
            f"(confidence={target_word.confidence:.2f}) at desktop "
            f"({desktop_abs_x}, {desktop_abs_y}) in window HWND {hwnd}."
        ),
        verified=False,  # Postcondition verified by caller or ScreenVerifier
    )


def verify_click_ocr_text(result: ToolResult) -> VerifyResult:
    """Verifier for OCR text clicks: accurately reports verified status."""
    if not result.ok:
        return VerifyResult(ok=False, method="ocr_grounded", detail=result.error or "OCR click reported failure.")
    return VerifyResult(
        ok=result.verified,
        method="ocr_grounded",
        detail="OCR click dispatched to desktop coordinates.",
    )


CLICK_OCR_TEXT_SPEC = ToolSpec(
    name="click_ocr_text",
    description=(
        "OCR fallback: locate visible text in the active window using optical "
        "character recognition and click the matched screen position. Use only "
        "when UI Automation (click_element) cannot reach the target."
    ),
    args_schema=ClickOcrTextArgs,
    risk_class=RiskClass.LOW,
    timeout_s=10.0,
    executor=execute_click_ocr_text,
    verifier=verify_click_ocr_text,
    adapter_priority=[AdapterPriority.OCR_GROUNDED, AdapterPriority.RAW_COORDINATE],
    cancellable=True,
)


ALL_UI_TOOLS: List[ToolSpec] = [
    INSPECT_ACTIVE_WINDOW_SPEC,
    CLICK_ELEMENT_SPEC,
    TYPE_INTO_ELEMENT_SPEC,
    CLICK_OCR_TEXT_SPEC,
]
