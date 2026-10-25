"""pluma.tools.ui — UI interaction tools via Windows UI Automation.

Spec §12, §14, §15: UI interactions are registered ToolSpecs.
pywinauto and UiaAdapter are imported lazily inside executors to protect the
resident core startup footprint.
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

from pluma.adapters.base import ControlInfo, ElementNotFoundError, ElementUnavailableError, WindowNotFoundError
from pluma.adapters.uia import UiaAdapter
from pluma.perception.context import ActiveWindowContext
from pluma.perception.uia_snapshot import UiaSnapshotBuilder
from pluma.tools.base import AdapterDispatcher, AdapterPriority, AdapterUnavailable, RiskClass, ToolResult, ToolSpec, VerifyResult
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
    snapshot_id: str = Field(description="Mandatory snapshot ID this click is grounded in.")
    target_ref: str = Field(description="Mandatory semantic reference string from UI snapshot (snapshot_id::element_id).")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND.")
    name: Optional[str] = Field(default=None, description="Name or title text of target element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of target element.")
    control_type: Optional[str] = Field(default=None, description="UIA control type.")
    expected_enabled: Optional[bool] = Field(
        default=None,
        description=(
            "Expected enabled state of the invoked control after the action. "
            "Without this readback request, dispatch is refused before action."
        ),
    )


class TypeIntoElementArgs(BaseModel):
    """Arguments for type_into_element."""
    model_config = {"extra": "forbid"}
    text: str = Field(description="Text to type or set into the target element.")
    snapshot_id: str = Field(description="Mandatory snapshot ID this typing action is grounded in.")
    target_ref: str = Field(description="Mandatory semantic reference string from UI snapshot (snapshot_id::element_id).")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND.")
    name: Optional[str] = Field(default=None, description="Name or label of target editable element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of editable element.")
    clear_existing: bool = Field(default=True, description="Clear existing text before typing.")



# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def inspect_active_window_native(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Use native context alone when semantic controls were not requested."""
    if args.get("include_controls", True):
        raise AdapterUnavailable("Semantic controls require UIA.")
    context = ActiveWindowContext()
    active = context.get_active_window()
    if not active.is_valid or not active.hwnd:
        return ToolResult.failure("inspect_active_window", "No active foreground window found.", "NO_ACTIVE_WINDOW")
    observed = context.get_active_window()
    if not observed.is_valid or (observed.hwnd, observed.pid) != (active.hwnd, active.pid):
        return ToolResult.failure("inspect_active_window", "Active window changed during inspection.", "WINDOW_MISMATCH")
    return ToolResult.success("inspect_active_window", data={
        "hwnd": active.hwnd, "process_name": active.process_name,
        "window_title": active.window_title, "control_count": 0,
        "controls": [], "snapshot_id": None, "raw_snapshot": None,
    }, factual_message="Read the active window context without inspecting controls.")


def execute_inspect_active_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Inspect the active foreground window and return its semantic controls.

    When task_context has a snapshot_registry, the captured snapshot is registered
    and snapshot_id is returned. Callers should pass this snapshot_id to subsequent
    click_element/type_into_element calls to ground them in verified state.
    """
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

        snapshot_id = snapshot.snapshot_id

        # Build controls summary; include target_ref values anchored to snapshot_id
        # Build controls summary; include target_ref values anchored to snapshot_id and element_id
        controls_summary = [
            {
                "element_id": c.element_id,
                "label": c.label,
                "control_type": c.control_type,
                "auto_id": c.uia_automation_id,
                "bounds": c.bounds.model_dump(),
                "capability": c.invocation_capability,
                # target_ref encodes snapshot + exact element_id for grounded UI actions
                "target_ref": (
                    f"{snapshot_id}::{c.element_id}"
                    if snapshot_id else None
                ),
            }
            for c in snapshot.controls[: args.get("max_controls", 50)]
        ]

        result_data: Dict[str, Any] = {
            "hwnd": active_info.hwnd,
            "process_name": active_info.process_name,
            "window_title": active_info.window_title,
            "control_count": len(snapshot.controls),
            "controls": controls_summary,
            "snapshot_id": snapshot_id,
            "raw_snapshot": snapshot.model_dump(mode="json"),
        }

        return ToolResult(
            ok=True,
            tool="inspect_active_window",
            data=result_data,
            factual_message=(
                f"Active window: '{active_info.window_title}' ({active_info.process_name}, "
                f"HWND {active_info.hwnd}), {len(snapshot.controls)} controls discovered."
                + (f" snapshot_id={snapshot_id}" if snapshot_id else "")
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

    expected_enabled = args.get("expected_enabled")
    if not isinstance(expected_enabled, bool):
        return ToolResult.failure(
            "click_element",
            "UIA click refused before dispatch: an expected enabled-state transition is required.",
            error_code="UI_POSTCONDITION_REQUIRED",
        )

    snapshot_id = args.get("snapshot_id")
    target_ref = args.get("target_ref")

    if not snapshot_id or not target_ref:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message="UI grounding rejected: snapshot_id and target_ref are mandatory for click_element.",
            verified=False, error="UNGROUNDED_UI_ACTION",
        )

    grounded_ui_target = getattr(task_context, "grounded_ui_target", None)
    if not grounded_ui_target:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message="UI Grounding rejected: no grounded_ui_target provided by parent.",
            verified=False, error="NO_GROUNDED_UI_TARGET",
        )

    context = ActiveWindowContext()
    active = context.get_active_window()
    if not active.is_valid or not active.hwnd:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message="Cannot click element: no active foreground window found.",
            verified=False, error="NO_ACTIVE_WINDOW",
        )

    # Revalidate active window identity against snapshot
    if grounded_ui_target["snapshot_hwnd"] and active.hwnd != grounded_ui_target["snapshot_hwnd"]:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window HWND changed from {grounded_ui_target['snapshot_hwnd']} to {active.hwnd}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        )
    if grounded_ui_target["snapshot_pid"] and active.pid and active.pid != grounded_ui_target["snapshot_pid"]:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window PID changed from {grounded_ui_target['snapshot_pid']} to {active.pid}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        )
    if grounded_ui_target["snapshot_creation_time_ns"] and active.pid:
        cur_t = context.get_process_creation_time_ns(active.pid)
        if cur_t and cur_t != grounded_ui_target["snapshot_creation_time_ns"]:
            return ToolResult(
                ok=False, tool="click_element", data=args,
                factual_message="Process creation timestamp mismatch (recycled PID).",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            )
    if grounded_ui_target["snapshot_dpi_scale"] and abs(active.dpi_scale - grounded_ui_target["snapshot_dpi_scale"]) > 0.05:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"DPI scaling changed from {grounded_ui_target['snapshot_dpi_scale']} to {active.dpi_scale}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        )
    
    # Check window bounds with 20px tolerance for slight shifts
    if "snapshot_rect_left" in grounded_ui_target and active.rect:
        dx = abs(active.rect.left - grounded_ui_target["snapshot_rect_left"])
        dy = abs(active.rect.top - grounded_ui_target["snapshot_rect_top"])
        dw = abs((active.rect.right - active.rect.left) - (grounded_ui_target["snapshot_rect_right"] - grounded_ui_target["snapshot_rect_left"]))
        dh = abs((active.rect.bottom - active.rect.top) - (grounded_ui_target["snapshot_rect_bottom"] - grounded_ui_target["snapshot_rect_top"]))
        if max(dx, dy, dw, dh) > 20:
            return ToolResult(
                ok=False, tool="click_element", data=args,
                factual_message="Active window moved or resized significantly since snapshot. Action aborted for safety.",
                verified=False, error="WINDOW_MOVED", error_code="WINDOW_MOVED",
            )

    hwnd = active.hwnd
    auto_id = grounded_ui_target["auto_id"]
    name = grounded_ui_target["name"]
    control_type = grounded_ui_target["control_type"]

    adapter = UiaAdapter()
    verifier = ScreenVerifier(uia_adapter=adapter)

    try:
        before = adapter.find_control(
            hwnd=hwnd,
            auto_id=auto_id,
            name=name,
            control_type=control_type,
            timeout_s=3.0,
        )
        if before.is_enabled is expected_enabled:
            return ToolResult.failure(
                "click_element",
                "UIA click refused before dispatch: the expected enabled state is already present, so no transition could be verified.",
                error_code="UI_NO_EXPECTED_TRANSITION",
            )

        adapter.invoke_control(
            hwnd=hwnd,
            auto_id=auto_id,
            name=name,
            control_type=control_type,
            timeout_s=3.0,
        )

        v_res = verifier.verify_control_enabled(
            hwnd=hwnd,
            expected_enabled=expected_enabled,
            auto_id=auto_id,
            name=name,
        )
        target_label = name or auto_id or control_type or "unknown"

        return ToolResult(
            ok=True,
            tool="click_element",
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "control_type": control_type, "snapshot_id": snapshot_id, "target_ref": target_ref},
            factual_message=(
                f"Invoked UI element '{target_label}' in window HWND {hwnd}. "
                + "Expected enabled-state transition was read back."
            ),
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except (ElementNotFoundError, ElementUnavailableError, WindowNotFoundError) as known_exc:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Failed to click element: {known_exc}",
            verified=False, error=str(known_exc), error_code="ELEMENT_NOT_FOUND",
        )
    except Exception as exc:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Error clicking UI element: {exc}",
            verified=False, error=str(exc), error_code="CLICK_FAILED",
        )


def execute_type_into_element(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Set or type text into a target editable UI element."""
    if task_context and hasattr(task_context, "cancellation_token") and task_context.cancellation_token.is_cancelled:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="Task cancelled before typing could execute.",
            verified=False, error="TASK_CANCELLED", error_code="TASK_CANCELLED",
        )

    text = args["text"]
    clear_existing = args.get("clear_existing", True)
    snapshot_id = args.get("snapshot_id")
    target_ref = args.get("target_ref")

    if not snapshot_id or not target_ref:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="UI grounding rejected: snapshot_id and target_ref are mandatory for type_into_element.",
            verified=False, error="UNGROUNDED_UI_ACTION", error_code="UNGROUNDED_UI_ACTION",
        )

    grounded_ui_target = getattr(task_context, "grounded_ui_target", None)
    if not grounded_ui_target:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="UI Grounding rejected: no grounded_ui_target provided by parent.",
            verified=False, error="NO_GROUNDED_UI_TARGET", error_code="NO_GROUNDED_UI_TARGET",
        )

    context = ActiveWindowContext()
    active = context.get_active_window()
    if not active.is_valid or not active.hwnd:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="Cannot type: no active foreground window found.",
            verified=False, error="NO_ACTIVE_WINDOW", error_code="NO_ACTIVE_WINDOW",
        )

    # Revalidate active window identity against snapshot
    if grounded_ui_target["snapshot_hwnd"] and active.hwnd != grounded_ui_target["snapshot_hwnd"]:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window HWND changed from {grounded_ui_target['snapshot_hwnd']} to {active.hwnd}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        )
    if grounded_ui_target["snapshot_pid"] and active.pid and active.pid != grounded_ui_target["snapshot_pid"]:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window PID changed from {grounded_ui_target['snapshot_pid']} to {active.pid}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        )
    if grounded_ui_target["snapshot_creation_time_ns"] and active.pid:
        cur_t = context.get_process_creation_time_ns(active.pid)
        if cur_t and cur_t != grounded_ui_target["snapshot_creation_time_ns"]:
            return ToolResult(
                ok=False, tool="type_into_element", data=args,
                factual_message="Process creation timestamp mismatch (recycled PID).",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            )
    if grounded_ui_target["snapshot_dpi_scale"] and abs(active.dpi_scale - grounded_ui_target["snapshot_dpi_scale"]) > 0.05:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"DPI scaling changed from {grounded_ui_target['snapshot_dpi_scale']} to {active.dpi_scale}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        )
        
    # Check window bounds with 20px tolerance for slight shifts
    if "snapshot_rect_left" in grounded_ui_target and active.rect:
        dx = abs(active.rect.left - grounded_ui_target["snapshot_rect_left"])
        dy = abs(active.rect.top - grounded_ui_target["snapshot_rect_top"])
        dw = abs((active.rect.right - active.rect.left) - (grounded_ui_target["snapshot_rect_right"] - grounded_ui_target["snapshot_rect_left"]))
        dh = abs((active.rect.bottom - active.rect.top) - (grounded_ui_target["snapshot_rect_bottom"] - grounded_ui_target["snapshot_rect_top"]))
        if max(dx, dy, dw, dh) > 20:
            return ToolResult(
                ok=False, tool="type_into_element", data=args,
                factual_message="Active window moved or resized significantly since snapshot. Action aborted for safety.",
                verified=False, error="WINDOW_MOVED", error_code="WINDOW_MOVED",
            )

    hwnd = active.hwnd
    auto_id = grounded_ui_target["auto_id"]
    name = grounded_ui_target["name"]

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
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "text_length": len(text), "snapshot_id": snapshot_id, "target_ref": target_ref},
            factual_message=f"Typed text into '{target_label}' in window HWND {hwnd}.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except (ElementNotFoundError, ElementUnavailableError, WindowNotFoundError) as known_exc:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Failed to type into element: {known_exc}",
            verified=False, error=str(known_exc),
        )
    except Exception as exc:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Error typing into UI element: {exc}",
            verified=False, error=str(exc),
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
    executor=AdapterDispatcher("inspect_active_window", {
        AdapterPriority.NATIVE_API: inspect_active_window_native,
        AdapterPriority.UIA: execute_inspect_active_window,
    }),
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.NATIVE_API, AdapterPriority.UIA],
    cancellable=True,
)

CLICK_ELEMENT_SPEC = ToolSpec(
    name="click_element",
    description="Click or invoke a semantic UI element by name, automation ID, or control type.",
    args_schema=ClickElementArgs,
    risk_class=RiskClass.LOW,
    timeout_s=5.0,
    executor=AdapterDispatcher("click_element", {AdapterPriority.UIA: execute_click_element}),
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.UIA],
    cancellable=True,
)

TYPE_INTO_ELEMENT_SPEC = ToolSpec(
    name="type_into_element",
    description="Type or set text value into an editable UI control.",
    args_schema=TypeIntoElementArgs,
    risk_class=RiskClass.LOW,
    timeout_s=5.0,
    executor=AdapterDispatcher("type_into_element", {AdapterPriority.UIA: execute_type_into_element}),
    verifier=verify_noop,
    adapter_priority=[AdapterPriority.UIA],
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
    snapshot_id: Optional[str] = Field(default=None, description="Optional snapshot ID to verify target window freshness.")
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
    1. Check cancellation token.
    2. Re-check target window identity, geometry, and DPI.
    3. If snapshot_id provided, revalidate snapshot freshness.
    4. Capture window/region image (ephemeral bytes — discarded immediately).
    5. Run OCR via OcrLifecycleManager.
    6. Reject if zero or multiple ambiguous matches (Spec §E-03, §E-08).
    7. Translate window-relative center coordinates to desktop absolute and verify within bounds.
    8. Click via InputAdapter.
    9. Perform postcondition verification.
    """
    from pluma.core.cancellation import TaskCancelledError

    cancellation_token = getattr(task_context, "cancellation_token", None)
    if cancellation_token is not None and cancellation_token.is_cancelled:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message="Task cancelled before OCR click could execute.",
            verified=False, error="TASK_CANCELLED", error_code="TASK_CANCELLED",
        )

    from pluma.adapters.input import InputAdapter
    from pluma.perception.capture import WindowCapture
    from pluma.perception.element_refs import BoundingBox
    from pluma.verify.screen import ScreenVerifier

    text_query = args["text"]
    hwnd = args.get("hwnd")
    min_confidence = args.get("min_confidence", 0.5)
    raw_region = args.get("region")
    snapshot_id = args.get("snapshot_id")

    def check_cancelled() -> None:
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

    # 1. Resolve and re-check target window identity
    context = ActiveWindowContext()
    active_info = context.get_active_window()
    if hwnd is None:
        if not active_info.is_valid or not active_info.hwnd:
            return ToolResult(
                ok=False,
                tool="click_ocr_text",
                data=args,
                factual_message="Cannot perform OCR click: no active foreground window found.",
                verified=False,
                error="No active window.",
                error_code="NO_ACTIVE_WINDOW",
            )
        target_hwnd = active_info.hwnd
        target_info = active_info
    else:
        target_hwnd = hwnd
        if active_info.is_valid and active_info.hwnd == target_hwnd:
            target_info = active_info
        else:
            target_info = context.get_window_info(target_hwnd)
            if not target_info.is_valid or target_info.hwnd != target_hwnd:
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message=f"Target window HWND {target_hwnd} does not exist or is inaccessible.",
                    verified=False, error="WINDOW_NOT_FOUND", error_code="WINDOW_NOT_FOUND",
                )

    window_rect = target_info.rect
    if not target_info.is_valid or target_info.hwnd != target_hwnd or window_rect.width <= 0 or window_rect.height <= 0:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Target window HWND {target_hwnd} has no valid geometry for OCR grounding.",
            verified=False, error="WINDOW_GEOMETRY_UNAVAILABLE", error_code="WINDOW_GEOMETRY_UNAVAILABLE",
        )
    captured_dpi_scale = target_info.dpi_scale
    captured_pid = target_info.pid
    if not captured_pid:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Target window HWND {target_hwnd} has no process identity for OCR grounding.",
            verified=False, error="PROCESS_IDENTITY_UNAVAILABLE", error_code="PROCESS_IDENTITY_UNAVAILABLE",
        )
    captured_creation_time_ns = context.get_process_creation_time_ns(captured_pid)
    if captured_creation_time_ns is None:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Process creation time for target HWND {target_hwnd} could not be verified.",
            verified=False, error="PROCESS_IDENTITY_UNAVAILABLE", error_code="PROCESS_IDENTITY_UNAVAILABLE",
        )

    # 2. Re-check snapshot freshness if snapshot_id provided
    if snapshot_id:
        snapshot_registry = getattr(task_context, "snapshot_registry", None)
        if snapshot_registry is None:
            return ToolResult(
                ok=False, tool="click_ocr_text", data=args,
                factual_message="Snapshot freshness cannot be verified because this task has no snapshot registry.",
                verified=False, error="SNAPSHOT_REGISTRY_UNAVAILABLE", error_code="STALE_SNAPSHOT",
            )
        try:
            snap = snapshot_registry.resolve(snapshot_id)
            if snap.hwnd and snap.hwnd != target_hwnd:
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message=f"Snapshot HWND {snap.hwnd} mismatch with target HWND {target_hwnd}.",
                    verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
                )
            if snap.pid and snap.pid != captured_pid:
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message="Snapshot process identity does not match the target window.",
                    verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
                )
            if (snap.process_creation_time_ns is not None
                    and snap.process_creation_time_ns != captured_creation_time_ns):
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message="Snapshot process creation identity does not match the target window.",
                    verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
                )
            if snap.dpi_scale and captured_dpi_scale and abs(snap.dpi_scale - captured_dpi_scale) > 0.05:
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message="Target window DPI differs from the supplied screen snapshot.",
                    verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
                )
            if snap.window_rect and window_rect:
                dx = abs(window_rect.left - snap.window_rect.left)
                dy = abs(window_rect.top - snap.window_rect.top)
                if max(dx, dy) > 20:
                    return ToolResult(
                        ok=False, tool="click_ocr_text", data=args,
                        factual_message="Target window moved or resized significantly (>20px) since snapshot.",
                        verified=False, error="WINDOW_MOVED", error_code="WINDOW_MOVED",
                    )
        except Exception as fresh_err:
            return ToolResult(
                ok=False, tool="click_ocr_text", data=args,
                factual_message=f"Snapshot freshness check failed: {fresh_err}",
                verified=False, error=str(fresh_err), error_code="STALE_SNAPSHOT",
            )

    # 3. Parse optional region
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
                verified=False, error=str(e), error_code="INVALID_REGION",
            )

    # 4. Capture ephemeral image bytes
    image_bytes: Optional[bytes] = None
    try:
        check_cancelled()
        capture = WindowCapture()
        if region is not None:
            image_bytes = capture.capture_region(region, hwnd=target_hwnd)
        else:
            image_bytes = capture.capture_window(target_hwnd)
    except TaskCancelledError:
        raise
    except Exception as cap_exc:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Screen capture failed: {cap_exc}",
            verified=False, error=str(cap_exc), error_code="CAPTURE_FAILED",
        )

    # 5. Run OCR only on the captured target image. A process-isolated ToolSpec
    # supplies the hard stop boundary for an uninterruptible OCR backend.
    try:
        from pluma.perception.ocr_lifecycle import get_default_ocr_lifecycle_manager
        ocr_manager = get_default_ocr_lifecycle_manager()
        check_cancelled()
        ocr_result = ocr_manager.run_ocr(image_bytes, cancellation_token=cancellation_token)
        check_cancelled()
    except TaskCancelledError:
        raise
    except Exception as ocr_exc:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"OCR recognition failed: {ocr_exc}",
            verified=False, error=str(ocr_exc), error_code="OCR_FAILED",
        )
    finally:
        image_bytes = None  # Explicitly discard ephemeral bytes

    # 6. Find matching words
    matches = ocr_result.find_words(text_query, min_confidence=min_confidence)

    if len(matches) == 0:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=(
                f"OCR found no text matching '{text_query}' "
                f"(min_confidence={min_confidence:.2f}) in window HWND {target_hwnd}."
            ),
            verified=False,
            error="OCR_NO_MATCH",
            error_code="OCR_NO_MATCH",
        )

    if len(matches) > 1:
        labels = [m.text for m in matches]
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=(
                f"Ambiguous OCR result: {len(matches)} matches for '{text_query}': "
                f"{labels}. Refusing to guess ambiguous target."
            ),
            verified=False,
            error="OCR_AMBIGUOUS",
            error_code="OCR_AMBIGUOUS",
        )

    target_word = matches[0]
    word_bounds = target_word.bounds

    # Apply region offset if scanning a sub-region
    offset_left = region.left if region else 0
    offset_top = region.top if region else 0

    # Window-relative center of the matched word
    center_x_window_rel = word_bounds.center_x + offset_left
    center_y_window_rel = word_bounds.center_y + offset_top

    # Refresh target identity/freshness before translating OCR bounds into
    # desktop coordinates or dispatching coordinate fallback.
    current_active = context.get_active_window()
    if not current_active.is_valid or current_active.hwnd != target_hwnd:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Pre-click safety abort: Active window changed right before click. Expected HWND {target_hwnd}.",
            verified=False, error="WINDOW_CHANGED_BEFORE_CLICK", error_code="WINDOW_CHANGED_BEFORE_CLICK",
        )
    if current_active.pid != captured_pid:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message="Pre-click safety abort: target window process changed after OCR capture.",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        )
    current_creation_time_ns = context.get_process_creation_time_ns(current_active.pid)
    if current_creation_time_ns is None or current_creation_time_ns != captured_creation_time_ns:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message="Pre-click safety abort: target process identity changed after OCR capture.",
            verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
        )

    # OCR coordinates belong to the exact window geometry and DPI used for
    # capture. Refresh both immediately before coordinate fallback; if either
    # changed while OCR ran, the old target coordinates are stale and unsafe.
    current_rect = current_active.rect
    if not current_rect or current_rect.width <= 0 or current_rect.height <= 0:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message="Pre-click safety abort: current window geometry could not be verified.",
            verified=False, error="WINDOW_GEOMETRY_UNAVAILABLE", error_code="WINDOW_GEOMETRY_UNAVAILABLE",
        )
    if (current_rect.left, current_rect.top, current_rect.right, current_rect.bottom) != (
        window_rect.left, window_rect.top, window_rect.right, window_rect.bottom
    ):
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message="Pre-click safety abort: target window moved or resized after OCR capture.",
            verified=False, error="WINDOW_MOVED", error_code="WINDOW_MOVED",
        )
    if captured_dpi_scale and abs(current_active.dpi_scale - captured_dpi_scale) > 0.05:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=(
                "Pre-click safety abort: DPI changed after OCR capture "
                f"({captured_dpi_scale} to {current_active.dpi_scale})."
            ),
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        )

    # If snapshot was provided, completely revalidate against it right before the click
    if snapshot_id:
        snapshot_registry = getattr(task_context, "snapshot_registry", None)
        if snapshot_registry:
            try:
                # resolve() inherently checks TTL/expiration
                final_snap = snapshot_registry.resolve(snapshot_id)
                if final_snap.hwnd and final_snap.hwnd != current_active.hwnd:
                     return ToolResult(ok=False, tool="click_ocr_text", data=args, factual_message="Pre-click abort: HWND mismatch", verified=False, error="WINDOW_MISMATCH")
                if final_snap.pid and current_active.pid and final_snap.pid != current_active.pid:
                     return ToolResult(ok=False, tool="click_ocr_text", data=args, factual_message="Pre-click abort: PID mismatch", verified=False, error="PROCESS_MISMATCH")
                if final_snap.dpi_scale and abs(current_active.dpi_scale - final_snap.dpi_scale) > 0.05:
                     return ToolResult(ok=False, tool="click_ocr_text", data=args, factual_message="Pre-click abort: DPI mismatch", verified=False, error="DPI_MISMATCH")
                
                # Check FULL window geometry/resize
                if final_snap.window_rect and current_active.rect:
                    dx = abs(current_active.rect.left - final_snap.window_rect.left)
                    dy = abs(current_active.rect.top - final_snap.window_rect.top)
                    dw = abs((current_active.rect.right - current_active.rect.left) - (final_snap.window_rect.right - final_snap.window_rect.left))
                    dh = abs((current_active.rect.bottom - current_active.rect.top) - (final_snap.window_rect.bottom - final_snap.window_rect.top))
                    if max(dx, dy, dw, dh) > 20:
                        return ToolResult(ok=False, tool="click_ocr_text", data=args, factual_message="Pre-click abort: Window moved or resized", verified=False, error="WINDOW_MOVED")
            except Exception as fresh_err:
                return ToolResult(
                    ok=False, tool="click_ocr_text", data=args,
                    factual_message=f"Pre-click safety abort: Snapshot freshness check failed: {fresh_err}",
                    verified=False, error=str(fresh_err), error_code="STALE_SNAPSHOT",
                )

    # Use the fresh, verified geometry for coordinate translation.
    desktop_abs_x = current_rect.left + center_x_window_rel
    desktop_abs_y = current_rect.top + center_y_window_rel

    if (
        desktop_abs_x < current_rect.left
        or desktop_abs_x > current_rect.right
        or desktop_abs_y < current_rect.top
        or desktop_abs_y > current_rect.bottom
    ):
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Computed click coordinates ({desktop_abs_x}, {desktop_abs_y}) lie outside window bounds.",
            verified=False, error="COORDINATES_OUT_OF_BOUNDS", error_code="COORDINATES_OUT_OF_BOUNDS",
        )

    # 8. Click via InputAdapter. STOP during OCR is observed before the next
    # state-changing operation; the isolated worker is also killable by STOP.
    try:
        check_cancelled()
        input_adapter = InputAdapter()
        input_adapter.mouse_click(desktop_abs_x, desktop_abs_y)
    except TaskCancelledError:
        raise
    except Exception as click_exc:
        return ToolResult(
            ok=False, tool="click_ocr_text", data=args,
            factual_message=f"Mouse click failed at ({desktop_abs_x}, {desktop_abs_y}): {click_exc}",
            verified=False, error=str(click_exc), error_code="CLICK_FAILED",
        )

    # 9. Read back the selected target. A change in unrelated OCR word counts
    # is not evidence that this target transitioned.
    verified = False
    v_res = None
    post_image_bytes: Optional[bytes] = None
    try:
        check_cancelled()
        time.sleep(0.3)  # Wait for UI to react
        check_cancelled()
        if region is not None:
            post_image_bytes = capture.capture_region(region, hwnd=target_hwnd)
        else:
            post_image_bytes = capture.capture_window(target_hwnd)
        check_cancelled()
        post_ocr = ocr_manager.run_ocr(post_image_bytes, cancellation_token=cancellation_token)
        check_cancelled()
        post_matches = post_ocr.find_words(text_query, min_confidence=min_confidence)
        original_bounds = BoundingBox(
            left=word_bounds.left + offset_left,
            top=word_bounds.top + offset_top,
            right=word_bounds.right + offset_left,
            bottom=word_bounds.bottom + offset_top,
        )
        target_still_at_original_bounds = any(
            match.text.strip().casefold() == target_word.text.strip().casefold()
            and _ocr_bounds_overlap(original_bounds, BoundingBox(
                left=match.bounds.left + offset_left,
                top=match.bounds.top + offset_top,
                right=match.bounds.right + offset_left,
                bottom=match.bounds.bottom + offset_top,
            )) >= 0.5
            for match in post_matches
        )
        if not target_still_at_original_bounds:
            verified = True
            v_res = VerifyResult(
                ok=True,
                method="ocr_target_transition",
                detail="The uniquely matched OCR target disappeared or moved from its original bounds.",
            )
        else:
            verified = False
            v_res = VerifyResult(
                ok=False,
                method="ocr_target_transition",
                detail="The original OCR target remains at the same bounds; its expected transition was not observed.",
            )
    except TaskCancelledError:
        raise
    except Exception as verify_exc:
        v_res = VerifyResult(ok=False, method="ocr_target_transition", detail=f"Post-click verification failed: {verify_exc}")
    finally:
        post_image_bytes = None

    return ToolResult(
        ok=True,
        tool="click_ocr_text",
        data={
            "hwnd": target_hwnd,
            "text": text_query,
            "matched_text": target_word.text,
            "confidence": round(target_word.confidence, 3),
            "window_rel_x": center_x_window_rel,
            "window_rel_y": center_y_window_rel,
            "desktop_x": desktop_abs_x,
            "desktop_y": desktop_abs_y,
            "snapshot_id": snapshot_id,
        },
        factual_message=(
            f"Clicked OCR-matched text '{target_word.text}' "
            f"(confidence={target_word.confidence:.2f}) at desktop "
            f"({desktop_abs_x}, {desktop_abs_y}) in window HWND {target_hwnd}."
        ),
        verified=verified,
        verify_detail=v_res or VerifyResult(
            ok=False,
            method="ocr_target_transition",
            detail="OCR click dispatched but the expected target transition was not confirmed.",
        ),
    )


def _ocr_bounds_overlap(first: Any, second: Any) -> float:
    """Return the intersection as a fraction of the smaller OCR target box."""
    intersection_width = max(0, min(first.right, second.right) - max(first.left, second.left))
    intersection_height = max(0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = intersection_width * intersection_height
    smaller_area = min(first.width * first.height, second.width * second.height)
    return intersection / smaller_area if smaller_area > 0 else 0.0


def verify_click_ocr_text(result: ToolResult) -> VerifyResult:
    """Verifier for OCR text clicks: accurately reports verified status with proof."""
    if not result.ok:
        return VerifyResult(ok=False, method="ocr_grounded", detail=result.error or "OCR click reported failure.")
    if not result.verified:
        return VerifyResult(ok=False, method="ocr_grounded", detail="OCR click completed without verified postcondition proof.")
    return VerifyResult(
        ok=True,
        method="ocr_grounded",
        detail=result.verify_detail.detail if result.verify_detail else "OCR click postcondition verified.",
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
    process_isolated=True,
    executor=AdapterDispatcher("click_ocr_text", {AdapterPriority.OCR_GROUNDED: execute_click_ocr_text}),
    verifier=verify_click_ocr_text,
    adapter_priority=[AdapterPriority.OCR_GROUNDED],
    cancellable=True,
)


ALL_UI_TOOLS: List[ToolSpec] = [
    INSPECT_ACTIVE_WINDOW_SPEC,
    CLICK_ELEMENT_SPEC,
    TYPE_INTO_ELEMENT_SPEC,
    CLICK_OCR_TEXT_SPEC,
]
