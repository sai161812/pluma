"""pluma.core — Resident core, task lifecycle, routing, multi-step execution and IPC."""

from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
from pluma.core.job_object import WindowsJobObject
from pluma.core.multi_step import (
    DEFAULT_MAX_REPLANS,
    HARD_CAP_MAX_REPLANS,
    MultiStepExecutionResult,
    MultiStepOrchestrator,
    StepExecutionRecord,
)
from pluma.core.orchestrator import Orchestrator, StepRecord, TaskExecutionResult
from pluma.core.ownership import OwnershipRegistry, get_process_creation_time
from pluma.core.recovery import CrashRecoveryManager, CrashRecoveryResult
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.resident import ResidentCore
from pluma.core.router import RouteResult, Router
from pluma.core.task_supervisor import (
    InvalidTaskTransition,
    OwnedResource,
    ResourceOwnership,
    TaskCapsule,
    TaskState,
    TaskStep,
    TaskSupervisor,
)

__all__ = [
    # Cancellation & Request
    "CancellationToken",
    "StopReason",
    "TaskCancelledError",
    "PlumaRequest",
    "InputMode",
    # Task Supervision
    "TaskState",
    "TaskCapsule",
    "TaskStep",
    "TaskSupervisor",
    "InvalidTaskTransition",
    "ResourceOwnership",
    "OwnedResource",
    # Routing & Orchestration
    "Router",
    "RouteResult",
    "Orchestrator",
    "StepRecord",
    "TaskExecutionResult",
    "MultiStepOrchestrator",
    "MultiStepExecutionResult",
    "StepExecutionRecord",
    "DEFAULT_MAX_REPLANS",
    "HARD_CAP_MAX_REPLANS",
    # Native Ownership, Recovery & Resident Core
    "WindowsJobObject",
    "OwnershipRegistry",
    "get_process_creation_time",
    "CrashRecoveryManager",
    "CrashRecoveryResult",
    "ResidentCore",
]
