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
    model_config = {"extra": "forbid", "strict": True}


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
    model_config = {"extra": "forbid", "strict": True}


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


class StrictObservation(BaseModel):
    model_config = {"strict": True, "extra": "forbid", "allow_inf_nan": False}


class SystemStatusData(StrictObservation):
    os: str = Field(min_length=1, max_length=2048)
    python_version: str = Field(min_length=1, max_length=2048)
    disk_root: str
    cpu_percent: float = Field(ge=0, le=100)
    cpu_sample_seconds: float = Field(gt=0)
    disk_free_gb: float = Field(ge=0)
    disk_total_gb: float = Field(ge=0)
    ram_free_gb: float = Field(ge=0)
    ram_total_gb: float = Field(ge=0)
    memory_load_percent: float = Field(ge=0, le=100)
    native_metrics: Dict[str, Any]


class NetworkStatusArgs(StrictObservation):
    max_entries: int = Field(default=32, ge=1, le=128)


class NetworkEntry(StrictObservation):
    name: str = Field(min_length=1, max_length=1024)
    is_up: bool
    mtu: int = Field(ge=0)
    link_speed_mbps: Optional[float] = Field(gt=0)


class NetworkStatusData(StrictObservation):
    interfaces: List[NetworkEntry] = Field(max_length=128)
    observed_count: int = Field(ge=0)
    max_entries: int = Field(ge=1, le=128)
    truncated: bool
    internet_connectivity: None


def verify_system_status(result: ToolResult) -> VerifyResult:
    from pluma.adapters.system_status import decode_system_status
    try:
        data = SystemStatusData.model_validate(result.data).model_dump()
        valid = (result.ok and result.tool in ("get_system_status", "system_status")
                 and data == decode_system_status(data["native_metrics"]))
    except (TypeError, ValueError, KeyError):
        valid = False
    return VerifyResult(ok=valid, method="native_api", detail=(
        "Native CPU sample and resource sizes agree with the observation." if valid else "System observation was not verified."))


def verify_network_status(result: ToolResult) -> VerifyResult:
    try:
        data = NetworkStatusData.model_validate(result.data)
        names = [item.name for item in data.interfaces]
        valid = (result.ok and result.tool == "network_status"
            and len(names) == min(data.observed_count, data.max_entries)
            and data.truncated == (data.observed_count > len(names))
            and len(set(names)) == len(names) and names == sorted(names))
    except (TypeError, ValueError):
        valid = False
    return VerifyResult(ok=valid, method="native_api", detail=(
        "Native interface snapshot is bounded; internet connectivity is unknown." if valid else "Network observation was not verified."))


def _system_observation(tool):
    from pluma.adapters.system_status import read_system_status
    try:
        data = SystemStatusData.model_validate(read_system_status()).model_dump()
    except NotImplementedError:
        return ToolResult.failure(tool, "Native Windows system status is unavailable.", "UNSUPPORTED_PLATFORM")
    except Exception:
        return ToolResult.failure(tool, "Native system resource status could not be read.", "SYSTEM_STATUS_FAILED")
    message = (f"System status: CPU {data['cpu_percent']:g}%, RAM {data['ram_free_gb']} GB available of "
               f"{data['ram_total_gb']} GB, disk {data['disk_root']} has {data['disk_free_gb']} GB free "
               f"of {data['disk_total_gb']} GB.")
    result = ToolResult.success(tool, data=data, verified=False, factual_message=message, adapter_used="native_api")
    proof = verify_system_status(result)
    if not proof.ok:
        return ToolResult.failure(tool, "System observation could not be verified.", "POSTCONDITION_FAILED")
    return result.model_copy(update={"verified": True, "verify_detail": proof})


def execute_get_system_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _system_observation("get_system_status")


def execute_system_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _system_observation("system_status")


def execute_network_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.adapters.system_status import read_network_status
    try:
        data = NetworkStatusData.model_validate(read_network_status(args.get("max_entries", 32))).model_dump()
    except NotImplementedError:
        return ToolResult.failure("network_status", "Native Windows network status is unavailable.", "UNSUPPORTED_PLATFORM")
    except Exception:
        return ToolResult.failure("network_status", "Native network interface status could not be read.", "NETWORK_STATUS_FAILED")
    result = ToolResult.success("network_status", data=data, verified=False, adapter_used="native_api",
        factual_message=f"Read {len(data['interfaces'])} of {data['observed_count']} network interfaces. Internet connectivity is unknown.")
    proof = verify_network_status(result)
    if not proof.ok:
        return ToolResult.failure("network_status", "Network observation could not be verified.", "POSTCONDITION_FAILED")
    return result.model_copy(update={"verified": True, "verify_detail": proof})


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
        process_isolated=True,
        executor=execute_get_system_status,
        verifier=verify_system_status,
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
        process_isolated=True,
        executor=execute_system_status,
        verifier=verify_system_status,
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

class BatteryData(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    ac_connected: Optional[bool]
    has_battery: Optional[bool]
    percent: Optional[int] = Field(ge=0, le=100)
    charging: Optional[bool]
    battery_saver: Optional[bool]
    remaining_seconds: Optional[int] = Field(ge=0)
    full_seconds: Optional[int] = Field(ge=0)
    native_status: Dict[str, int]


def verify_battery_status(result: ToolResult) -> VerifyResult:
    from pluma.adapters.power import decode_power_status
    try:
        data = BatteryData.model_validate(result.data).model_dump()
        valid = result.ok and result.tool == "battery_status" and data == decode_power_status(data["native_status"])
    except (ValueError, TypeError, KeyError):
        valid = False
    return VerifyResult(ok=valid, method="native_api", detail=(
        "Native unsigned power fields and reported state agree." if valid else "Battery observation was not verified."))


def execute_battery_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.adapters.power import read_battery_status
    try:
        data = BatteryData.model_validate(read_battery_status()).model_dump()
    except NotImplementedError:
        return ToolResult.failure("battery_status", "Native Windows battery status is unavailable.", "UNSUPPORTED_PLATFORM")
    except Exception:
        return ToolResult.failure("battery_status", "Native battery status could not be read.", "BATTERY_STATUS_FAILED")
    if data["has_battery"] is False:
        battery = "No system battery detected"
    elif data["has_battery"] is None:
        battery = "Battery presence unknown"
    else:
        battery = "Battery level unknown" if data["percent"] is None else f"Battery at {data['percent']}%"
    charging = {True: "charging", False: "not charging", None: "charging status unknown"}[data["charging"]]
    ac = {True: "AC connected", False: "AC disconnected", None: "AC status unknown"}[data["ac_connected"]]
    result = ToolResult.success("battery_status", data=data, verified=False,
        factual_message=f"{battery}, {charging}, {ac}.", adapter_used="native_api")
    proof = verify_battery_status(result)
    if not proof.ok:
        return ToolResult.failure("battery_status", "Battery observation could not be verified.", "POSTCONDITION_FAILED")
    return result.model_copy(update={"verified": True, "verify_detail": proof})


SYSTEM_TOOL_SPECS.append(ToolSpec(
    name="battery_status",
    description="Query system battery and AC power status.",
    args_schema=BatteryStatusArgs,
    risk_class=RiskClass.READ,
    timeout_s=5.0,
    process_isolated=True,
    executor=execute_battery_status,
    verifier=verify_battery_status,
    undo_builder=None,
    adapter_priority=[AdapterPriority.NATIVE_API],
    cancellable=True,
))


SYSTEM_TOOL_SPECS.append(ToolSpec(
    name="network_status", description="Read bounded native network interface link status; internet connectivity is unknown.",
    args_schema=NetworkStatusArgs, risk_class=RiskClass.READ, timeout_s=5, process_isolated=True,
    executor=execute_network_status, verifier=verify_network_status,
    adapter_priority=[AdapterPriority.NATIVE_API], cancellable=True,
))
