"""pluma.brain.tool_subset — Route-specific tool schema selector.

Spec §10: "Never provide the model with ... all tool schemas by default.
Tool schema selection should be route-specific."
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Sequence, Union

from pluma.brain.schemas import RouteMode
from pluma.tools.base import ToolSpec
from pluma.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

# Standard tool groupings
FILE_TOOLS = [
    "open_file",
    "safe_delete",
    "copy_file",
    "list_folder",
    "file_info",
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
    "get_active_window_context",
    "inspect_window_controls",
    "capture_target_window",
    "read_visible_text",
    "find_visible_text",
    "refresh_screen_snapshot",
    "find_control",
    "invoke_control",
    "set_control_text",
    "read_control_text",
    "wait_for_control",
    "invoke_screen_element",
    "press_key",
    "hotkey",
    "type_text",
    "click_window_relative",
]

AUDIO_TOOLS = [
    "set_default_audio_device",
    "get_volume",
    "list_audio_devices",
    "get_volume_status",
    "set_volume",
    "mute",
    "unmute",
    "mute_audio",
    "unmute_audio",
]

WINDOW_MANAGEMENT_TOOLS = [
    "move_window",
    "resize_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "close_window",
    "list_windows",
    "focus_window",
]

SYSTEM_CLIPBOARD_TOOLS = [
    'clipboard_get', 'clipboard_set',
    'lock', 'sleep_request', 'restart_request', 'shutdown_request',
    "save_preference", "get_preference", "create_routine", "run_routine",
    "get_system_status",
    "system_status",
    "battery_status",
    "network_status",
    "clear_clipboard",
    "clipboard_clear",
    "get_clipboard_text",
    "set_clipboard_text",
    "clipboard_read",
    "clipboard_write",
    "show_activity",
    "undo_last",
    "stop_current",
    "list_processes",
    "process_info",
    "process_usage",
    "graceful_close_process",
    "terminate_process",
    "get_process_status",
    "kill_process",
]

# Route to standard tool name mappings
TERMINAL_TOOLS = ['run_command', 'run_powershell', 'run_project_command', 'open_terminal']
BROWSER_TOOLS = ['open_url', 'list_tabs', 'focus_tab', 'close_tab', 'download_status']
ROUTE_TOOL_MAP: Dict[RouteMode, List[str]] = {
    RouteMode.FAST: [],  # FAST route bypasses LLM planning entirely
    RouteMode.SMART: FILE_TOOLS + APP_WINDOW_TOOLS + WINDOW_MANAGEMENT_TOOLS + AUDIO_TOOLS + SYSTEM_CLIPBOARD_TOOLS + TERMINAL_TOOLS + BROWSER_TOOLS,
    RouteMode.SCREEN: UI_PERCEPTION_TOOLS + WINDOW_MANAGEMENT_TOOLS,
    RouteMode.DEEP: (
        FILE_TOOLS
        + APP_WINDOW_TOOLS
        + WINDOW_MANAGEMENT_TOOLS
        + UI_PERCEPTION_TOOLS
        + AUDIO_TOOLS
        + SYSTEM_CLIPBOARD_TOOLS
        + TERMINAL_TOOLS
        + BROWSER_TOOLS
    ),
}


class ToolSubsetSelector:
    """Selects route-appropriate tool schemas to prevent token bloat and hallucination."""

    @staticmethod
    def is_tool_permitted(tool_name: str, route: Union[RouteMode, str]) -> bool:
        """Return True if tool_name is permitted for execution in the given route."""
        try:
            route_enum = route if isinstance(route, RouteMode) else RouteMode(str(route).upper())
            permitted = ROUTE_TOOL_MAP.get(route_enum, [])
            return tool_name in permitted
        except Exception:
            return False

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
            if any(k in cmd_lower for k in ("routine", "preference", "remember")):
                return base_names
            if any(k in cmd_lower for k in ('terminal', 'powershell', 'diagnostic', 'project command')):
                return TERMINAL_TOOLS
            explicit_browser_context = re.search(
                r"\b(?:browser|website|web\s+site|webpage|web\s+page|web|url|tab)\b|https?://|www\.",
                cmd_lower,
            )
            if explicit_browser_context:
                return BROWSER_TOOLS
            file_operation_hint = any(
                k in cmd_lower for k in ("file", "folder", "directory", "move", "rename")
            ) or bool(re.search(r"\bdownloads\b", cmd_lower))
            file_type_hint = any(k in cmd_lower for k in ("pdf", "doc"))
            if file_operation_hint or file_type_hint:
                return FILE_TOOLS + (SYSTEM_CLIPBOARD_TOOLS if "clipboard" in cmd_lower else [])
            if re.search(r"\bdownload(?:s|ed|ing)?\b", cmd_lower):
                return BROWSER_TOOLS
            # If purely clipboard task
            if any(k in cmd_lower for k in ("clipboard", "copy", "paste")):
                return SYSTEM_CLIPBOARD_TOOLS + APP_WINDOW_TOOLS

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

    # Aliases for caller compatibility
    select_schemas_for_route = select_schemas
    get_schemas_for_route = select_schemas

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
