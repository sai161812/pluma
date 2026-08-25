"""pluma.brain.tool_subset — Route-specific tool schema selector.

Spec §10: "Never provide the model with ... all tool schemas by default.
Tool schema selection should be route-specific."
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Union

from pluma.brain.schemas import RouteMode
from pluma.tools.base import ToolSpec
from pluma.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Standard tool groupings
FILE_TOOLS = [
    "list_files",
    "find_file",
    "move_file",
    "rename_file",
    "create_folder",
]

APP_WINDOW_TOOLS = [
    "open_app",
    "close_app",
    "focus_app",
    "list_apps",
    "app_status",
    "list_windows",
    "focus_window",
]

UI_PERCEPTION_TOOLS = [
    "inspect_active_window",
    "click_element",
    "type_into_element",
    "click_ocr_text",
]

SYSTEM_CLIPBOARD_TOOLS = [
    "system_status",
    "battery_status",
    "clear_clipboard",
    "clipboard_read",
    "clipboard_write",
    "show_activity",
    "undo_last",
]

# Route to standard tool name mappings
ROUTE_TOOL_MAP: Dict[RouteMode, List[str]] = {
    RouteMode.FAST: [],  # FAST route bypasses LLM entirely
    RouteMode.SMART: FILE_TOOLS + APP_WINDOW_TOOLS + SYSTEM_CLIPBOARD_TOOLS,
    RouteMode.SCREEN: UI_PERCEPTION_TOOLS + ["focus_window", "list_windows"],
    RouteMode.DEEP: (
        FILE_TOOLS
        + APP_WINDOW_TOOLS
        + UI_PERCEPTION_TOOLS
        + SYSTEM_CLIPBOARD_TOOLS
    ),
}


class ToolSubsetSelector:
    """Selects route-appropriate tool schemas to prevent token bloat and hallucination."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self._registry = registry

    def get_tool_names_for_route(
        self,
        route: Union[RouteMode, str],
        command: Optional[str] = None,
    ) -> List[str]:
        """Return the list of tool names permitted for the given route and command."""
        route_enum = route if isinstance(route, RouteMode) else RouteMode(str(route).upper())
        base_names = list(ROUTE_TOOL_MAP.get(route_enum, []))

        # If command hints at specific domain in SMART route, can prioritize or trim
        if route_enum == RouteMode.SMART and command:
            cmd_lower = command.lower()
            # If purely clipboard task
            if any(k in cmd_lower for k in ("clipboard", "copy", "paste")):
                return SYSTEM_CLIPBOARD_TOOLS + APP_WINDOW_TOOLS
            # If purely file task
            if any(k in cmd_lower for k in ("file", "folder", "directory", "move", "rename", "pdf", "doc")):
                return FILE_TOOLS + ["open_app", "focus_window"]

        return base_names

    def select_schemas(
        self,
        route: Union[RouteMode, str],
        registry: Optional[ToolRegistry] = None,
        command: Optional[str] = None,
        explicit_tool_names: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Extract tool schema dictionaries for the permitted tool subset."""
        target_registry = registry or self._registry
        if target_registry is None:
            raise ValueError("A ToolRegistry must be provided to extract tool schemas.")

        if explicit_tool_names is not None:
            tool_names = list(explicit_tool_names)
        else:
            tool_names = self.get_tool_names_for_route(route, command=command)

        # Filter against what actually exists in registry
        available_names = [n for n in tool_names if target_registry.contains(n)]
        return target_registry.schema_for_planner(available_names)

    # Alias for caller compatibility
    select_schemas_for_route = select_schemas

    @staticmethod
    def format_tools_for_prompt(schemas: List[Dict[str, Any]]) -> str:
        """Format tool schemas into a concise, token-efficient text description for LLM prompts."""
        lines = []
        for s in schemas:
            name = s["name"]
            desc = s.get("description", "")
            args_schema = s.get("args_schema", {})
            props = args_schema.get("properties", {})
            req = args_schema.get("required", [])

            arg_parts = []
            for prop_name, prop_def in props.items():
                ptype = prop_def.get("type", "any")
                is_req = "*" if prop_name in req else ""
                pdesc = prop_def.get("description", "")
                desc_str = f" ({pdesc})" if pdesc else ""
                arg_parts.append(f"{prop_name}{is_req}: {ptype}{desc_str}")

            args_str = ", ".join(arg_parts) if arg_parts else "none"
            lines.append(f"- {name}({args_str}): {desc}")

        return "\n".join(lines)

    # Alias for caller compatibility
    format_schemas_for_prompt = format_tools_for_prompt
