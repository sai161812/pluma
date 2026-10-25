"""Strict read-only app/window observations shared by registered ToolSpecs."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator, field_validator

from pluma.tools.base import ToolResult, VerifyResult
from pluma.tools.processes import ProcessTargetArgs


class Strict(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}

    @field_validator('available', mode='before', check_fields=False)
    @classmethod
    def exact_available_flag(cls, value):
        if type(value) is not bool:
            raise ValueError('Availability must be an observed boolean.')
        return value


class ListAppWindowsArgs(Strict):
    visible_only: bool = True
    filter: str | None = Field(default=None, min_length=1, max_length=1024)
    max_entries: int = Field(default=128, ge=1, le=256, description='Maximum observed window entries, grouped by process for list_apps.')
    max_scan_entries: int = Field(default=1024, ge=1, le=2048)


class WindowEntry(Strict):
    available: Literal[True]
    hwnd: int = Field(gt=0)
    pid: int = Field(gt=0, le=0xffffffff)
    creation_time: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=1024)
    title: str = Field(max_length=2048)
    title_truncated: bool
    thread_id: int = Field(gt=0)
    class_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    visible: bool
    minimized: bool
    maximized: bool
    rectangle: list[int] = Field(min_length=4, max_length=4)


class UnavailableWindow(Strict):
    available: Literal[False]
    hwnd: int = Field(gt=0)
    pid: int = Field(ge=0, le=0xffffffff)
    reason: Literal['access_denied', 'gone_or_changed', 'unavailable']


class WindowListData(ListAppWindowsArgs):
    observed_at_ns: int = Field(gt=0)
    windows: list[WindowEntry | UnavailableWindow] = Field(max_length=256)
    count: int = Field(ge=0, le=256)
    scanned_windows: int = Field(ge=0, le=2048)
    limited: bool

    @model_validator(mode='after')
    def coherent(self):
        if (self.count != len(self.windows) or self.count > self.max_entries
                or self.scanned_windows > self.max_scan_entries or self.count > self.scanned_windows
                or len({entry.hwnd for entry in self.windows}) != self.count):
            raise ValueError('Inconsistent bounded window observation.')
        for entry in self.windows:
            if entry.available:
                if self.visible_only and not entry.visible:
                    raise ValueError('Hidden window contradicts the requested scope.')
        return self


def project_apps(observation):
    groups = {}
    for entry in observation['windows']:
        if not entry['available']:
            continue
        key = (entry['pid'], entry['creation_time'])
        group = groups.setdefault(key, {'pid': key[0], 'creation_time': key[1], 'name': entry['name'], 'window_handles': []})
        if group['name'] != entry['name']:
            raise ValueError('Process name changed during observation.')
        group['window_handles'].append(entry['hwnd'])
    return {'count': len(groups), 'apps': sorted(groups.values(), key=lambda row: row['pid']),
            'window_observation': observation,
            'unavailable_windows': sum(not entry['available'] for entry in observation['windows'])}


def execute_list(args, context=None, *, apps=False):
    from pluma.adapters.app_windows import enumerate_windows
    from pluma.core.cancellation import TaskCancelledError
    tool = 'list_apps' if apps else 'list_windows'
    try:
        values = ListAppWindowsArgs.model_validate(args).model_dump()
        packet = WindowListData.model_validate(enumerate_windows(values, context, apps=apps)).model_dump()
        data = project_apps(packet) if apps else packet
        unavailable = sum(not entry['available'] for entry in packet['windows'])
        result = ToolResult.success(tool, data=data, verified=False, adapter_used='native_api',
            factual_message=f"Observed {data['count']} {'application instances' if apps else 'window entries'}." +
                (' Enumeration stopped at a limit.' if packet['limited'] else '') +
                (f' {unavailable} window entries were unreadable or changed.' if unavailable else '')).model_copy(
                    update={'private_context': {'window_observation': packet}})
        checked = verify_list(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except TaskCancelledError:
        return ToolResult.failure(tool, 'Application/window inspection was stopped.', 'TASK_CANCELLED')
    except Exception:
        return ToolResult.failure(tool, 'Native application/window observation could not be verified.', 'APP_WINDOW_READ_UNVERIFIED')


def verify_list(result):
    from pluma.adapters.app_windows import verify_windows
    try:
        packet = WindowListData.model_validate(result.private_context['window_observation']).model_dump()
        projected = project_apps(packet) if result.tool == 'list_apps' else packet
        filtered = all(not entry['available'] or packet['filter'] is None or packet['filter'].casefold() in
            entry['name' if result.tool == 'list_apps' else 'title'].casefold() for entry in packet['windows'])
        valid = (result.ok and result.tool in ('list_apps', 'list_windows') and result.adapter_used == 'native_api'
                 and result.data == projected and filtered and verify_windows(packet))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_window_process_identity', detail=(
        'Scoped native window/process identities read back.' if valid else 'Application/window observation was not verified.'))


class AppStatusData(ProcessTargetArgs):
    state: Literal['running', 'gone_or_changed']
    running: bool
    name: str | None = Field(min_length=1, max_length=1024)

    @model_validator(mode='after')
    def coherent(self):
        if self.running != (self.state == 'running') or self.running != (self.name is not None):
            raise ValueError('Process status contradicts its identity observation.')
        return self


def execute_status(args, context=None):
    from pluma.adapters.app_windows import status
    from pluma.core.cancellation import TaskCancelledError
    try:
        token = getattr(context, 'cancellation_token', None)
        if token is not None:
            token.raise_if_cancelled()
        values = ProcessTargetArgs.model_validate(args).model_dump()
        data = AppStatusData.model_validate(status(values)).model_dump()
        if token is not None:
            token.raise_if_cancelled()
        result = ToolResult.success('app_status', data=data, verified=False, adapter_used='native_api',
            factual_message='Requested process identity is live.' if data['running'] else 'Requested process identity is no longer live.').model_copy(
                update={'private_context': {'app_status': data}})
        checked = verify_status(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except TaskCancelledError:
        return ToolResult.failure('app_status', 'Application inspection was stopped.', 'TASK_CANCELLED')
    except Exception:
        return ToolResult.failure('app_status', 'Exact application identity is unreadable or unavailable.', 'APP_STATUS_UNVERIFIED')


def verify_status(result):
    from pluma.adapters.app_windows import status
    try:
        data = AppStatusData.model_validate(result.data).model_dump()
        valid = (result.ok and result.tool == 'app_status' and result.adapter_used == 'native_api'
            and data == result.private_context['app_status']
            and status({key: data[key] for key in ('pid', 'creation_time')}) == data)
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_process_identity_readback', detail=(
        'Exact process identity status read back.' if valid else 'Application status was not verified.'))
