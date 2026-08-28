"""tests.unit.test_phase13_7_ocr_grounding — Verify UI action freshness and identity rejection."""

import pytest
from pluma.tools.ui import execute_click_element, execute_type_into_element
from pluma.tools.base import ToolResult
from dataclasses import dataclass
from pluma.perception.element_refs import BoundingBox

@dataclass
class MockActiveWindow:
    is_valid: bool = True
    hwnd: int = 1234
    pid: int = 5678
    dpi_scale: float = 1.0
    rect: BoundingBox = BoundingBox(left=100, top=100, right=500, bottom=500)

class MockTaskContext:
    grounded_ui_target = {
        "snapshot_hwnd": 1234,
        "snapshot_pid": 5678,
        "snapshot_creation_time_ns": 999999,
        "snapshot_dpi_scale": 1.0,
        "snapshot_rect_left": 100,
        "snapshot_rect_top": 100,
        "snapshot_rect_right": 500,
        "snapshot_rect_bottom": 500,
        "auto_id": "btn1",
        "name": "Submit",
        "control_type": "Button",
    }

def test_moved_window_rejected(monkeypatch):
    """Verify that if the window moved > 20px, click_element aborts."""
    
    # Mock ActiveWindowContext
    class FakeContext:
        def get_active_window(self):
            # Window moved by 50px
            return MockActiveWindow(rect=BoundingBox(left=150, top=100, right=550, bottom=500))
        def get_process_creation_time_ns(self, pid):
            return 999999
            
    import pluma.tools.ui
    monkeypatch.setattr(pluma.tools.ui, "ActiveWindowContext", FakeContext)
    
    args = {"snapshot_id": "snap-1", "target_ref": "snap-1::btn1"}
    ctx = MockTaskContext()
    
    res = execute_click_element(args, ctx)
    assert res.ok is False
    assert res.error == "WINDOW_MOVED"

def test_changed_hwnd_rejected(monkeypatch):
    """Verify HWND change is rejected."""
    class FakeContext:
        def get_active_window(self):
            return MockActiveWindow(hwnd=9999) # Different HWND
        def get_process_creation_time_ns(self, pid):
            return 999999
            
    import pluma.tools.ui
    monkeypatch.setattr(pluma.tools.ui, "ActiveWindowContext", FakeContext)
    
    args = {"snapshot_id": "snap-1", "target_ref": "snap-1::btn1"}
    ctx = MockTaskContext()
    
    res = execute_click_element(args, ctx)
    assert res.ok is False
    assert res.error == "WINDOW_MISMATCH"

