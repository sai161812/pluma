"""tests/unit/test_brain_tool_subset.py — Phase 9: ToolSubsetSelector unit tests."""

from __future__ import annotations

import pytest

from pluma.brain.schemas import RouteMode
from pluma.brain.tool_subset import (
    FILE_TOOLS,
    ROUTE_TOOL_MAP,
    SYSTEM_CLIPBOARD_TOOLS,
    UI_PERCEPTION_TOOLS,
    ToolSubsetSelector,
)
from pluma.tools.registry import get_default_tool_registry


def test_tool_subset_fast_route_empty() -> None:
    selector = ToolSubsetSelector()
    names = selector.get_tool_names_for_route(RouteMode.FAST)
    assert names == [], "FAST route must not provide tools for LLM planning"


def test_tool_subset_smart_route_default() -> None:
    selector = ToolSubsetSelector()
    names = selector.get_tool_names_for_route(RouteMode.SMART)
    assert "list_files" in names
    assert "open_app" in names
    assert "clipboard_read" in names
    # Perception tools should NOT be in SMART by default
    assert "inspect_active_window" not in names


def test_tool_subset_screen_route() -> None:
    selector = ToolSubsetSelector()
    names = selector.get_tool_names_for_route(RouteMode.SCREEN)
    assert "inspect_active_window" in names
    assert "click_element" in names
    assert "type_into_element" in names
    assert "click_ocr_text" in names
    assert "list_files" not in names


def test_tool_subset_deep_route() -> None:
    selector = ToolSubsetSelector()
    names = selector.get_tool_names_for_route(RouteMode.DEEP)
    assert "list_files" in names
    assert "click_element" in names
    assert "open_app" in names


def test_select_schemas_from_registry() -> None:
    registry = get_default_tool_registry()
    selector = ToolSubsetSelector(registry=registry)

    schemas = selector.select_schemas(RouteMode.SCREEN)
    schema_names = [s["name"] for s in schemas]

    assert "click_element" in schema_names
    assert "click_ocr_text" in schema_names
    assert "list_files" not in schema_names


def test_format_tools_for_prompt() -> None:
    selector = ToolSubsetSelector()
    mock_schemas = [
        {
            "name": "move_file",
            "description": "Move a file from source to destination.",
            "args_schema": {
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Dest path"},
                },
                "required": ["source", "destination"],
            },
        }
    ]

    formatted = selector.format_tools_for_prompt(mock_schemas)
    assert "- move_file(" in formatted
    assert "source*" in formatted
    assert "destination*" in formatted
    assert "Move a file from source to destination." in formatted
