"""pluma.tools.apps — Application lifecycle and management tools.

Spec §11, §12, §14: Application tools as registered ToolSpecs.
Applications launch from an owned parent service into a separately owned Job,
so successful task cleanup can preserve the explicitly opened instance.

Boundary: No heavy automation libraries imported at module level.
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from pluma.core.task_supervisor import ResourceOwnership
from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.app_observations import ListAppWindowsArgs, execute_list, execute_status, verify_list, verify_status
from pluma.tools.processes import ProcessTargetArgs
from pluma.tools.app_lifecycle import CloseAppArgs, capture_close
from pluma.tools import app_launch as launch
from pluma.tools.app_launch import OpenAppArgs
from pluma.tools import window_focus as focus
from pluma.tools.window_focus import FocusAppArgs
from functools import partial
from pluma.verify.common import (
    verify_noop,
    verify_process_closed,
    verify_process_running,
    verify_window_focused,
)


class ListAppsArgs(ListAppWindowsArgs):
    """Arguments for list_apps."""


class AppStatusArgs(ProcessTargetArgs):
    """Arguments for app_status."""


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_open_app(args, task_context=None):
    return launch.execute(args, task_context)


def execute_close_app(args, task_context=None):
    from pluma.tools.app_lifecycle import execute_close
    return execute_close(args, task_context)


def execute_focus_app(args, task_context=None):
    return focus.execute(args, task_context, tool='focus_app')


def execute_list_apps(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_list(args, task_context, apps=True)


def execute_app_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_status(args, task_context)


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def verify_open_app(result):
    return launch.verify(result)


def verify_close_app(result):
    from pluma.tools.app_lifecycle import verify_close
    return verify_close(result)


def verify_focus_app(result):
    return focus.verify(result)


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

APP_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="open_app",
        description="Launch an application through a closed native alias with owned process/window readback.",
        args_schema=OpenAppArgs,
        risk_class=RiskClass.LOW,
        timeout_s=10.0,
        executor=execute_open_app,
        verifier=verify_open_app,
        undo_builder=launch.capture,
        execution_scope="task_service",
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
        creates_resources=True,
    ),
    ToolSpec(
        name="close_app",
        description="Close a running application gracefully.",
        args_schema=CloseAppArgs,
        risk_class=RiskClass.MEDIUM,
        timeout_s=10.0,
        executor=execute_close_app,
        verifier=verify_close_app,
        undo_builder=capture_close,
        non_undoable=True,
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="focus_app",
        description="Bring a running application window to the foreground.",
        args_schema=FocusAppArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_focus_app,
        verifier=verify_focus_app,
        undo_builder=partial(focus.capture, tool="focus_app"),
        process_isolated=True,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="list_apps",
        description="List running user applications.",
        args_schema=ListAppsArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_list_apps,
        verifier=verify_list,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="app_status",
        description="Query the running status of a specific application.",
        args_schema=AppStatusArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_app_status,
        verifier=verify_status,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]
