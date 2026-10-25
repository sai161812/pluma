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
import uuid
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import verify_noop
from pluma.tools.power_actions import POWER_ACTION_SPECS


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class GetSystemStatusArgs(BaseModel):
    """Arguments for get_system_status."""
    model_config = {"extra": "forbid", "strict": True}


class StopCurrentArgs(BaseModel):
    """Arguments for stop_current."""
    model_config = {"extra": "forbid", "strict": True}
    reason: Literal["user_stop"] = "user_stop"


class ShowActivityArgs(BaseModel):
    """Arguments for show_activity."""
    model_config = {"extra": "forbid", "strict": True}
    limit: int = Field(default=10, ge=1, le=100, description="Maximum number of activity records to return.")


class UndoLastArgs(BaseModel):
    """Arguments for undo_last."""
    model_config = {"extra": "forbid"}


class BatteryStatusArgs(BaseModel):
    """Arguments for battery_status."""
    model_config = {"extra": "forbid", "strict": True}


class FlushDnsCacheArgs(BaseModel):
    """Argument-free fixed operation; no command or target comes from the planner."""

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


def verify_stop_current(result: ToolResult) -> VerifyResult:
    from pluma.core.stop_protocol import StopReply, StopOutcome
    try:
        reply = StopReply.model_validate_json(__import__("json").dumps(result.data))
        clean = result.ok and reply.status == "ok" and all(
            item.outcome in (StopOutcome.STOPPED, StopOutcome.TERMINAL)
            and item.completion_verified and item.terminal_persisted is True
            and not item.has_residual for item in reply.tasks)
    except (TypeError, ValueError):
        clean = False
    return VerifyResult(ok=clean, method="supervisor_readback",
        detail="STOP cleanup and terminal history verified." if clean else "STOP cleanup is pending or unverified.")


def execute_stop_current(args: Dict[str, Any], task_context: Any = None, *, stop_service=None) -> ToolResult:
    if not callable(stop_service):
        return ToolResult.failure("stop_current", "Priority STOP service is unavailable.", "STOP_SERVICE_UNAVAILABLE")
    try:
        StopCurrentArgs.model_validate(args)
        reply = stop_service(wait_s=.1)
        result = ToolResult.success("stop_current", data=reply.wire(), verified=False,
            factual_message="STOP requested. Cleanup results are recorded per task.", adapter_used="supervisor")
        proof = verify_stop_current(result)
        return result.model_copy(update={"verified": proof.ok, "verify_detail": proof})
    except Exception:
        return ToolResult.failure("stop_current", "STOP cleanup could not be verified.", "STOP_SERVICE_FAILED")


class ActivityEntry(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    task_id: str = Field(min_length=1, max_length=128)
    command: str = Field(max_length=4096)
    command_truncated: bool
    state: Optional[str]
    created_at: str
    input_mode: str
    route: Optional[str]
    action_count: int = Field(ge=0)


class ActivityData(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    count: int = Field(ge=0, le=100)
    limit: int = Field(ge=1, le=100)
    records: List[ActivityEntry] = Field(max_length=100)


def verify_activity(result: ToolResult) -> VerifyResult:
    try:
        data = ActivityData.model_validate(result.data)
        valid = (result.ok and result.tool == "show_activity"
                 and data.count == len(data.records) <= data.limit
                 and len({row.task_id for row in data.records}) == data.count)
    except (TypeError, ValueError):
        valid = False
    return VerifyResult(ok=valid, method="sqlite_snapshot",
        detail="Bounded executor-ledger snapshot read." if valid else "Activity snapshot was not verified.")


def execute_show_activity(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.memory.reader import recent_activity, recent_activity_from_query
    from pluma.memory.activity import ActivityQuery
    try:
        limit = ShowActivityArgs.model_validate(args).limit
        query = getattr(task_context, "query", None)
        if isinstance(query, ActivityQuery):
            records = recent_activity_from_query(query, limit)
        else:
            records = recent_activity(getattr(task_context, "storage_path", None), limit)
        data = ActivityData(count=len(records), limit=limit, records=records).model_dump()
    except Exception:
        return ToolResult.failure("show_activity", "Activity history could not be read.", "ACTIVITY_READ_FAILED")
    result = ToolResult.success("show_activity", data=data, verified=False,
        factual_message=f"Retrieved {len(records)} recent Activity records.", adapter_used="sqlite")
    proof = verify_activity(result)
    return result.model_copy(update={"verified": proof.ok, "verify_detail": proof})


def verify_undo_last(result: ToolResult) -> VerifyResult:
    from pluma.memory.undo import verify
    try:
        receipt = result.private_context["undo_receipt"]
        valid = (result.ok and result.tool == "undo_last"
                 and result.data == {"action_row_id": receipt["action_id"], "action": receipt["undo_data"]["action"]}
                 and verify(receipt))
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method="inverse_and_sqlite_readback", detail=(
        "Inverse state and atomic undo consumption verified." if valid else "Undo state was not verified."))


def execute_undo_last(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.memory.undo import claim_latest, finish, verify
    from pluma.rollback.recipes import RollbackRecipes
    try:
        path = getattr(task_context, "storage_path", None)
        binding = getattr(task_context, 'execution_binding', None) or {}
        private = binding.get('clipboard_private')
        screen_text_private = binding.get('screen_text_private')
        receipt = claim_latest(path, task_context.task_id, private, screen_text_private)
    except Exception:
        return ToolResult.failure("undo_last", "No safe unclaimed undo record is available.", "UNDO_UNAVAILABLE")
    try:
        task_context.cancellation_token.raise_if_cancelled()
        state = receipt['undo_data']
        if state['action'] == 'clipboard_restore':
            payload = dict(state, clipboard_private=receipt['clipboard_private'])
        elif state['action'] == 'screen_control_text':
            payload = dict(state, screen_text_private=receipt['screen_text_private'])
        else:
            payload = state
        inverse = RollbackRecipes().apply(state['action'], payload)
        if state['action'] == 'clipboard_restore' and inverse.ok:
            receipt['clipboard_restore_proof'] = inverse.data['clipboard_inverse_proof']
        finish(receipt, inverse.ok)
        if not inverse.ok or not verify(receipt):
            raise ValueError("Inverse or consumption was not verified.")
        # Worker snapshots are reconciled in the parent only after proof/history.
        task_context.undo_stack[:] = [item for item in task_context.undo_stack if item != receipt["undo_data"]]
        return ToolResult.success("undo_last", data={"action_row_id": receipt["action_id"],
            "action": receipt["undo_data"]["action"]}, verified=True,
            factual_message="Reversed one verified action.", adapter_used="sqlite_and_inverse").model_copy(
                update={"private_context": {"undo_receipt": receipt}})
    except Exception:
        return ToolResult.failure("undo_last", "Undo could not be verified. Its claim and pre-state are retained.", "UNDO_UNVERIFIED")


class FlushDnsIntent(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    action: Literal["non_undoable_elevation"]
    guard_version: Literal[1]
    non_undoable: Literal[True]
    tool: Literal["flush_dns_cache"]
    operation: Literal["FLUSH_DNS"]
    operation_id: str = Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def capture_flush_dns_intent(args: Dict[str, Any], task_context: Any = None) -> Dict[str, Any]:
    FlushDnsCacheArgs.model_validate(args)
    token = getattr(task_context, "cancellation_token", None)
    if token is None or not getattr(task_context, "task_id", None):
        raise ValueError("An owned task is required to journal elevation intent.")
    token.raise_if_cancelled()
    return FlushDnsIntent(action="non_undoable_elevation", guard_version=1,
        non_undoable=True, tool="flush_dns_cache", operation="FLUSH_DNS",
        operation_id=str(uuid.uuid4())).model_dump()


def execute_flush_dns_cache(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    try:
        FlushDnsCacheArgs.model_validate(args)
        binding = getattr(task_context, "execution_binding", None) or {}
        if binding != {"elevation_operation": "FLUSH_DNS"}:
            return ToolResult.failure("flush_dns_cache", "The exact elevation operation was not authorized.",
                "ELEVATION_BINDING_INVALID")
        if task_context is None:
            return ToolResult.failure("flush_dns_cache", "An owned task is required for elevation.",
                "ELEVATION_OWNERSHIP_REQUIRED")
        pending = next((item for item in reversed(task_context.undo_stack)
            if item.get("action") == "pending_mutation" and item.get("tool") == "flush_dns_cache"), None)
        if pending is None:
            return ToolResult.failure("flush_dns_cache", "Durable elevation intent is unavailable.",
                "COMMIT_JOURNAL_REQUIRED")
        intent = FlushDnsIntent.model_validate(pending.get("pre_state", {}))
        if intent.operation != binding["elevation_operation"]:
            return ToolResult.failure("flush_dns_cache", "Elevation intent does not match the authorized operation.",
                "ELEVATION_INTENT_MISMATCH")
        task_context.cancellation_token.raise_if_cancelled()
        from pluma.policy.elevation_broker import ElevationBroker, ElevationOperation, ElevationOpType
        return ElevationBroker(timeout_s=15.0).execute_operation(
            ElevationOperation(op_type=ElevationOpType.FLUSH_DNS),
            task_id=task_context.task_id, task_context=task_context,
            timeout_s=15.0,
        )
    except Exception:
        return ToolResult.failure("flush_dns_cache", "The one-operation elevation request failed; its effect may be uncertain.",
            "ELEVATION_OPERATION_FAILED")


def verify_flush_dns_cache(result: ToolResult) -> VerifyResult:
    data = result.data if isinstance(result.data, dict) else {}
    valid = (result.ok and result.tool == "flush_dns_cache"
        and result.adapter_used == "one_operation_uac"
        and data == {"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True,
            "cache_entry_count": 0, "cache_readback_observed": True}
        and type(data.get("cache_entry_count")) is int
        and type(data.get("exit_code")) is int
        and data.get("process_exit_observed") is True
        and data.get("cache_readback_observed") is True)
    return VerifyResult(ok=valid, method="independent_dns_cache_readback", detail=(
        "The fixed DNS operation exited and an independent cache read observed zero entries."
        if valid else "The fixed DNS operation or its process exit was not verified."))


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

SYSTEM_TOOL_SPECS: List[ToolSpec] = POWER_ACTION_SPECS + [
    ToolSpec(
        name="flush_dns_cache",
        description="Flush the local Windows DNS client cache through one fixed UAC operation.",
        args_schema=FlushDnsCacheArgs,
        risk_class=RiskClass.ADMIN,
        timeout_s=20.0,
        process_isolated=True,
        non_undoable=True,
        executor=execute_flush_dns_cache,
        verifier=verify_flush_dns_cache,
        undo_builder=capture_flush_dns_intent,
        elevation_operation="FLUSH_DNS",
        adapter_priority=[AdapterPriority.POWERSHELL],
        cancellable=True,
    ),
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
        verifier=verify_stop_current,
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
        process_isolated=True,
        executor=execute_show_activity,
        verifier=verify_activity,
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
        process_isolated=True,
        executor=execute_undo_last,
        verifier=verify_undo_last,
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
