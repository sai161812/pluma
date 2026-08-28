"""tests.unit.test_phase13_7_fail_closed_permissions — Verify ToolSubsetSelector fail-closed."""

from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core.router import RouteMode

def test_permissions_fail_closed_on_invalid_route():
    # An invalid route string should throw an exception in Enum casting,
    # which must be caught and return False, not True.
    assert ToolSubsetSelector.is_tool_permitted("open_app", "INVALID_ROUTE_123") is False

def test_fast_route_forbids_tools():
    assert ToolSubsetSelector.is_tool_permitted("open_app", RouteMode.FAST) is False
