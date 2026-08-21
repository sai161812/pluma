"""tests.unit.test_tools_windows — Unit and verification tests for Window tools."""

import pytest

from pluma.tools.windows import (
    execute_focus_window,
    execute_list_windows,
)
from pluma.tools.registry import ToolRegistry, register_default_tools


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_list_windows() -> None:
    res = execute_list_windows({"visible_only": True})
    assert res.ok is True
    assert res.verified is True
    assert "windows" in res.data
    assert isinstance(res.data["windows"], list)


def test_focus_window_argument_validation(registry: ToolRegistry) -> None:
    # Must fail if neither hwnd nor title is provided
    from pluma.tools.registry import ToolArgumentError
    with pytest.raises(ToolArgumentError):
        registry.validate_call("focus_window", {})
