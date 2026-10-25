"""Policy-side allowlist for one-operation Windows elevation."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Optional

from pydantic import BaseModel

from pluma.tools.base import ToolResult

DEFAULT_ELEVATION_TIMEOUT_S = 15.0


class ElevationOpType(str, Enum):
    """The sole V1 operation currently authorized for one-operation UAC."""

    FLUSH_DNS = "FLUSH_DNS"


class ElevationOperation(BaseModel):
    """Closed, argument-free operation contract; planner values cannot reach UAC."""

    model_config = {"extra": "forbid", "frozen": True}

    op_type: ElevationOpType


class ElevationBroker:
    """Dispatch one static operation without elevating the resident process."""

    def __init__(
        self,
        timeout_s: float = DEFAULT_ELEVATION_TIMEOUT_S,
        *,
        runner: Optional[Callable[..., ToolResult]] = None,
    ) -> None:
        if not 0 < timeout_s <= 30:
            raise ValueError("Elevation timeout must be greater than zero and at most 30 seconds.")
        self.timeout_s = timeout_s
        self._runner = runner

    def execute_operation(
        self,
        operation: ElevationOperation,
        *,
        task_id: Optional[str],
        task_context: Any,
        timeout_s: Optional[float] = None,
    ) -> ToolResult:
        """Route the typed singleton operation to its native UAC adapter."""
        if not isinstance(operation, ElevationOperation):
            return ToolResult.failure("flush_dns_cache", "Elevation operation schema was rejected.", "ELEVATION_SCHEMA_INVALID")
        if operation.op_type != ElevationOpType.FLUSH_DNS:
            return ToolResult.failure("flush_dns_cache", "Elevation operation is not allowlisted.", "ELEVATION_OPERATION_DENIED")
        if not isinstance(task_id, str) or not task_id or task_context is None:
            return ToolResult.failure("flush_dns_cache", "An owned task is required for elevation.", "ELEVATION_OWNERSHIP_REQUIRED")

        runner = self._runner
        if runner is None:
            from pluma.adapters.elevation import run_dns_cache_flush
            runner = run_dns_cache_flush
        budget = min(self.timeout_s, float(timeout_s)) if timeout_s is not None else self.timeout_s
        if not 0 < budget <= 30:
            return ToolResult.failure("flush_dns_cache", "Elevation timeout was invalid.", "ELEVATION_TIMEOUT_INVALID")
        try:
            result = runner(task_id=task_id, timeout_s=budget, task_context=task_context)
        except Exception:
            return ToolResult.failure("flush_dns_cache", "The elevation adapter failed; the effect may be uncertain.",
                "ELEVATION_ADAPTER_FAILED")
        if not isinstance(result, ToolResult) or result.tool != "flush_dns_cache":
            return ToolResult.failure("flush_dns_cache", "The elevation adapter returned an invalid result.",
                "ELEVATION_RESULT_INVALID")
        return result
