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
    include_controls: bool = Field(default=True, description="Whether to include semantic controls.")
    max_controls: int = Field(default=50, description="Maximum number of controls to return.")


class ClickElementArgs(BaseModel):
    """Arguments for click_element."""
    name: Optional[str] = Field(default=None, description="Name or title text of the target UI element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of the target element.")
    control_type: Optional[str] = Field(default=None, description="UIA control type (e.g. 'Button', 'MenuItem').")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND. If omitted, uses active window.")

    @model_validator(mode="after")
    def _require_identifier(self) -> "ClickElementArgs":
        if not self.name and not self.auto_id and not self.control_type:
            raise ValueError("At least one of 'name', 'auto_id', or 'control_type' must be specified.")
        return self


class TypeIntoElementArgs(BaseModel):
    """Arguments for type_into_element."""
    text: str = Field(description="Text to type or set into the target element.")
    name: Optional[str] = Field(default=None, description="Name or label of the target editable element.")
    auto_id: Optional[str] = Field(default=None, description="UIA AutomationId of the editable element.")
    hwnd: Optional[int] = Field(default=None, description="Target window HWND. If omitted, uses active window.")
    clear_existing: bool = Field(default=True, description="Clear existing text before typing.")


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
    name = args.get("name")
    auto_id = args.get("auto_id")
    control_type = args.get("control_type")
    hwnd = args.get("hwnd")

    if hwnd is None:
        context = ActiveWindowContext()
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
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "control_type": control_type},
            factual_message=f"Clicked UI element '{target_label}' in window HWND {hwnd}.",
            verified=v_res.ok,
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
    text = args["text"]
    name = args.get("name")
    auto_id = args.get("auto_id")
    hwnd = args.get("hwnd")

    if hwnd is None:
        context = ActiveWindowContext()
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

    adapter = UiaAdapter()
    verifier = ScreenVerifier(uia_adapter=adapter)

    try:
        adapter.set_control_text(
            hwnd=hwnd,
            text=text,
            auto_id=auto_id,
            name=name,
            timeout_s=3.0,
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
            data={"hwnd": hwnd, "name": name, "auto_id": auto_id, "text_length": len(text)},
            factual_message=f"Typed text into '{target_label}' in window HWND {hwnd}.",
            verified=v_res.ok,
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

ALL_UI_TOOLS: List[ToolSpec] = [
    INSPECT_ACTIVE_WINDOW_SPEC,
    CLICK_ELEMENT_SPEC,
    TYPE_INTO_ELEMENT_SPEC,
]
