"""Typed Section 21 screen-control catalog tools.

All screen actions require a task-owned, unexpired snapshot reference. UIA is
used first; OCR and window-relative input remain explicit, target-scoped
fallbacks. Screenshot bytes stay in memory and never enter ToolResult data.
"""

from __future__ import annotations

import time
import uuid
from functools import partial
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field, model_validator

from pluma.adapters.base import ElementNotFoundError, ElementUnavailableError, WindowNotFoundError
from pluma.adapters.uia import UiaAdapter
from pluma.core.cancellation import TaskCancelledError
from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement, ScreenSnapshot
from pluma.perception.snapshot_registry import SnapshotNotFoundError, SnapshotRegistry
from pluma.perception.element_refs import StaleSnapshotError
from pluma.perception.uia_snapshot import UiaSnapshotBuilder
from pluma.tools.base import AdapterDispatcher, AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import verify_noop

_SNAPSHOT_TTL_S = 3.0
_INPUT_KEYS = {
    "tab", "enter", "return", "escape", "esc", "space", "backspace", "delete", "del",
    "home", "end", "pageup", "pagedown", "left", "right", "up", "down",
    *{f"f{i}" for i in range(1, 13)},
    *{chr(code) for code in range(ord("a"), ord("z") + 1)},
    *{str(number) for number in range(10)},
}
_MODIFIERS = {"ctrl", "control", "alt", "shift"}
SCREEN_TEXT_UNDO_TTL_S = 1800.0
SCREEN_TEXT_UNDO_MAX = 128


class _NoArgs(BaseModel):
    model_config = {"extra": "forbid"}


class InspectWindowControlsArgs(BaseModel):
    model_config = {"extra": "forbid"}
    hwnd: Optional[int] = Field(default=None, gt=0)
    max_controls: int = Field(default=50, ge=1, le=200)


class SnapshotArgs(BaseModel):
    model_config = {"extra": "forbid"}
    snapshot_id: str = Field(min_length=1, max_length=80)


class CaptureTargetWindowArgs(SnapshotArgs):
    region: Optional[BoundingBox] = None


class ReadVisibleTextArgs(CaptureTargetWindowArgs):
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class FindVisibleTextArgs(ReadVisibleTextArgs):
    visible_text_query: str = Field(min_length=1, max_length=256)
    exact_match: bool = True


class RefreshScreenSnapshotArgs(BaseModel):
    model_config = {"extra": "forbid"}
    snapshot_id: Optional[str] = Field(default=None, min_length=1, max_length=80)
    hwnd: Optional[int] = Field(default=None, gt=0)
    include_ocr: bool = False

class FindControlArgs(SnapshotArgs):
    label: Optional[str] = Field(default=None, min_length=1, max_length=256)
    automation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    control_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    exact_match: bool = True

    @model_validator(mode="after")
    def selector_required(self) -> "FindControlArgs":
        if not (self.label or self.automation_id or self.control_type):
            raise ValueError("label, automation_id or control_type is required")
        return self


class ScreenTargetArgs(SnapshotArgs):
    target_ref: str = Field(min_length=1, max_length=180)


class InvokeControlArgs(ScreenTargetArgs):
    expected_enabled: bool


class SetControlTextArgs(ScreenTargetArgs):
    screen_input: str = Field(max_length=2048)


class ReadControlTextArgs(ScreenTargetArgs):
    pass


class WaitForControlArgs(SnapshotArgs):
    label: Optional[str] = Field(default=None, min_length=1, max_length=256)
    automation_id: Optional[str] = Field(default=None, min_length=1, max_length=128)
    control_type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    timeout_ms: int = Field(default=1000, ge=1, le=2500)

    @model_validator(mode="after")
    def selector_required(self) -> "WaitForControlArgs":
        if not (self.label or self.automation_id or self.control_type):
            raise ValueError("label, automation_id or control_type is required")
        return self


class InvokeScreenElementArgs(ScreenTargetArgs):
    expected_enabled: Optional[bool] = None


class _ExpectedInputPostcondition(BaseModel):
    expected_control_text: Optional[str] = Field(default=None, max_length=2048)
    expected_enabled: Optional[bool] = None

    @model_validator(mode="after")
    def postcondition_required(self):
        if self.expected_control_text is None and self.expected_enabled is None:
            raise ValueError("an expected_control_text or expected_enabled readback is required")
        return self


class PressKeyArgs(ScreenTargetArgs, _ExpectedInputPostcondition):
    key: str = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def safe_key(self) -> "PressKeyArgs":
        if self.key.casefold() not in _INPUT_KEYS:
            raise ValueError("key is outside the supported stable-input set")
        return self


class HotkeyArgs(ScreenTargetArgs, _ExpectedInputPostcondition):
    modifiers: List[str] = Field(min_length=1, max_length=3)
    key: str = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def safe_chord(self) -> "HotkeyArgs":
        mods = [item.casefold() for item in self.modifiers]
        if len(mods) != len(set(mods)) or any(item not in _MODIFIERS for item in mods):
            raise ValueError("modifiers must be unique Ctrl, Alt or Shift keys")
        if self.key.casefold() not in _INPUT_KEYS or self.key.casefold() in _MODIFIERS:
            raise ValueError("key is outside the supported stable-input set")
        return self


class TypeTextArgs(ScreenTargetArgs, _ExpectedInputPostcondition):
    screen_input: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def text_readback_required(self) -> "TypeTextArgs":
        if self.expected_control_text is None:
            raise ValueError("expected_control_text is required for text-input verification")
        return self


class ClickWindowRelativeArgs(ScreenTargetArgs):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)


def _failure(tool: str, message: str, code: str) -> ToolResult:
    return ToolResult.failure(tool, message, error_code=code)


def _cancel(task_context: Any) -> None:
    token = getattr(task_context, "cancellation_token", None)
    if token is not None:
        token.raise_if_cancelled()


def _snapshot(snapshot_id: str, task_context: Any, tool: str) -> ScreenSnapshot:
    registry = getattr(task_context, "snapshot_registry", None)
    if not isinstance(registry, SnapshotRegistry):
        raise ValueError("Task has no screen snapshot registry.")
    return registry.resolve(snapshot_id)


def _check_window(snapshot: ScreenSnapshot, task_context: Any, *, foreground: bool = True) -> ActiveWindowInfo:
    context = ActiveWindowContext()
    current = context.get_active_window() if foreground else context.get_window_info(snapshot.hwnd or 0)
    if not current.is_valid or not current.hwnd:
        raise ValueError("The snapshot target window is no longer available.")
    if (snapshot.hwnd != current.hwnd or snapshot.pid != current.pid
            or snapshot.active_process.casefold() != current.process_name.casefold()
            or snapshot.active_window_title != current.window_title):
        raise ValueError("The current window identity differs from the snapshot.")
    if snapshot.process_creation_time_ns is None:
        raise ValueError("The snapshot has no verified process creation identity.")
    creation = context.get_process_creation_time_ns(current.pid)
    if creation is None or creation != snapshot.process_creation_time_ns:
        raise ValueError("The current process creation identity differs from the snapshot.")
    if snapshot.window_class and snapshot.window_class != current.class_name:
        raise ValueError("The current window class differs from the snapshot.")
    if snapshot.window_rect != current.rect:
        raise ValueError("The target window moved or resized after the snapshot.")
    if abs(snapshot.dpi_scale - current.dpi_scale) > 0.01:
        raise ValueError("The target window DPI differs from the snapshot.")
    return current


def _target(args: Dict[str, Any], task_context: Any, tool: str,
            sources: Optional[Sequence[ElementSource]] = None):
    try:
        snapshot = _snapshot(args["snapshot_id"], task_context, tool)
        prefix, separator, element_id = args["target_ref"].partition("::")
        if not separator or prefix != snapshot.snapshot_id or not element_id:
            raise ValueError("target_ref does not belong to snapshot_id.")
        element = task_context.snapshot_registry.resolve_element(snapshot.snapshot_id, element_id)
        if element.snapshot_id != snapshot.snapshot_id:
            raise ValueError("Screen element belongs to another snapshot.")
        if sources is not None and element.source not in sources:
            raise ValueError("The screen element source is not supported by this tool.")
        peers = [candidate for candidate in (*snapshot.controls, *snapshot.ocr_words)
                 if candidate.source == element.source
                 and candidate.label.strip().casefold() == element.label.strip().casefold()]
        if len(peers) != 1:
            raise ValueError(f"Screen target label is ambiguous ({len(peers)} matching elements).")
        current = _check_window(snapshot, task_context)
        _cancel(task_context)
        return snapshot, element, current, None
    except TaskCancelledError:
        raise
    except (StaleSnapshotError, SnapshotNotFoundError) as exc:
        return None, None, None, _failure(tool, f"Screen target rejected: {exc}", "STALE_SNAPSHOT")
    except Exception as exc:
        message = str(exc)
        lowered = message.casefold()
        if "ambiguous" in lowered:
            code = "UI_AMBIGUOUS_TARGET"
        elif "moved" in lowered or "resized" in lowered or "dpi" in lowered:
            code = "WINDOW_MOVED"
        elif "identity" in lowered or "differs from the snapshot" in lowered:
            code = "WINDOW_MISMATCH"
        else:
            code = "SCREEN_TARGET_INVALID"
        return None, None, None, _failure(tool, f"Screen target rejected: {exc}", code)


def _summary(snapshot: ScreenSnapshot, limit: int = 200) -> List[Dict[str, Any]]:
    return [{
        "element_id": item.element_id,
        "target_ref": f"{snapshot.snapshot_id}::{item.element_id}",
        "label": item.label,
        "control_type": item.control_type,
        "automation_id": item.uia_automation_id,
        "source": item.source.value,
        "bounds": item.bounds.model_dump(),
        "confidence": item.confidence,
        "capability": item.invocation_capability,
    } for item in (*snapshot.controls, *snapshot.ocr_words)[:limit]]


def _ocr_summary(snapshot: ScreenSnapshot, elements: Optional[Sequence[ScreenElement]] = None) -> List[Dict[str, Any]]:
    selected = elements if elements is not None else snapshot.ocr_words
    return [{
        "element_id": item.element_id,
        "target_ref": f"{snapshot.snapshot_id}::{item.element_id}",
        "visible_text": item.label,
        "bounds": item.bounds.model_dump(),
        "confidence": item.confidence,
    } for item in selected]


def execute_get_active_window_context(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "get_active_window_context"
    _cancel(task_context)
    context = ActiveWindowContext()
    before = context.get_active_window()
    if not before.is_valid or not before.hwnd:
        return _failure(tool, "No active foreground window is available.", "NO_ACTIVE_WINDOW")
    creation = context.get_process_creation_time_ns(before.pid)
    if creation is None:
        return _failure(tool, "Active process creation identity could not be read.", "PROCESS_IDENTITY_UNAVAILABLE")
    after = context.get_active_window()
    after_creation = context.get_process_creation_time_ns(after.pid) if after.is_valid else None
    before_identity = (before.hwnd, before.pid, before.process_name, before.window_title,
        before.class_name, before.rect, before.dpi_scale)
    after_identity = (after.hwnd, after.pid, after.process_name, after.window_title,
        after.class_name, after.rect, after.dpi_scale)
    if not after.is_valid or before_identity != after_identity or creation != after_creation:
        return _failure(tool, "Active window changed during context inspection.", "WINDOW_MISMATCH")
    return ToolResult.success(tool, {
        "hwnd": before.hwnd, "pid": before.pid, "process_creation_time_ns": creation,
        "process_name": before.process_name, "window_title": before.window_title,
        "window_class": before.class_name, "window_rect": before.rect.model_dump(),
        "dpi_scale": before.dpi_scale,
    }, "Read the active window identity and geometry.", verified=True,
       verify_detail=VerifyResult(ok=True, method="win32",
           detail="Active HWND, process identity, geometry and DPI were read twice."))


def _resolve_window(hwnd: Optional[int], tool: str):
    context = ActiveWindowContext()
    info = context.get_active_window() if hwnd is None else context.get_window_info(hwnd)
    if not info.is_valid or not info.hwnd:
        return None, None, _failure(tool, "Target window does not exist or is inaccessible.", "WINDOW_NOT_FOUND")
    if info.pid <= 0 or context.get_process_creation_time_ns(info.pid) is None:
        return None, None, _failure(tool, "Target process identity could not be verified.", "PROCESS_IDENTITY_UNAVAILABLE")
    return context, info, None


def _new_snapshot(hwnd: int, *, include_ocr: bool, region: Optional[BoundingBox], task_context: Any):
    region = BoundingBox.model_validate(region) if region is not None else None
    _cancel(task_context)
    context = ActiveWindowContext()
    snapshot = UiaSnapshotBuilder(context=context).capture(hwnd=hwnd, ttl_seconds=_SNAPSHOT_TTL_S)
    _cancel(task_context)
    _check_window(snapshot, task_context, foreground=False)
    if not include_ocr:
        return snapshot
    from pluma.perception.capture import WindowCapture
    from pluma.perception.ocr_lifecycle import get_default_ocr_lifecycle_manager
    _cancel(task_context)
    capture = WindowCapture()
    image = capture.capture_window(hwnd) if region is None else capture.capture_region(region, hwnd=hwnd)
    try:
        _cancel(task_context)
        result = get_default_ocr_lifecycle_manager().run_ocr(
            image, cancellation_token=getattr(task_context, "cancellation_token", None))
        _cancel(task_context)
        _check_window(snapshot, task_context, foreground=False)
        offset_x = region.left if region else 0
        offset_y = region.top if region else 0
        words = [ScreenElement(
            snapshot_id=snapshot.snapshot_id,
            source=ElementSource.OCR,
            label=word.text,
            control_type="StaticText",
            bounds=BoundingBox(left=word.bounds.left + offset_x, top=word.bounds.top + offset_y,
                               right=word.bounds.right + offset_x, bottom=word.bounds.bottom + offset_y),
            confidence=word.confidence,
            invocation_capability="click",
        ) for word in result.words]
        return snapshot.model_copy(update={"ocr_words": words}), result
    finally:
        image = None


def execute_inspect_window_controls(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "inspect_window_controls"
    context, info, error = _resolve_window(args.get("hwnd"), tool)
    if error:
        return error
    try:
        _cancel(task_context)
        snapshot = UiaSnapshotBuilder(context=context).capture(hwnd=info.hwnd, ttl_seconds=_SNAPSHOT_TTL_S)
        _cancel(task_context)
        if (snapshot.hwnd != info.hwnd or snapshot.pid != info.pid
                or snapshot.process_creation_time_ns != context.get_process_creation_time_ns(info.pid)):
            return _failure(tool, "Window identity changed during semantic inspection.", "WINDOW_MISMATCH")
        _check_window(snapshot, task_context, foreground=False)
        return ToolResult.success(tool, {
            "hwnd": info.hwnd, "snapshot_id": snapshot.snapshot_id,
            "controls": _summary(snapshot, args["max_controls"]),
            "control_count": len(snapshot.controls), "raw_snapshot": snapshot.model_dump(mode="json"),
        }, f"Inspected {len(snapshot.controls)} semantic controls in the target window.", verified=True,
           verify_detail=VerifyResult(ok=True, method="uia", detail="UIA controls and target process identity were read back."))
    except Exception:
        if getattr(task_context, "cancellation_token", None) is not None and task_context.cancellation_token.is_cancelled:
            raise TaskCancelledError("Task cancelled during UIA inspection.")
        return _failure(tool, "UI Automation could not inspect the target window.", "UIA_INSPECTION_FAILED")


def execute_capture_target_window(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "capture_target_window"
    try:
        _cancel(task_context)
        snap = _snapshot(args["snapshot_id"], task_context, tool)
        info = _check_window(snap, task_context)
        from pluma.perception.capture import WindowCapture
        region_value = args.get("region")
        region = BoundingBox.model_validate(region_value) if region_value is not None else None
        image = WindowCapture().capture_window(info.hwnd) if region is None else WindowCapture().capture_region(region, hwnd=info.hwnd)
        _cancel(task_context)
        length = len(image)
        image = None
        if length <= 0:
            return _failure(tool, "Target window capture returned no image data.", "CAPTURE_FAILED")
        return ToolResult.success(tool, {"hwnd": info.hwnd, "snapshot_id": snap.snapshot_id,
            "captured": True, "byte_count": length,
            "region": region.model_dump() if region else None},
            "Captured the requested target window in memory; image bytes were discarded.", verified=True,
            verify_detail=VerifyResult(ok=True, method="win32", detail="The target-scoped capture returned non-empty in-memory bytes."))
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"Target window capture failed: {exc}", "CAPTURE_FAILED")

def _read_ocr(args: Dict[str, Any], task_context: Any, *, find: bool) -> ToolResult:
    tool = "find_visible_text" if find else "read_visible_text"
    try:
        snap = _snapshot(args["snapshot_id"], task_context, tool)
        info = _check_window(snap, task_context)
        # Read OCR once, scoped to the requested HWND/region. The derived
        # snapshot replaces the old reference for any later grounded action.
        updated, ocr = _new_snapshot(info.hwnd, include_ocr=True, region=args.get("region"), task_context=task_context)
        if (updated.hwnd != snap.hwnd or updated.pid != snap.pid
                or updated.process_creation_time_ns != snap.process_creation_time_ns):
            return _failure(tool, "Target process identity changed during OCR observation.", "WINDOW_MISMATCH")
        if updated.window_rect != snap.window_rect or abs(updated.dpi_scale - snap.dpi_scale) > 0.01:
            return _failure(tool, "Target geometry or DPI changed during OCR observation.", "WINDOW_MOVED")
        if find:
            matches = ocr.find_words(args["visible_text_query"],
                min_confidence=args["min_confidence"], exact_match=args["exact_match"])
            region = args.get("region")
            offset_x = region["left"] if isinstance(region, dict) else region.left if region else 0
            offset_y = region["top"] if isinstance(region, dict) else region.top if region else 0
            elements = [element for element in updated.ocr_words
                if any(element.label == item.text and element.bounds == BoundingBox(
                    left=item.bounds.left + offset_x, top=item.bounds.top + offset_y,
                    right=item.bounds.right + offset_x, bottom=item.bounds.bottom + offset_y)
                    for item in matches)]
            result_data = {"snapshot_id": updated.snapshot_id, "matches": _ocr_summary(updated, elements),
                "match_count": len(elements), "raw_snapshot": updated.model_dump(mode="json")}
            message = f"Found {len(elements)} visible text matches in the target window."
        else:
            words = _ocr_summary(updated)
            result_data = {"snapshot_id": updated.snapshot_id, "visible_text": ocr.full_text,
                "words": words, "word_count": len(updated.ocr_words),
                "raw_snapshot": updated.model_dump(mode="json")}
            message = f"Read {len(updated.ocr_words)} visible text elements from the target window."
        return ToolResult.success(tool, result_data, message, verified=True,
            verify_detail=VerifyResult(ok=True, method="ocr", detail="OCR returned target-window text and bounding boxes."))
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"Target-scoped OCR read failed: {exc}", "OCR_READ_FAILED")


def execute_read_visible_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _read_ocr(args, task_context, find=False)


def execute_find_visible_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _read_ocr(args, task_context, find=True)


def execute_refresh_screen_snapshot(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "refresh_screen_snapshot"
    try:
        old = None
        if args.get("snapshot_id"):
            old = getattr(task_context, "snapshot_registry", None).get(args["snapshot_id"])
            if old is None:
                return _failure(tool, "Snapshot is not registered to this task.", "STALE_SNAPSHOT")
        hwnd = args.get("hwnd") or (old.hwnd if old else None)
        context, info, error = _resolve_window(hwnd, tool)
        if error:
            return error
        if old and (old.hwnd != info.hwnd or old.pid != info.pid
                    or old.process_creation_time_ns != context.get_process_creation_time_ns(info.pid)):
            return _failure(tool, "Snapshot target process identity changed; a new explicit target is required.", "WINDOW_MISMATCH")
        snapshot_result = _new_snapshot(info.hwnd, include_ocr=args["include_ocr"], region=None, task_context=task_context)
        snapshot = snapshot_result[0] if args["include_ocr"] else snapshot_result
        if (snapshot.hwnd != info.hwnd or snapshot.pid != info.pid
                or snapshot.process_creation_time_ns != context.get_process_creation_time_ns(info.pid)):
            return _failure(tool, "Target process identity changed during snapshot refresh.", "WINDOW_MISMATCH")
        elements = _summary(snapshot.model_copy(update={"ocr_words": []}))
        if snapshot.ocr_words:
            elements.extend(_ocr_summary(snapshot))
        return ToolResult.success(tool, {"snapshot_id": snapshot.snapshot_id, "hwnd": info.hwnd,
            "control_count": len(snapshot.controls), "ocr_word_count": len(snapshot.ocr_words),
            "elements": elements, "raw_snapshot": snapshot.model_dump(mode="json")},
            "Refreshed the target-window screen snapshot.", verified=True,
            verify_detail=VerifyResult(ok=True, method="uia_ocr" if args["include_ocr"] else "uia",
                                       detail="Fresh target identity, controls and requested text observations were captured."))
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"Screen snapshot refresh failed: {exc}", "SNAPSHOT_REFRESH_FAILED")


def execute_find_control(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "find_control"
    try:
        snap = _snapshot(args["snapshot_id"], task_context, tool)
        _check_window(snap, task_context)
        label = args.get("label")
        automation_id = args.get("automation_id")
        control_type = args.get("control_type")
        matches = []
        for item in snap.controls:
            if item.source != ElementSource.UIA:
                continue
            if label:
                actual = item.label.strip().casefold()
                expected = label.strip().casefold()
                matches_label = actual == expected if args.get("exact_match", True) else expected in actual
                if not matches_label:
                    continue
            if automation_id and item.uia_automation_id != automation_id:
                continue
            if control_type and (item.control_type or "").casefold() != control_type.casefold():
                continue
            matches.append(item)
        subset = snap.model_copy(update={"controls": matches, "ocr_words": []})
        return ToolResult.success(tool, {"snapshot_id": snap.snapshot_id, "matches": _summary(subset),
            "match_count": len(matches)}, f"Found {len(matches)} matching semantic controls.", verified=True,
            verify_detail=VerifyResult(ok=True, method="uia_snapshot", detail="The fresh task-owned snapshot was searched without invoking OCR."))
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"Semantic control lookup failed: {exc}", "CONTROL_LOOKUP_FAILED")


def _control(snapshot: ScreenSnapshot, element: ScreenElement, tool: str):
    if element.source != ElementSource.UIA:
        raise ValueError("A UI Automation element is required.")
    if not (element.uia_automation_id or element.label):
        raise ValueError("The semantic element has no stable UIA identity.")
    return {"hwnd": snapshot.hwnd, "auto_id": element.uia_automation_id,
        "name": element.label or None, "control_type": element.control_type}


def execute_read_control_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "read_control_text"
    snap, element, _, error = _target(args, task_context, tool, [ElementSource.UIA])
    if error:
        return error
    try:
        selector = _control(snap, element, tool)
        value = UiaAdapter().find_control(**selector, timeout_s=2.0)
        if not value.is_visible:
            return _failure(tool, "The target control is no longer visible.", "ELEMENT_UNAVAILABLE")
        if value.is_password is not False:
            return _failure(tool, "Password or unclassified controls cannot be read as text.", "SENSITIVE_CONTROL_REFUSED")
        if value.text_value is None:
            return _failure(tool, "The UIA provider did not expose a readable text value.", "CONTROL_TEXT_UNAVAILABLE")
        return ToolResult.success(tool, {"snapshot_id": snap.snapshot_id, "target_ref": args["target_ref"],
            "control_text": value.text_value, "control_type": value.control_type},
            "Read text from the uniquely identified UI Automation control.", verified=True,
            verify_detail=VerifyResult(ok=True, method="uia", detail="The target control value was read from UI Automation."))
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"UIA control text read failed: {exc}", "CONTROL_TEXT_READ_FAILED")


def execute_find_control_wait(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "wait_for_control"
    try:
        snap = _snapshot(args["snapshot_id"], task_context, tool)
        _check_window(snap, task_context)
        deadline = time.monotonic() + args["timeout_ms"] / 1000.0
        latest = snap
        while time.monotonic() < deadline:
            _cancel(task_context)
            latest = UiaSnapshotBuilder().capture(hwnd=snap.hwnd, ttl_seconds=_SNAPSHOT_TTL_S)
            _check_window(latest, task_context)
            criteria = {key: args.get(key) for key in ("label", "automation_id", "control_type") if args.get(key)}
            found = []
            for element in latest.controls:
                if element.source != ElementSource.UIA:
                    continue
                if criteria.get("label") and element.label.strip().casefold() != criteria["label"].strip().casefold():
                    continue
                if criteria.get("automation_id") and element.uia_automation_id != criteria["automation_id"]:
                    continue
                if criteria.get("control_type") and (element.control_type or "").casefold() != criteria["control_type"].casefold():
                    continue
                found.append(element)
            if len(found) > 1:
                return _failure(tool, f"Wait refused an ambiguous control selector ({len(found)} matches).", "UI_AMBIGUOUS_TARGET")
            if found:
                return ToolResult.success(tool, {"snapshot_id": latest.snapshot_id,
                    "target_ref": f"{latest.snapshot_id}::{found[0].element_id}",
                    "control": _summary(latest.model_copy(update={"controls": found, "ocr_words": []}))[0],
                    "raw_snapshot": latest.model_dump(mode="json")},
                    "The requested UI Automation control appeared in the target window.", verified=True,
                    verify_detail=VerifyResult(ok=True, method="uia", detail="Control presence was read from a fresh UIA snapshot."))
            time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        return _failure(tool, "The requested UI Automation control did not appear before the bounded wait expired.", "CONTROL_WAIT_TIMEOUT")
    except Exception as exc:
        if isinstance(exc, TaskCancelledError):
            raise
        return _failure(tool, f"UIA control wait failed: {exc}", "CONTROL_WAIT_FAILED")


def _invoke_uia(args: Dict[str, Any], task_context: Any, tool: str, *, expected_enabled: Optional[bool] = None) -> ToolResult:
    snap, element, _, error = _target(args, task_context, tool, [ElementSource.UIA])
    if error:
        return error
    if not isinstance(expected_enabled, bool):
        return _failure(tool, "Invocation requires an expected enabled-state transition.", "UI_POSTCONDITION_REQUIRED")
    selector = _control(snap, element, tool)
    adapter = UiaAdapter()
    try:
        before = adapter.find_control(**selector, timeout_s=2.0)
        if not before.is_visible:
            return _failure(tool, "The target UIA control is no longer visible.", "ELEMENT_UNAVAILABLE")
        if before.is_enabled is expected_enabled:
            return _failure(tool, "Invocation refused because the expected state is already present.", "UI_NO_EXPECTED_TRANSITION")
        _cancel(task_context)
        adapter.invoke_control(**selector, timeout_s=2.0)
        _cancel(task_context)
        after = adapter.find_control(**selector, timeout_s=2.0)
        ok = after.is_enabled is expected_enabled
        proof = VerifyResult(ok=ok, method="uia", detail=(
            f"Enabled state read back as {expected_enabled}." if ok else
            f"Enabled state remained {after.is_enabled}; expected {expected_enabled}."))
        return ToolResult.success(tool, {"snapshot_id": snap.snapshot_id, "target_ref": args["target_ref"],
            "hwnd": snap.hwnd, "enabled": after.is_enabled},
            "Invoked the uniquely identified UI Automation control." if ok else
            "UI Automation invocation returned, but the expected enabled-state transition was not observed.",
            verified=ok, verify_detail=proof)
    except (ElementNotFoundError, ElementUnavailableError, WindowNotFoundError) as exc:
        return _failure(tool, f"UIA invocation failed: {exc}", "CONTROL_INVOKE_FAILED")
    except Exception:
        if getattr(task_context, "cancellation_token", None) is not None and task_context.cancellation_token.is_cancelled:
            raise TaskCancelledError("Task cancelled during UIA invocation.")
        return _failure(tool, "UIA invocation failed before its state transition could be verified.", "CONTROL_INVOKE_FAILED")


def execute_invoke_control(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _invoke_uia(args, task_context, "invoke_control", expected_enabled=args.get("expected_enabled"))


def execute_invoke_screen_uia(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    snap, element, _, error = _target(args, task_context, "invoke_screen_element")
    if error:
        return error
    if element.source == ElementSource.OCR:
        from pluma.tools.base import AdapterUnavailable
        raise AdapterUnavailable("The target is OCR-grounded; use the declared OCR adapter.")
    return _invoke_uia(args, task_context, "invoke_screen_element", expected_enabled=args.get("expected_enabled"))


def execute_invoke_screen_ocr(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    snap, element, _, error = _target(args, task_context, "invoke_screen_element", [ElementSource.OCR])
    if error:
        return error
    from pluma.tools.ui import execute_click_ocr_text
    result = execute_click_ocr_text({"text": element.label, "snapshot_id": snap.snapshot_id,
        "hwnd": snap.hwnd, "min_confidence": element.confidence, "region": element.bounds.model_dump()}, task_context)
    return result.model_copy(update={"tool": "invoke_screen_element"})


def execute_invoke_screen_element(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_invoke_screen_uia(args, task_context)


def _find_live_control(snapshot: ScreenSnapshot, element: ScreenElement, tool: str):
    selector = _control(snapshot, element, tool)
    value = UiaAdapter().find_control(**selector, timeout_s=2.0)
    if not value.is_visible:
        raise ValueError("Target UIA control is no longer visible.")
    if not value.is_enabled:
        raise ValueError("Target UIA control is disabled.")
    return selector, value


def _find_live_text_control(snapshot: ScreenSnapshot, element: ScreenElement, tool: str):
    selector, value = _find_live_control(snapshot, element, tool)
    if value.is_password is not False:
        raise ValueError("Password or unclassified controls cannot be changed by a screen text tool.")
    if value.text_value is None:
        raise ValueError("The UIA provider did not expose a readable text value.")
    if value.control_type.casefold() not in {"edit", "document", "combobox"}:
        raise ValueError("Target UIA control does not support text replacement.")
    return selector, value


def _capture_text_undo(args: Dict[str, Any], task_context: Any = None) -> Dict[str, Any]:
    snap, element, info, error = _target(args, task_context, "set_control_text", [ElementSource.UIA])
    if error:
        return {}
    try:
        _, current = _find_live_text_control(snap, element, "set_control_text")
    except Exception:
        return {}
    if len(current.text_value or "") > 2048:
        return {}
    reference = str(uuid.uuid4())
    return {"action": "screen_control_text", "undo_ref": reference, "hwnd": snap.hwnd,
        "guard_version": 1, "volatile": True,
        "pid": snap.pid, "process_creation_time_ns": snap.process_creation_time_ns,
        "window_title": snap.active_window_title, "window_class": snap.window_class,
        "window_rect": snap.window_rect.model_dump(), "dpi_scale": snap.dpi_scale,
        "auto_id": element.uia_automation_id, "name": element.label,
        "control_type": element.control_type, "target_ref": args["target_ref"],
        "screen_text_private": {"before_value": current.text_value}}


def seal_screen_text_capture(state: Dict[str, Any]):
    """Separate the captured value from the durable, identity-only undo record."""
    private = state.pop("screen_text_private", None)
    if (not isinstance(private, dict) or set(private) != {"before_value"}
            or not isinstance(private["before_value"], str) or len(private["before_value"]) > 2048
            or state.get("action") != "screen_control_text" or state.get("guard_version") != 1
            or state.get("volatile") is not True):
        raise ValueError("Invalid private screen text capture.")
    reference = state.get("undo_ref")
    if not isinstance(reference, str) or str(uuid.UUID(reference)) != reference:
        raise ValueError("Invalid screen text undo reference.")
    required = {"action", "undo_ref", "guard_version", "volatile", "hwnd", "pid",
        "process_creation_time_ns", "window_title", "window_class", "window_rect",
        "dpi_scale", "auto_id", "name", "control_type", "target_ref"}
    if set(state) != required:
        raise ValueError("Screen text undo record has unexpected fields.")
    return state, private


def verify_screen_control_text(undo_data: Dict[str, Any], private: Dict[str, Any], *, restored: bool) -> bool:
    """Independently read the target control after a screen-text inverse."""
    try:
        record = {key: value for key, value in undo_data.items() if key != "screen_text_private"}
        if private.get("record") != record:
            return False
        context = ActiveWindowContext()
        info = context.get_window_info(int(record["hwnd"]))
        if (not info.is_valid or info.pid != record["pid"]
                or context.get_process_creation_time_ns(info.pid) != record["process_creation_time_ns"]
                or info.window_title != record["window_title"]
                or info.class_name != record["window_class"]
                or info.rect.model_dump() != record["window_rect"]
                or abs(info.dpi_scale - float(record["dpi_scale"])) > 0.01):
            return False
        selector = {"hwnd": info.hwnd, "auto_id": record.get("auto_id"),
            "name": record.get("name"), "control_type": record.get("control_type")}
        value = UiaAdapter().find_control(**selector, timeout_s=2.0)
        if not value.is_visible or value.is_password is not False:
            return False
        expected = private.get("before_value") if restored else private.get("after_value")
        return isinstance(expected, str) and value.text_value == expected
    except Exception:
        return False


def restore_screen_control_text(undo_data: Dict[str, Any]):
    """Restore a prior value only while the same target still has our expected text."""
    from pluma.rollback.recipes import RollbackStepResult
    try:
        private = undo_data.get("screen_text_private", {})
        reference = undo_data.get("undo_ref")
        if (private.get("record") != {key: value for key, value in undo_data.items()
                                      if key != "screen_text_private"}
                or private.get("undo_ref") != reference
                or time.monotonic() - float(private.get("created_monotonic", 0)) > SCREEN_TEXT_UNDO_TTL_S):
            raise ValueError("Private screen text pre-state is unavailable or expired.")
        # A failed/unchanged action may already be at its captured value.
        if verify_screen_control_text(undo_data, private, restored=True):
            return RollbackStepResult(True, "screen_control_text", "The target already contains its captured prior value.")
        if not verify_screen_control_text(undo_data, private, restored=False):
            raise ValueError("Target changed after the screen text action.")
        record = {key: value for key, value in undo_data.items() if key != "screen_text_private"}
        info = ActiveWindowContext().get_window_info(int(record["hwnd"]))
        adapter = UiaAdapter()
        selector = {"hwnd": info.hwnd, "auto_id": record.get("auto_id"),
                    "name": record.get("name"), "control_type": record.get("control_type")}
        adapter.set_control_text(**selector, text=private["before_value"], clear_existing=True, timeout_s=2.0)
        if not verify_screen_control_text(undo_data, private, restored=True):
            raise ValueError("Restored control text did not read back exactly.")
        return RollbackStepResult(True, "screen_control_text", "Restored and read back the previous screen-control text.")
    except Exception:
        return RollbackStepResult(False, "screen_control_text", "Screen-control text changed or could not be safely restored.", error="ROLLBACK_CONFLICT")


def execute_set_control_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "set_control_text"
    snap, element, _, error = _target(args, task_context, tool, [ElementSource.UIA])
    if error:
        return error
    try:
        selector, before = _find_live_text_control(snap, element, tool)
        private = (getattr(task_context, "execution_binding", None) or {}).get("screen_text_private")
        pending = next((item for item in reversed(getattr(task_context, "undo_stack", []))
                        if item.get("action") == "pending_mutation" and item.get("tool") == tool), None)
        if (not private or pending is None or private.get("record") != pending.get("pre_state")
                or private.get("before_value") != before.text_value):
            return _failure(tool, "Screen text pre-state could not be matched to the live control.", "UNDO_PRESTATE_MISMATCH")
        if before.text_value == args["screen_input"]:
            return _failure(tool, "Requested text is already present; no state change was made.", "NO_STATE_CHANGE")
        _cancel(task_context)
        UiaAdapter().set_control_text(**selector, text=args["screen_input"], timeout_s=2.0, clear_existing=True)
        _cancel(task_context)
        after = UiaAdapter().find_control(**selector, timeout_s=2.0)
        ok = after.text_value == args["screen_input"]
        proof = VerifyResult(ok=ok, method="uia", detail="The new control text was read back exactly." if ok else "The UIA value differs from the requested text.")
        return ToolResult.success(tool, {"snapshot_id": snap.snapshot_id, "target_ref": args["target_ref"],
            "text_length": len(args["screen_input"])}, "Set and read back text in the target UIA control." if ok
            else "Text was dispatched, but the requested value was not read back.", verified=ok, verify_detail=proof)
    except Exception:
        if getattr(task_context, "cancellation_token", None) is not None and task_context.cancellation_token.is_cancelled:
            raise TaskCancelledError("Task cancelled during UIA text update.")
        return _failure(tool, "UIA text update failed or its readback could not be verified.", "CONTROL_TEXT_SET_FAILED")


def _postcondition(args: Dict[str, Any], snap: ScreenSnapshot, element: ScreenElement, tool: str) -> VerifyResult:
    selector = _control(snap, element, tool)
    try:
        current = UiaAdapter().find_control(**selector, timeout_s=2.0)
        checks = []
        if args.get("expected_control_text") is not None:
            checks.append(current.text_value == args["expected_control_text"])
        if args.get("expected_enabled") is not None:
            checks.append(current.is_enabled is args["expected_enabled"])
        ok = bool(checks) and all(checks)
        return VerifyResult(ok=ok, method="uia", detail="The requested UIA postcondition was read back." if ok
            else "The UIA control did not match the requested postcondition.")
    except Exception:
        return VerifyResult(ok=False, method="uia", detail="The targeted UIA postcondition could not be read back.")


def _input_action(args: Dict[str, Any], task_context: Any, tool: str) -> ToolResult:
    snap, element, _, error = _target(args, task_context, tool, [ElementSource.UIA])
    if error:
        return error
    try:
        selector, current = _find_live_control(snap, element, tool)
        if tool == "type_text":
            selector, current = _find_live_text_control(snap, element, tool)
            private = (getattr(task_context, "execution_binding", None) or {}).get("screen_text_private")
            pending = next((item for item in reversed(getattr(task_context, "undo_stack", []))
                            if item.get("action") == "pending_mutation" and item.get("tool") == tool), None)
            if (not private or pending is None or private.get("record") != pending.get("pre_state")
                    or private.get("before_value") != current.text_value):
                return _failure(tool, "Screen text pre-state could not be matched to the live control.", "UNDO_PRESTATE_MISMATCH")
        adapter = UiaAdapter()
        adapter.focus_control(**selector, timeout_s=2.0)
        _cancel(task_context)
        from pluma.adapters.input import InputAdapter
        input_adapter = InputAdapter()
        if tool == "press_key":
            input_adapter.press_key(args["key"])
        elif tool == "hotkey":
            input_adapter.send_hotkey(args["modifiers"], args["key"])
        elif tool == "type_text":
            input_adapter.send_text(args["screen_input"])
        _cancel(task_context)
        proof = _postcondition(args, snap, element, tool)
        length = len(args.get("screen_input", ""))
        data = {"snapshot_id": snap.snapshot_id, "target_ref": args["target_ref"], "hwnd": snap.hwnd}
        if tool == "type_text":
            data["text_length"] = length
        data.update({"postcondition_verified": proof.ok})
        return ToolResult.success(tool, data,
            f"Sent the requested {tool.replace('_', ' ')} input to the grounded UIA control." if proof.ok
            else "Input was sent, but the requested UIA postcondition was not observed.",
            verified=proof.ok, verify_detail=proof)
    except Exception:
        if getattr(task_context, "cancellation_token", None) is not None and task_context.cancellation_token.is_cancelled:
            raise TaskCancelledError("Task cancelled during stable input.")
        return _failure(tool, "Stable input fallback failed or its target/readback was unavailable.", "INPUT_ACTION_FAILED")


def execute_press_key(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _input_action(args, task_context, "press_key")


def execute_hotkey(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _input_action(args, task_context, "hotkey")


def execute_type_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _input_action(args, task_context, "type_text")


def execute_click_window_relative(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    tool = "click_window_relative"
    snap, element, info, error = _target(args, task_context, tool, [ElementSource.OCR])
    if error:
        return error
    if not (element.bounds.left <= args["x"] < element.bounds.right
            and element.bounds.top <= args["y"] < element.bounds.bottom):
        return _failure(tool, "Window-relative coordinates must fall inside the grounded OCR target bounds.", "COORDINATES_OUT_OF_BOUNDS")
    try:
        from pluma.adapters.input import InputAdapter
        _cancel(task_context)
        # Re-run OCR against the exact target window immediately before input.
        from pluma.perception.capture import WindowCapture
        from pluma.perception.ocr_lifecycle import get_default_ocr_lifecycle_manager
        image = WindowCapture().capture_window(info.hwnd)
        current = get_default_ocr_lifecycle_manager().run_ocr(
            image, cancellation_token=getattr(task_context, "cancellation_token", None))
        image = None
        matches = [word for word in current.find_words(element.label, min_confidence=args["min_confidence"], exact_match=True)
                   if _bounds_overlap(element.bounds, word.bounds) >= 0.5]
        if len(matches) != 1:
            return _failure(tool, "OCR target is absent, ambiguous or moved since its snapshot.", "OCR_TARGET_STALE")
        _, fresh_element, live, freshness_error = _target(args, task_context, tool, [ElementSource.OCR])
        if freshness_error:
            return freshness_error
        if fresh_element.element_id != element.element_id:
            return _failure(tool, "OCR target reference changed before input.", "OCR_TARGET_STALE")
        fresh_word = matches[0]
        if not (fresh_word.bounds.left <= args["x"] < fresh_word.bounds.right
                and fresh_word.bounds.top <= args["y"] < fresh_word.bounds.bottom):
            return _failure(tool, "Window-relative point no longer falls inside the refreshed OCR target.", "OCR_TARGET_STALE")
        _cancel(task_context)
        InputAdapter().mouse_click(live.rect.left + args["x"], live.rect.top + args["y"])
        _cancel(task_context)
        time.sleep(0.2)
        _cancel(task_context)
        after_image = WindowCapture().capture_window(info.hwnd)
        try:
            after = get_default_ocr_lifecycle_manager().run_ocr(after_image,
                cancellation_token=getattr(task_context, "cancellation_token", None))
        finally:
            after_image = None
        still_here = any(word.text.strip().casefold() == element.label.strip().casefold()
            and _bounds_overlap(element.bounds, word.bounds) >= 0.5 for word in after.words)
        proof = VerifyResult(ok=not still_here, method="ocr_target_transition",
            detail="Target text disappeared or moved after the click." if not still_here
            else "The OCR target remains at its original location; transition was not verified.")
        return ToolResult.success(tool, {"snapshot_id": snap.snapshot_id, "target_ref": args["target_ref"],
            "hwnd": info.hwnd, "x": args["x"], "y": args["y"]},
            "Clicked the fresh OCR-grounded window-relative target." if proof.ok
            else "Click was dispatched, but the expected OCR target transition was not observed.",
            verified=proof.ok, verify_detail=proof)
    except Exception:
        if getattr(task_context, "cancellation_token", None) is not None and task_context.cancellation_token.is_cancelled:
            raise TaskCancelledError("Task cancelled during window-relative input.")
        return _failure(tool, "Window-relative OCR input failed or its transition could not be verified.", "WINDOW_RELATIVE_CLICK_FAILED")


def _bounds_overlap(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    smaller = min(first.width * first.height, second.width * second.height)
    return intersection / smaller if smaller else 0.0


def _verified(result: ToolResult) -> VerifyResult:
    if result.ok and result.verified:
        return result.verify_detail if isinstance(result.verify_detail, VerifyResult) else VerifyResult(
            ok=True, method="executor_readback", detail="The screen-tool postcondition was read back.")
    return VerifyResult(ok=False, method="executor_readback", detail=result.error or "Screen-tool postcondition failed.")


def _intent(args: Dict[str, Any], task_context: Any = None, *, tool_name: str) -> Dict[str, Any]:
    return {"non_undoable": True, "action": "pending_mutation", "tool": tool_name,
            "snapshot_id": args.get("snapshot_id"), "target_ref": args.get("target_ref")}


def _spec(name: str, description: str, schema: Any, priority: AdapterPriority,
          executor, *, risk: RiskClass = RiskClass.READ, timeout: float = 5.0,
          verifier=verify_noop, undo_builder=None, process_isolated: bool = True,
          non_undoable: bool = False) -> ToolSpec:
    return ToolSpec(name=name, description=description, args_schema=schema, risk_class=risk,
        timeout_s=timeout, process_isolated=process_isolated,
        executor=AdapterDispatcher(name, {priority: executor}), verifier=verifier,
        undo_builder=undo_builder, non_undoable=non_undoable,
        adapter_priority=[priority], cancellable=True)


GET_ACTIVE_WINDOW_CONTEXT_SPEC = _spec("get_active_window_context", "Read the active window identity, process, geometry and DPI.",
    _NoArgs, AdapterPriority.NATIVE_API, execute_get_active_window_context, process_isolated=False)
INSPECT_WINDOW_CONTROLS_SPEC = _spec("inspect_window_controls", "Inspect semantic UI Automation controls in a target window.",
    InspectWindowControlsArgs, AdapterPriority.UIA, execute_inspect_window_controls)
CAPTURE_TARGET_WINDOW_SPEC = _spec("capture_target_window", "Capture only a fresh target window or its in-window region; discard image bytes after use.",
    CaptureTargetWindowArgs, AdapterPriority.NATIVE_API, execute_capture_target_window, timeout=5.0)
READ_VISIBLE_TEXT_SPEC = _spec("read_visible_text", "Read visible text and bounds from a target-window OCR pass.",
    ReadVisibleTextArgs, AdapterPriority.OCR_GROUNDED, execute_read_visible_text, timeout=12.0)
FIND_VISIBLE_TEXT_SPEC = _spec("find_visible_text", "Find visible text in a target-window OCR pass and return grounded references.",
    FindVisibleTextArgs, AdapterPriority.OCR_GROUNDED, execute_find_visible_text, timeout=12.0)
REFRESH_SCREEN_SNAPSHOT_SPEC = _spec("refresh_screen_snapshot", "Re-observe a target window and create a fresh task-scoped screen snapshot.",
    RefreshScreenSnapshotArgs, AdapterPriority.UIA, execute_refresh_screen_snapshot, timeout=12.0)
FIND_CONTROL_SPEC = _spec("find_control", "Find semantic UI Automation controls in a fresh task snapshot without OCR.",
    FindControlArgs, AdapterPriority.UIA, execute_find_control)
INVOKE_CONTROL_SPEC = _spec("invoke_control", "Invoke one unique semantic UIA control and read back its enabled-state transition.",
    InvokeControlArgs, AdapterPriority.UIA, execute_invoke_control, risk=RiskClass.HIGH,
    verifier=_verified, undo_builder=partial(_intent, tool_name="invoke_control"), non_undoable=True)
SET_CONTROL_TEXT_SPEC = _spec("set_control_text", "Set text in a uniquely identified editable UIA control and verify the readback.",
    SetControlTextArgs, AdapterPriority.UIA, execute_set_control_text, risk=RiskClass.MEDIUM,
    verifier=_verified, undo_builder=_capture_text_undo)
READ_CONTROL_TEXT_SPEC = _spec("read_control_text", "Read text from a unique non-password UIA control.",
    ReadControlTextArgs, AdapterPriority.UIA, execute_read_control_text)
WAIT_FOR_CONTROL_SPEC = _spec("wait_for_control", "Wait a bounded time for one unique UIA control to appear.",
    WaitForControlArgs, AdapterPriority.UIA, execute_find_control_wait, timeout=4.0)
INVOKE_SCREEN_ELEMENT_SPEC = ToolSpec(name="invoke_screen_element",
    description="Invoke a grounded UIA element or use OCR-grounded input when UIA cannot address it.",
    args_schema=InvokeScreenElementArgs, risk_class=RiskClass.HIGH, timeout_s=12.0,
    process_isolated=True, executor=AdapterDispatcher("invoke_screen_element", {
        AdapterPriority.UIA: execute_invoke_screen_uia,
        AdapterPriority.OCR_GROUNDED: execute_invoke_screen_ocr,
    }), verifier=_verified, undo_builder=partial(_intent, tool_name="invoke_screen_element"),
    non_undoable=True, adapter_priority=[AdapterPriority.UIA, AdapterPriority.OCR_GROUNDED], cancellable=True)
PRESS_KEY_SPEC = _spec("press_key", "Send one supported key to a grounded UIA control and verify a requested state.",
    PressKeyArgs, AdapterPriority.KEYBOARD, execute_press_key, risk=RiskClass.HIGH, verifier=_verified,
    undo_builder=partial(_intent, tool_name="press_key"), non_undoable=True)
HOTKEY_SPEC = _spec("hotkey", "Send a supported modifier chord to a grounded UIA control and verify a requested state.",
    HotkeyArgs, AdapterPriority.KEYBOARD, execute_hotkey, risk=RiskClass.HIGH, verifier=_verified,
    undo_builder=partial(_intent, tool_name="hotkey"), non_undoable=True)
TYPE_TEXT_SPEC = _spec("type_text", "Type text into a grounded, non-password UIA control and verify the requested value.",
    TypeTextArgs, AdapterPriority.KEYBOARD, execute_type_text, risk=RiskClass.MEDIUM, verifier=_verified,
    undo_builder=_capture_text_undo)
CLICK_WINDOW_RELATIVE_SPEC = _spec("click_window_relative", "Click a point inside a fresh OCR target in window-relative coordinates and verify its transition.",
    ClickWindowRelativeArgs, AdapterPriority.OCR_GROUNDED, execute_click_window_relative,
    risk=RiskClass.HIGH, timeout=12.0, verifier=_verified,
    undo_builder=partial(_intent, tool_name="click_window_relative"), non_undoable=True)

SCREEN_CONTROL_TOOLS: List[ToolSpec] = [
    GET_ACTIVE_WINDOW_CONTEXT_SPEC, INSPECT_WINDOW_CONTROLS_SPEC, CAPTURE_TARGET_WINDOW_SPEC,
    READ_VISIBLE_TEXT_SPEC, FIND_VISIBLE_TEXT_SPEC, REFRESH_SCREEN_SNAPSHOT_SPEC,
    FIND_CONTROL_SPEC, INVOKE_CONTROL_SPEC, SET_CONTROL_TEXT_SPEC, READ_CONTROL_TEXT_SPEC,
    WAIT_FOR_CONTROL_SPEC, INVOKE_SCREEN_ELEMENT_SPEC, PRESS_KEY_SPEC, HOTKEY_SPEC,
    TYPE_TEXT_SPEC, CLICK_WINDOW_RELATIVE_SPEC,
]


__all__ = ["SCREEN_CONTROL_TOOLS", "restore_screen_control_text"]
