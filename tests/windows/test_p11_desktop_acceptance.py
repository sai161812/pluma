"""Interactive P11 acceptance; run on an unlocked foreground desktop.

This is intentionally an assertion, never a skip or an inert desktop substitute.
The 2026-10-25 noninteractive attempt failed NO_ACTIVE_WINDOW; it is not a pass.
"""
from pluma.tools.registry import ToolRegistry
from pluma.tools.ui import INSPECT_ACTIVE_WINDOW_SPEC


def test_native_production_inspection_reads_foreground_without_uia():
    registry = ToolRegistry()
    registry.register(INSPECT_ACTIVE_WINDOW_SPEC)
    try:
        result = registry.execute("inspect_active_window", {"include_controls": False})
    finally:
        registry.close()
    assert result.ok and result.verified
    assert result.adapter_used == "native_api"
    assert result.data["hwnd"] > 0 and result.data["controls"] == []
