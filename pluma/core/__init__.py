"""Public core contracts, loaded on access to avoid registry/import cycles."""
from importlib import import_module

_EXPORT_MODULES = {'CancellationToken': 'pluma.core.cancellation',
 'StopReason': 'pluma.core.cancellation',
 'TaskCancelledError': 'pluma.core.cancellation',
 'WindowsJobObject': 'pluma.core.job_object',
 'DEFAULT_MAX_REPLANS': 'pluma.core.multi_step',
 'HARD_CAP_MAX_REPLANS': 'pluma.core.multi_step',
 'MultiStepExecutionResult': 'pluma.core.multi_step',
 'MultiStepOrchestrator': 'pluma.core.multi_step',
 'StepExecutionRecord': 'pluma.core.multi_step',
 'Orchestrator': 'pluma.core.orchestrator',
 'StepRecord': 'pluma.core.orchestrator',
 'TaskExecutionResult': 'pluma.core.orchestrator',
 'OwnershipRegistry': 'pluma.core.ownership',
 'get_process_creation_time': 'pluma.core.ownership',
 'CrashRecoveryManager': 'pluma.core.recovery',
 'CrashRecoveryResult': 'pluma.core.recovery',
 'InputMode': 'pluma.core.request',
 'PlumaRequest': 'pluma.core.request',
 'ResidentCore': 'pluma.core.resident',
 'RouteResult': 'pluma.core.router',
 'Router': 'pluma.core.router',
 'InvalidTaskTransition': 'pluma.core.task_supervisor',
 'OwnedResource': 'pluma.core.task_supervisor',
 'ResourceOwnership': 'pluma.core.task_supervisor',
 'TaskCapsule': 'pluma.core.task_supervisor',
 'TaskState': 'pluma.core.task_supervisor',
 'TaskStep': 'pluma.core.task_supervisor',
 'TaskSupervisor': 'pluma.core.task_supervisor'}

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


def __getattr__(name):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
