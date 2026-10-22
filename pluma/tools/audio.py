"""pluma.tools.audio — System audio playback and volume tools.

Spec §11, §13, §14: Audio actions as registered ToolSpecs.
Reversible tools (set_volume, mute, unmute) capture previous audio state.
Postconditions are read back before reporting success.

Boundary: No audio libraries imported at module level.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel, Field, ValidationError, model_validator

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class SetVolumeArgs(BaseModel):
    """Arguments for set_volume."""
    model_config = {"extra": "forbid", "strict": True}
    level: int = Field(ge=0, le=100, description="Target volume percentage (0 to 100).")


class MuteArgs(BaseModel):
    """Arguments for mute."""
    model_config = {"extra": "forbid", "strict": True}


class UnmuteArgs(BaseModel):
    """Arguments for unmute."""
    model_config = {"extra": "forbid", "strict": True}


class GetVolumeStatusArgs(BaseModel):
    """Arguments for get_volume_status."""
    model_config = {"extra": "forbid", "strict": True}


class VolumeData(BaseModel):
    model_config = {"extra": "forbid", "strict": True, "allow_inf_nan": False}
    endpoint_id: str = Field(min_length=1, max_length=1024)
    volume: int = Field(ge=0, le=100)
    scalar: float = Field(ge=0, le=1)
    muted: bool
    is_mock: bool

    @model_validator(mode="after")
    def coherent_scalar(self):
        if self.volume != round(self.scalar * 100):
            raise ValueError("Inconsistent native volume observation.")
        return self


class ListAudioDevicesArgs(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    max_entries: int = Field(default=64, ge=1, le=128)


class AudioDeviceData(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    endpoint_id: str = Field(min_length=1, max_length=1024)
    name: str | None = Field(min_length=1, max_length=1024)
    state: int = Field(ge=1, le=8)
    flow: str

    @model_validator(mode="after")
    def known_state(self):
        if self.state not in (1, 2, 4, 8) or self.flow not in ("render", "capture"):
            raise ValueError("Unknown endpoint state or direction.")
        return self


class AudioDevicesData(BaseModel):
    model_config = {"extra": "forbid", "strict": True}
    devices: list[AudioDeviceData] = Field(max_length=128)
    observed_device_count: int = Field(ge=0)
    truncated: bool

    @model_validator(mode="after")
    def coherent_count(self):
        if (self.observed_device_count < len(self.devices)
                or self.truncated != (self.observed_device_count > len(self.devices))
                or len({d.endpoint_id for d in self.devices}) != len(self.devices)):
            raise ValueError("Inconsistent endpoint enumeration.")
        return self


# ---------------------------------------------------------------------------
# Native Windows Core Audio Helpers (lazy loaded)
# ---------------------------------------------------------------------------

# Explicit fixture state; never selected because a native operation failed.
_MOCK_AUDIO_STATE = {"volume": 50, "muted": False}


def _get_mock_audio_path() -> str:
    import tempfile
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    clean_user = "".join(c for c in username if c.isalnum() or c in ("-", "_"))
    return os.path.join(tempfile.gettempdir(), f"pluma_mock_audio_{clean_user}.json")


def _load_mock_audio() -> Dict[str, Any]:
    import json
    p = _get_mock_audio_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "volume" in data and "muted" in data:
                    _MOCK_AUDIO_STATE.update(data)
                    return dict(_MOCK_AUDIO_STATE)
        except Exception:
            pass
    return dict(_MOCK_AUDIO_STATE)


def _save_mock_audio(level: Optional[int] = None, mute: Optional[bool] = None) -> None:
    import json
    if level is not None:
        _MOCK_AUDIO_STATE["volume"] = level
    if mute is not None:
        _MOCK_AUDIO_STATE["muted"] = mute
    p = _get_mock_audio_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(_MOCK_AUDIO_STATE, f)
    except Exception:
        pass


def _get_audio_endpoint_volume() -> Optional[Dict[str, Any]]:
    """Native read; emulation is an explicit test seam, never an error fallback."""
    if os.environ.get("PLUMA_EMULATE_AUDIO") == "1":
        state = _load_mock_audio()
        return dict(state, is_mock=True, endpoint_id="fixture:default", scalar=state["volume"] / 100.0)
    try:
        from pluma.adapters.audio import read_volume
        state = VolumeData.model_validate(read_volume())
        return None if state.is_mock else state.model_dump()
    except Exception:
        return None


def _set_audio_endpoint_volume(level: Optional[int] = None, mute: Optional[bool] = None,
                               expected_endpoint: Optional[str] = None, expected_state=None,
                               scalar_target=None) -> bool:
    """Native setter with endpoint identity; its caller still requires readback."""
    if os.environ.get("PLUMA_EMULATE_AUDIO") == "1":
        if expected_endpoint not in (None, "fixture:default"):
            return False
        if expected_state is not None and _get_audio_endpoint_volume() != expected_state:
            return False
        if scalar_target is not None:
            level = round(scalar_target * 100)
        _save_mock_audio(level=level, mute=mute)
        return True
    try:
        from pluma.adapters.audio import set_volume
        state = VolumeData.model_validate(set_volume(level, mute, expected_endpoint, expected_state, scalar_target))
        return (not state.is_mock and (expected_endpoint is None or state.endpoint_id == expected_endpoint)
                and (level is None or abs(state.volume - level) <= 2)
                and (mute is None or state.muted == mute))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Undo Builders
# ---------------------------------------------------------------------------

def _volume_prestate(action, args):
    current = _get_audio_endpoint_volume()
    if current is None:
        return None
    current = VolumeData.model_validate(current).model_dump()
    return {'action': action, 'guard_version': 1, 'before': current,
            'target': {'level': args['level']} if action == 'set_volume' else {'muted': action == 'mute'},
            'previous_volume': current['volume'], 'previous_muted': current['muted']}


def undo_builder_set_volume(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture previous volume level and mute status before changing volume."""
    return _volume_prestate('set_volume', args)


def undo_builder_mute(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture previous mute status before muting."""
    return _volume_prestate('mute', args)


def undo_builder_unmute(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture previous mute status before unmuting."""
    return _volume_prestate('unmute', args)


def _pending_prestate(tool, context):
    if context is None:
        return None
    for record in reversed(getattr(context, 'undo_stack', [])):
        if record.get('action') == 'pending_mutation' and record.get('tool') == tool:
            return record['pre_state']
    raise ValueError('Durable audio intent is unavailable.')


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def _check_cancel(context):
    token = getattr(context, "cancellation_token", None)
    if token is not None:
        token.raise_if_cancelled()


def _audio_change(tool, args, context):
    _check_cancel(context)
    previous = _get_audio_endpoint_volume()
    if previous is None:
        return ToolResult.failure(tool, "Audio endpoint state could not be read.", "AUDIO_READ_FAILED")
    try:
        captured = _pending_prestate(tool, context)
        if captured is not None and (captured.get('guard_version') != 1 or captured['before'] != previous
                or captured['action'] != tool
                or captured['target'] != ({'level': args['level']} if tool == 'set_volume' else {'muted': tool == 'mute'})):
            raise ValueError('Audio endpoint changed after capture.')
    except Exception:
        return ToolResult.failure(tool, 'Captured audio state changed or is unavailable.', 'AUDIO_PRESTATE_CONFLICT')
    level = args["level"] if tool == "set_volume" else None
    mute = None if tool == "set_volume" else tool == "mute"
    _check_cancel(context)
    if not _set_audio_endpoint_volume(level=level, mute=mute, expected_endpoint=previous["endpoint_id"], expected_state=previous):
        return ToolResult.failure(tool, "Audio endpoint change could not be verified.", "AUDIO_SET_FAILED")
    _check_cancel(context)
    current = _get_audio_endpoint_volume()
    if (current is None or current["endpoint_id"] != previous["endpoint_id"]
            or current["is_mock"] != previous["is_mock"]
            or (level is not None and (abs(current["volume"] - level) > 2
                                      or current["muted"] != previous["muted"]))
            or (mute is not None and (current["muted"] != mute or current['scalar'] != previous['scalar']))):
        return ToolResult.failure(tool, "Audio endpoint readback did not confirm the change.", "AUDIO_READBACK_FAILED")
    data = {"observed_state": current}
    if level is not None:
        data.update(target_level=level, actual_level=current["volume"])
        message = f"Set volume to {current['volume']}%."
    else:
        data["muted"] = current["muted"]
        message = "Muted master audio." if mute else "Unmuted master audio."
    if current["is_mock"]:
        message = "Fixture audio state changed."
    record = dict(captured or _volume_record(tool, args, previous), after=current)
    return ToolResult.success(tool, data=data, factual_message=message, verified=True,
        undo_record=record,
        adapter_used="emulated" if current["is_mock"] else "native_api",
        verify_detail=VerifyResult(ok=True, method="api", detail="Endpoint identity and state read back.")).model_copy(
            update={'private_context': {'audio_receipt': record}})


def _volume_record(tool, args, previous):
    return {'action': tool, 'guard_version': 1, 'before': previous,
            'target': {'level': args['level']} if tool == 'set_volume' else {'muted': tool == 'mute'},
            'previous_volume': previous['volume'], 'previous_muted': previous['muted']}


def _coherent_volume_receipt(record):
    before = VolumeData.model_validate(record['before']).model_dump()
    after = VolumeData.model_validate(record['after']).model_dump()
    if (record.get('guard_version') != 1 or before['endpoint_id'] != after['endpoint_id']
            or before['is_mock'] != after['is_mock']):
        return False
    if record['action'] == 'set_volume':
        target = SetVolumeArgs.model_validate(record['target']).level
        return abs(after['volume'] - target) <= 2 and before['muted'] == after['muted']
    return (record['action'] in ('mute', 'unmute')
            and record['target'] == {'muted': record['action'] == 'mute'}
            and after['muted'] == (record['action'] == 'mute') and before['scalar'] == after['scalar'])


def execute_set_volume(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _audio_change("set_volume", args, task_context)


def execute_mute(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _audio_change("mute", args, task_context)


def execute_unmute(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _audio_change("unmute", args, task_context)


def execute_get_volume(args, task_context=None, *, tool="get_volume"):
    _check_cancel(task_context)
    current = _get_audio_endpoint_volume()
    if current is None:
        return ToolResult.failure(tool, "Audio endpoint state could not be read.", "AUDIO_READ_FAILED")
    _check_cancel(task_context)
    message = ("Fixture audio state read." if current["is_mock"] else
               f"Volume is at {current['volume']}% ({'muted' if current['muted'] else 'unmuted'}).")
    return ToolResult.success(tool, data=current, factual_message=message, verified=True,
        adapter_used="emulated" if current["is_mock"] else "native_api",
        verify_detail=VerifyResult(ok=True, method="api", detail=(
            "Fixture endpoint state read." if current["is_mock"] else "Native endpoint state read.")))


def execute_get_volume_status(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return execute_get_volume(args, task_context, tool="get_volume_status")


def execute_list_audio_devices(args, task_context=None):
    from pluma.adapters.audio import list_devices
    from pluma.core.cancellation import TaskCancelledError
    try:
        _check_cancel(task_context)
        data = AudioDevicesData.model_validate(list_devices(args["max_entries"], task_context)).model_dump()
        _check_cancel(task_context)
    except TaskCancelledError:
        return ToolResult.failure("list_audio_devices", "Audio device inspection was stopped.", "TASK_CANCELLED")
    except Exception:
        return ToolResult.failure("list_audio_devices", "Audio devices could not be read.", "AUDIO_DEVICES_READ_FAILED")
    return ToolResult.success("list_audio_devices", data=data,
        factual_message=f"Observed {len(data['devices'])} audio devices.", verified=True, adapter_used="native_api",
        verify_detail=VerifyResult(ok=True, method="api", detail="Native endpoint identities and states read back."))


def _valid_volume_result(result, state):
    current = VolumeData.model_validate(state)
    return (result.ok and result.verified and isinstance(result.verify_detail, VerifyResult)
            and result.verify_detail.ok and result.verify_detail.method == "api"
            and result.adapter_used == ("emulated" if current.is_mock else "native_api")
            and (not current.is_mock or os.environ.get("PLUMA_EMULATE_AUDIO") == "1"))


def verify_volume_observation(result):
    try:
        valid = _valid_volume_result(result, result.data)
    except (ValueError, ValidationError):
        valid = False
    return VerifyResult(ok=bool(valid), method="api", detail="Endpoint volume observation validated." if valid
                        else "Endpoint volume observation was not established.")


def _verify_audio_change(result):
    try:
        state = result.data["observed_state"]
        valid = _valid_volume_result(result, state)
        receipt = result.private_context['audio_receipt']
        valid = (valid and _coherent_volume_receipt(receipt) and receipt['action'] == result.tool
                 and receipt['after'] == state and _get_audio_endpoint_volume() == state)
        if result.tool == "set_volume":
            target = SetVolumeArgs(level=result.data["target_level"]).level
            valid = valid and result.data["actual_level"] == state["volume"] and abs(state["volume"] - target) <= 2
        else:
            valid = valid and result.tool in ("mute", "unmute") and state["muted"] == (result.tool == "mute")
            valid = valid and result.data["muted"] == state["muted"]
    except (KeyError, ValueError, TypeError):
        valid = False
    return VerifyResult(ok=bool(valid), method="api", detail="Endpoint change observation validated." if valid
                        else "Endpoint change observation was not established.")


verify_set_volume = _verify_audio_change
verify_mute = _verify_audio_change
verify_unmute = _verify_audio_change


def verify_audio_devices(result):
    try:
        AudioDevicesData.model_validate(result.data)
        valid = (result.ok and result.verified and result.adapter_used == "native_api"
                 and isinstance(result.verify_detail, VerifyResult) and result.verify_detail.ok)
    except ValueError:
        valid = False
    return VerifyResult(ok=bool(valid), method="api", detail="Native endpoint enumeration validated." if valid
                        else "Native endpoint enumeration was not established.")


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

AUDIO_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="set_volume",
        description="Set the system master audio volume (0 to 100%).",
        args_schema=SetVolumeArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_set_volume,
        verifier=verify_set_volume,
        undo_builder=undo_builder_set_volume,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="mute",
        description="Mute system master audio output.",
        args_schema=MuteArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_mute,
        verifier=verify_mute,
        undo_builder=undo_builder_mute,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="unmute",
        description="Unmute system master audio output.",
        args_schema=UnmuteArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_unmute,
        verifier=verify_unmute,
        undo_builder=undo_builder_unmute,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="get_volume_status",
        description="Read current system volume level and mute state.",
        args_schema=GetVolumeStatusArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_get_volume_status,
        verifier=verify_volume_observation,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]

# Exact master catalog names; get_volume_status remains a compatibility tool.
AUDIO_TOOL_SPECS.extend([
    ToolSpec(name="get_volume", description="Read the native multimedia output endpoint volume and mute state.",
             args_schema=GetVolumeStatusArgs, risk_class=RiskClass.READ, timeout_s=5, process_isolated=True,
             executor=execute_get_volume, verifier=verify_volume_observation),
    ToolSpec(name="list_audio_devices", description="List bounded native capture/render audio endpoint identities, names and states.",
             args_schema=ListAudioDevicesArgs, risk_class=RiskClass.READ, timeout_s=5, process_isolated=True,
             executor=execute_list_audio_devices, verifier=verify_audio_devices),
])


class DefaultAudioArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    endpoint_id: str = Field(min_length=1, max_length=1024, pattern=r'^[^\x00-\x1f]+$')
    flow: Literal['render', 'capture']
    role: Literal['console', 'multimedia', 'communications']


class DefaultAudioState(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    endpoint_id: str = Field(min_length=1, max_length=1024)
    flow: Literal['render', 'capture']
    role: Literal['console', 'multimedia', 'communications']


def undo_builder_default(args):
    from pluma.adapters.audio import read_default
    state = DefaultAudioState.model_validate(read_default(args['flow'], args['role'])).model_dump()
    return {'action': 'set_default_audio_device', 'guard_version': 1, 'before': state,
            'target': DefaultAudioArgs.model_validate(args).model_dump()}


def execute_default(args, context=None):
    from pluma.adapters.audio import set_default
    try:
        _check_cancel(context)
        captured = _pending_prestate('set_default_audio_device', context)
        if captured is None or captured.get('guard_version') != 1 or captured['target'] != args:
            raise ValueError('Durable default audio intent is unavailable.')
        after = DefaultAudioState.model_validate(set_default(args['flow'], args['role'],
            args['endpoint_id'], captured['before'])).model_dump()
        _check_cancel(context)
        record = dict(captured, after=after)
        result = ToolResult.success('set_default_audio_device', data=after, verified=False,
            factual_message='Default audio endpoint selection verified.', adapter_used='native_api', undo_record=record).model_copy(
                update={'private_context': {'audio_receipt': record}})
        check = verify_default(result)
        return result.model_copy(update={'verified': check.ok, 'verify_detail': check})
    except Exception:
        return ToolResult.failure('set_default_audio_device', 'Default audio endpoint was refused or not verified.', 'AUDIO_DEFAULT_UNVERIFIED')


def verify_default(result):
    from pluma.adapters.audio import read_default
    try:
        state = DefaultAudioState.model_validate(result.data).model_dump()
        receipt = result.private_context['audio_receipt']
        valid = (result.ok and result.adapter_used == 'native_api' and receipt.get('guard_version') == 1
            and receipt['action'] == 'set_default_audio_device' and receipt['after'] == receipt['target'] == state
            and read_default(state['flow'], state['role']) == state)
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_audio_default', detail=(
        'Exact endpoint/direction/role read back.' if valid else 'Default audio endpoint was not verified.'))


AUDIO_TOOL_SPECS.append(ToolSpec(name='set_default_audio_device',
    description='Set an exact active endpoint for one explicit direction and role.',
    args_schema=DefaultAudioArgs, risk_class=RiskClass.MEDIUM, timeout_s=5, process_isolated=True,
    executor=execute_default, verifier=verify_default, undo_builder=undo_builder_default,
    adapter_priority=[AdapterPriority.NATIVE_API]))


def verify_audio_restored(record):
    if record.get('guard_version') != 1 or 'after' not in record:
        return False
    if record['action'] == 'set_default_audio_device':
        from pluma.adapters.audio import read_default
        before = DefaultAudioState.model_validate(record['before']).model_dump()
        return read_default(before['flow'], before['role']) == before
    before = VolumeData.model_validate(record['before']).model_dump()
    return _get_audio_endpoint_volume() == before


def restore_audio(record):
    if record.get('guard_version') != 1 or 'after' not in record:
        raise ValueError('Audio undo lacks a verified guarded receipt.')
    action = record['action']
    if action == 'set_default_audio_device':
        from pluma.adapters.audio import read_default, set_default
        before = DefaultAudioState.model_validate(record['before']).model_dump()
        after = DefaultAudioState.model_validate(record['after']).model_dump()
        if after != record['target'] or (before['flow'], before['role']) != (after['flow'], after['role']):
            raise ValueError('Audio undo receipt is inconsistent.')
        if read_default(after['flow'], after['role']) != after:
            raise ValueError('Default audio changed after this action.')
        set_default(before['flow'], before['role'], before['endpoint_id'], after)
    elif action in ('set_volume', 'mute', 'unmute'):
        if not _coherent_volume_receipt(record):
            raise ValueError('Audio undo receipt is inconsistent.')
        before = VolumeData.model_validate(record['before']).model_dump()
        after = VolumeData.model_validate(record['after']).model_dump()
        if before['endpoint_id'] != after['endpoint_id'] or before['is_mock'] != after['is_mock']:
            raise ValueError('Audio undo endpoint identity is inconsistent.')
        if _get_audio_endpoint_volume() != after:
            raise ValueError('Audio endpoint/state changed after this action.')
        if not _set_audio_endpoint_volume(mute=before['muted'], expected_endpoint=before['endpoint_id'],
                                         expected_state=after, scalar_target=before['scalar']):
            raise ValueError('Audio undo was refused.')
    else:
        raise ValueError('Audio inverse is not registered.')
    if not verify_audio_restored(record):
        raise ValueError('Audio undo readback failed.')
