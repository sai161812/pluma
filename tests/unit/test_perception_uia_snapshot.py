"""tests/unit/test_perception_uia_snapshot.py — Phase 7: UiaSnapshotBuilder unit tests."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock
import pytest

from pluma.adapters.base import WindowNotFoundError
from pluma.perception.context import ActiveWindowContext, ActiveWindowInfo
from pluma.perception.element_refs import BoundingBox, ElementSource, ScreenElement, ScreenSnapshot
from pluma.perception.uia_snapshot import UiaSnapshotBuilder


def test_pywinauto_not_imported_at_module_level() -> None:
    """Verify that importing perception modules does NOT import pywinauto."""
    import pluma.perception.uia_snapshot
    import pluma.perception.context
    assert "pywinauto" not in sys.modules, "pywinauto must not be imported at module level"


def test_uia_snapshot_builder_with_custom_extractor() -> None:
    mock_context = MagicMock(spec=ActiveWindowContext)
    mock_context.get_active_window.return_value = ActiveWindowInfo(
        hwnd=54321,
        process_name="calc.exe",
        window_title="Calculator",
        rect=BoundingBox(left=200, top=150, right=800, bottom=750),
        dpi_scale=1.0,
        is_valid=True,
        pid=1234,
        class_name="ApplicationFrameWindow",
    )

    def custom_extractor(hwnd: int) -> list:
        return [
            {
                "label": "One",
                "control_type": "Button",
                "uia_automation_id": "num1Button",
                "bounds": {"left": 50, "top": 100, "right": 120, "bottom": 150},
                "invocation_capability": "invoke",
            },
            {
                "label": "Display",
                "control_type": "Edit",
                "uia_automation_id": "CalculatorResults",
                "bounds": {"left": 50, "top": 20, "right": 350, "bottom": 80},
                "invocation_capability": "set_value",
            },
        ]

    builder = UiaSnapshotBuilder(context=mock_context, custom_extractor=custom_extractor)
    snapshot = builder.capture(hwnd=None, ttl_seconds=3.0)

    assert isinstance(snapshot, ScreenSnapshot)
    assert snapshot.active_process == "calc.exe"
    assert snapshot.active_window_title == "Calculator"
    assert len(snapshot.controls) == 2

    c1 = snapshot.controls[0]
    assert c1.label == "One"
    assert c1.control_type == "Button"
    assert c1.uia_automation_id == "num1Button"
    assert c1.invocation_capability == "invoke"
    assert c1.source == ElementSource.UIA
    assert c1.confidence == 1.0
    assert c1.bounds.left == 50
    assert c1.bounds.width == 70

    c2 = snapshot.controls[1]
    assert c2.label == "Display"
    assert c2.control_type == "Edit"
    assert c2.invocation_capability == "set_value"

    # Find element by id
    found = snapshot.find_element(c1.element_id)
    assert found == c1


def test_uia_snapshot_builder_no_active_window_raises_error() -> None:
    mock_context = MagicMock(spec=ActiveWindowContext)
    mock_context.get_active_window.return_value = ActiveWindowInfo(is_valid=False)

    builder = UiaSnapshotBuilder(context=mock_context)
    with pytest.raises(WindowNotFoundError, match="No active foreground window found"):
        builder.capture(hwnd=None)
