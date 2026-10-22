"""Typed, bounded native process inspection. No process control or command lines."""
from __future__ import annotations

from functools import partial
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult


class StrictModel(BaseModel):
    model_config = {"strict": True, "extra": "forbid", "allow_inf_nan": False}


class ListProcessesArgs(StrictModel):
    max_entries: int = Field(default=100, ge=1, le=500)


class ProcessTargetArgs(StrictModel):
    pid: int = Field(gt=0, le=0xFFFFFFFF)
    creation_time: int = Field(gt=0, description="Native Windows FILETIME from list_processes.")


class TerminateProcessArgs(ProcessTargetArgs):
    allow_unsaved_data_loss: Literal[True] = Field(description="Required acknowledgement: forced exit can lose unsaved data and cannot be undone.")

    @field_validator('allow_unsaved_data_loss', mode='before')
    @classmethod
    def exact_acknowledgement(cls, value):
        if value is not True:
            raise ValueError('An explicit boolean true acknowledgement is required.')
        return value


class ProcessExitData(ProcessTargetArgs):
    state: Literal['exited']
    exit_code: int = Field(ge=0, le=0xFFFFFFFF)
    windows_signaled: int = Field(ge=0, le=64)
    non_undoable: Literal[True]


class ProcessEntry(StrictModel):
    pid: int = Field(ge=0, le=0xFFFFFFFF)
    available: bool
    creation_time: int | None = Field(ge=1)
    name: str | None = Field(min_length=1, max_length=1024)
    unavailable_reason: Literal["access_denied", "gone_or_changed", "unavailable"] | None

    @model_validator(mode="after")
    def coherent_identity(self):
        if self.available:
            if self.creation_time is None or self.name is None or self.unavailable_reason is not None:
                raise ValueError("Available entries require a verified process identity.")
        elif self.creation_time is not None or self.name is not None or self.unavailable_reason is None:
            raise ValueError("Unavailable entries cannot claim process metadata.")
        return self


class ProcessListData(StrictModel):
    observed_at_ns: int = Field(gt=0)
    entries: list[ProcessEntry] = Field(max_length=500)
    observed_pid_count: int = Field(ge=0)
    truncated: bool

    @model_validator(mode="after")
    def coherent_count(self):
        if (self.observed_pid_count < len(self.entries)
                or self.truncated != (self.observed_pid_count > len(self.entries))
                or len({entry.pid for entry in self.entries}) != len(self.entries)):
            raise ValueError("Process enumeration count is inconsistent.")
        return self


class ProcessInfoData(ProcessTargetArgs):
    observed_at_ns: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=1024)
    status: str = Field(min_length=1, max_length=64)
    parent_pid: int = Field(ge=0)
    thread_count: int = Field(ge=1)


class ProcessUsageData(ProcessTargetArgs):
    observed_at_ns: int = Field(gt=0)
    cpu_percent: float = Field(ge=0)
    sample_seconds: float = Field(gt=0)
    rss_bytes: int = Field(ge=0)


DATA_SCHEMAS = {"list_processes": ProcessListData, "process_info": ProcessInfoData,
                "process_usage": ProcessUsageData}


def execute_inspection(args, task_context=None, *, tool):
    from pluma.adapters.processes import inspect_processes
    from pluma.core.cancellation import TaskCancelledError
    try:
        data = inspect_processes(tool, args, task_context)
        data = DATA_SCHEMAS[tool].model_validate(data).model_dump()
    except TaskCancelledError:
        return ToolResult.failure(tool, "Process inspection was stopped.", "TASK_CANCELLED")
    except NotImplementedError:
        return ToolResult.failure(tool, "Native Windows process inspection is unavailable.", "PROCESS_UNSUPPORTED")
    except PermissionError:
        return ToolResult.failure(tool, "Access to the process was denied.", "PROCESS_ACCESS_DENIED")
    except ProcessLookupError:
        return ToolResult.failure(tool, "Process is absent or its identity changed.", "PROCESS_IDENTITY_CHANGED")
    except Exception:
        return ToolResult.failure(tool, "Process state could not be read.", "PROCESS_READ_FAILED")
    message = (f"Observed {len(data['entries'])} process entries."
               if tool == "list_processes" else f"Read process {'usage' if tool == 'process_usage' else 'information'}.")
    return ToolResult.success(tool, data=data, factual_message=message, verified=True,
                              adapter_used="native_api", verify_detail=VerifyResult(
                                  ok=True, method="api", detail="Native process identity checked around the read."))


def verify_inspection(result):
    valid = (result.ok and result.verified and result.adapter_used == "native_api"
             and isinstance(result.verify_detail, VerifyResult) and result.verify_detail.ok
             and result.verify_detail.method == "api" and result.tool in DATA_SCHEMAS)
    if valid:
        try:
            DATA_SCHEMAS[result.tool].model_validate(result.data)
        except ValidationError:
            valid = False
    return VerifyResult(ok=bool(valid), method="api", detail=(
        "Native process observation validated." if valid else "Native process observation was not established."))


PROCESS_TOOL_SPECS = [ToolSpec(
    name=name, description=description, args_schema=schema, risk_class=RiskClass.READ,
    timeout_s=5, process_isolated=True, executor=partial(execute_inspection, tool=name),
    verifier=verify_inspection, adapter_priority=[AdapterPriority.NATIVE_API],
) for name, description, schema in [
    ("list_processes", "List bounded process identities without command lines; unavailable entries are explicit.", ListProcessesArgs),
    ("process_info", "Read information for one process matching its native creation time.", ProcessTargetArgs),
    ("process_usage", "Sample CPU and memory usage for one process matching its native creation time.", ProcessTargetArgs),
]]


def capture_process_intent(args, context=None, *, tool):
    from pluma.adapters.process_control import capture_intent
    return capture_intent(args, context, tool=tool)


def execute_process_control(args, task_context=None, *, tool):
    from pluma.adapters.process_control import execute_control
    try:
        data, proof = execute_control(tool, args, task_context)
        data = ProcessExitData.model_validate(data).model_dump()
        return ToolResult.success(tool, data=data, verified=True, adapter_used='native_handle',
            factual_message='Target process exited. This action cannot be undone.').model_copy(
                update={'private_context': {'process_exit': proof}})
    except Exception:
        return ToolResult.failure(tool,
            'Process exit could not be verified. No automatic force fallback was attempted. Effects may remain.',
            'PROCESS_EXIT_UNVERIFIED')


def verify_process_control(result):
    from pluma.core.ownership import subprocess_absent
    try:
        data = ProcessExitData.model_validate(result.data)
        proof = result.private_context['process_exit']
        valid = (result.ok and result.verified and result.adapter_used == 'native_handle'
            and proof == {'original_handle_signaled': True, 'pid': data.pid, 'creation_time': data.creation_time,
                'exit_code': data.exit_code, 'tool': result.tool}
            and (result.tool in ('graceful_close_process', 'close_app') and data.windows_signaled > 0
                 or result.tool == 'terminate_process' and data.windows_signaled == 0)
            and subprocess_absent(data.pid, data.creation_time))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_process_handle',
        detail='Original process exit independently verified.' if valid else 'Process exit was not verified.')


PROCESS_TOOL_SPECS += [ToolSpec(name=name, description=description, args_schema=schema,
    risk_class=RiskClass.MEDIUM, timeout_s=8, process_isolated=True, non_undoable=True,
    executor=partial(execute_process_control, tool=name), verifier=verify_process_control,
    undo_builder=partial(capture_process_intent, tool=name), adapter_priority=[AdapterPriority.NATIVE_API])
    for name, description, schema in [
        ('graceful_close_process', 'Ask one exact same-user process to close its native windows; verify exit without force fallback. Not undoable.', ProcessTargetArgs),
        ('terminate_process', 'Force one exact same-user noncritical process to exit; unsaved data can be lost. Not undoable.', TerminateProcessArgs),
    ]]
