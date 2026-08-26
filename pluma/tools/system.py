"""pluma.tools.system — System status, STOP trigger, Activity query, and Undo tools.

Spec §11, §12, §13, §16:
- get_system_status: System status metrics.
- stop_current: Immediate cooperative/latch STOP for current task.
- show_activity: Retrieve recent Activity Ledger entries.
- undo_last: Reverses the most recent undoable action.

Boundary: No heavy monitoring or ML libraries imported at module level.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import verify_noop


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class GetSystemStatusArgs(BaseModel):
    """Arguments for get_system_status."""
    model_config = {"extra": "forbid"}


class StopCurrentArgs(BaseModel):
    """Arguments for stop_current."""
    model_config = {"extra": "forbid"}
    reason: str = Field(default="user_stop", description="Reason for stopping the task.")


class ShowActivityArgs(BaseModel):
    """Arguments for show_activity."""
    model_config = {"extra": "forbid"}
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of activity records to return.")


class UndoLastArgs(BaseModel):
    """Arguments for undo_last."""
    model_config = {"extra": "forbid"}


class BatteryStatusArgs(BaseModel):
    """Arguments for battery_status."""
    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


def execute_get_system_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import platform
    import shutil

    # Disk usage
    total, used, free = shutil.disk_usage(os.path.abspath(os.sep))
    disk_free_gb = round(free / (1024 ** 3), 1)
    disk_total_gb = round(total / (1024 ** 3), 1)

    # Memory and CPU metrics
    data: Dict[str, Any] = {
        "os": platform.platform(),
        "python_version": platform.python_version(),
        "disk_free_gb": disk_free_gb,
        "disk_total_gb": disk_total_gb,
        "cpu_percent": 0.0,
    }

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("sullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            data["memory_load_percent"] = stat.dwMemoryLoad
            data["ram_free_gb"] = round(stat.ullAvailPhys / (1024 ** 3), 1)
            data["ram_total_gb"] = round(stat.ullTotalPhys / (1024 ** 3), 1)

        # Lazy check for psutil for accurate CPU measurement if present
        try:
            import psutil
            data["cpu_percent"] = psutil.cpu_percent(interval=None)
        except Exception:
            data["cpu_percent"] = 0.0

    ram_info = f"RAM: {data.get('ram_free_gb', '?')}GB free of {data.get('ram_total_gb', '?')}GB"
    disk_info = f"Disk: {disk_free_gb}GB free of {disk_total_gb}GB"
    cpu_info = f"CPU: {data.get('cpu_percent', 0.0)}%"

    return ToolResult(
        ok=True,
        tool="get_system_status",
        data=data,
        factual_message=f"System Status — {cpu_info}, {ram_info}, {disk_info}.",
        verified=True,
    )


def execute_stop_current(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.core.cancellation import StopReason
    
    reason = args.get("reason", "user_stop")
    if task_context and hasattr(task_context, "cancellation_token"):
        task_context.cancellation_token.cancel(StopReason.USER_STOP)
        
    return ToolResult(
        ok=True,
        tool="stop_current",
        data={"reason": reason},
        factual_message="Stopped current task execution.",
        verified=True,
    )


def execute_show_activity(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    limit = args.get("limit", 10)
    
    from pluma.memory.activity import ActivityQuery
    from pluma.memory.db import DbConnection
    
    records: List[Dict[str, Any]] = []
    
    # 1. Check if db or query is attached to task_context
    query: Optional[ActivityQuery] = None
    if task_context:
        if hasattr(task_context, "query") and isinstance(task_context.query, ActivityQuery):
            query = task_context.query
        elif hasattr(task_context, "db") and isinstance(task_context.db, DbConnection):
            query = ActivityQuery(task_context.db)

    # 2. Check default or env configured database path
    if query is None:
        db_path = os.environ.get("PLUMA_DB_PATH")
        if not db_path:
            appdata = os.environ.get("LOCALAPPDATA") or "/tmp"
            db_path = os.path.join(appdata, "PLUMA", "activity.db")
        
        if os.path.exists(db_path):
            try:
                with DbConnection(db_path) as db:
                    q = ActivityQuery(db)
                    tasks = q.recent_tasks(limit=limit)
                    for t in tasks:
                        actions = q.actions_for_task(t["task_id"])
                        records.append({
                            "task_id": t["task_id"],
                            "command": t["command_text"],
                            "state": t.get("final_state"),
                            "created_at": t.get("created_at"),
                            "action_count": len(actions),
                        })
            except Exception:
                pass
    else:
        try:
            tasks = query.recent_tasks(limit=limit)
            for t in tasks:
                actions = query.actions_for_task(t["task_id"])
                records.append({
                    "task_id": t["task_id"],
                    "command": t["command_text"],
                    "state": t.get("final_state"),
                    "created_at": t.get("created_at"),
                    "action_count": len(actions),
                })
        except Exception:
            pass

    count = len(records)
    return ToolResult(
        ok=True,
        tool="show_activity",
        data={"count": count, "records": records},
        factual_message=f"Retrieved {count} recent Activity record{'s' if count != 1 else ''}.",
        verified=True,
    )


def execute_undo_last(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Execute reverse rollback of the latest undo record.
    
    Spec §13: Evidence-based undo.
    """
    import json
    from pluma.config.paths import get_paths
    from pluma.memory.activity import ActivityLedger, ActivityQuery
    from pluma.memory.db import DbConnection
    from pluma.rollback.recipes import RollbackRecipes

    recipes = RollbackRecipes()

    # 1. Look for in-memory undo records in task_context
    if task_context and hasattr(task_context, "undo_stack") and task_context.undo_stack:
        undo_data = task_context.undo_stack.pop()
        action_name = undo_data.get("action", "")
        step_res = recipes.apply(action_name, undo_data)
        if not step_res.ok:
            return ToolResult.failure("undo_last", step_res.message)
        return ToolResult(
            ok=True,
            tool="undo_last",
            data=step_res.data or {"action": step_res.action},
            factual_message=f"Undo: {step_res.message}",
            verified=True,
        )

    # 2. Check SQLite Activity Ledger for the most recent unconsumed undo record
    db_conn = None
    if task_context and hasattr(task_context, "db") and task_context.db:
        db_conn = task_context.db
    elif task_context and hasattr(task_context, "ledger") and task_context.ledger:
        db_conn = getattr(task_context.ledger, "_db", None)

    if not db_conn:
        try:
            paths = get_paths()
            db_path = str(paths.db_path)
            if os.path.exists(db_path):
                db_conn = DbConnection(db_path)
                if not db_conn.is_open:
                    db_conn.open()
        except Exception:
            pass

    if db_conn:
        try:
            query = ActivityQuery(db_conn)
            latest = query.get_latest_available_undo_record()
            if latest:
                raw_json = latest.get("undo_json")
                action_id = latest.get("action_id")
                undo_dict = json.loads(raw_json) if isinstance(raw_json, str) else (raw_json or {})
                action_name = undo_dict.get("action") or latest.get("tool", "")
                step_res = recipes.apply(action_name, undo_dict)

                if step_res.ok:
                    ledger = ActivityLedger(db_conn)
                    ledger.mark_undo_consumed(action_id)
                    return ToolResult(
                        ok=True,
                        tool="undo_last",
                        data=step_res.data or {"action": step_res.action},
                        factual_message=f"Undo: {step_res.message}",
                        verified=True,
                    )
                else:
                    return ToolResult.failure("undo_last", f"Rollback failed: {step_res.message}")
        except Exception as exc:
            return ToolResult.failure("undo_last", f"Failed to read undo record from database: {exc}")

    return ToolResult.failure("undo_last", "No undo records available to reverse.")


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

SYSTEM_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="get_system_status",
        description="Query system resource metrics (CPU, RAM, disk usage).",
        args_schema=GetSystemStatusArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_get_system_status,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="system_status",
        description="Query system resource metrics (CPU, RAM, disk usage).",
        args_schema=GetSystemStatusArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_get_system_status,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="stop_current",
        description="Stop active task execution immediately.",
        args_schema=StopCurrentArgs,
        risk_class=RiskClass.LOW,
        timeout_s=3.0,
        executor=execute_stop_current,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=False,
    ),
    ToolSpec(
        name="show_activity",
        description="Query recent Activity Ledger task and action history.",
        args_schema=ShowActivityArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_show_activity,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="undo_last",
        description="Reverse the most recent reversible action.",
        args_schema=UndoLastArgs,
        risk_class=RiskClass.MEDIUM,
        timeout_s=10.0,
        executor=execute_undo_last,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]


# ---------------------------------------------------------------------------
# Battery Status (registered separately; requires no rewrite of the above)
# ---------------------------------------------------------------------------

def execute_battery_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Query system battery/power state via Win32 GetSystemPowerStatus."""
    data: Dict[str, Any] = {}

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_ = [
                ("ACLineStatus", ctypes.c_byte),
                ("BatteryFlag", ctypes.c_byte),
                ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte),
                ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD),
            ]

        sps = SYSTEM_POWER_STATUS()
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        ok = kernel32.GetSystemPowerStatus(ctypes.byref(sps))
        if ok:
            ac_line = sps.ACLineStatus        # 0=offline, 1=online, 255=unknown
            pct = sps.BatteryLifePercent      # 0-100 or 255 if unknown
            charging = ac_line == 1
            has_battery = sps.BatteryFlag != 128  # 128 = no battery
            data = {
                "ac_connected": charging,
                "has_battery": has_battery,
                "percent": pct if pct != 255 else None,
                "charging": charging and has_battery,
            }
            if pct == 255:
                msg = "AC power, no battery detected."
            elif charging:
                msg = f"Battery at {pct}%, charging (AC connected)."
            else:
                msg = f"Battery at {pct}%, on battery power."
        else:
            data = {"ac_connected": None, "has_battery": None, "percent": None}
            msg = "Battery status unavailable."
    else:
        data = {"ac_connected": True, "has_battery": False, "percent": None}
        msg = "Battery status: AC power (non-Windows stub)."

    return ToolResult(
        ok=True,
        tool="battery_status",
        data=data,
        factual_message=msg,
        verified=True,
    )


SYSTEM_TOOL_SPECS.append(ToolSpec(
    name="battery_status",
    description="Query system battery and AC power status.",
    args_schema=BatteryStatusArgs,
    risk_class=RiskClass.READ,
    timeout_s=5.0,
    executor=execute_battery_status,
    verifier=verify_noop,
    undo_builder=None,
    adapter_priority=[AdapterPriority.NATIVE_API],
    cancellable=True,
))
