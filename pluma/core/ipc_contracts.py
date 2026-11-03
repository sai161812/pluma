"""Version 1 typed request/acknowledgement/readback messages for local UI IPC."""
from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from uuid import UUID

from pydantic import (BaseModel, ConfigDict, Field, StrictBool, StrictInt,
                      StrictStr, ValidationError, model_validator)


from pluma.config.settings_contract import FIELDS

PROTOCOL_VERSION = 1


class _Envelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1]
    message_type: StrictStr


class SubmitTextV1(_Envelope):
    message_type: Literal["submit_text"]
    request_id: StrictStr
    text: StrictStr = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def canonical_request_id(self):
        try:
            if str(UUID(self.request_id)) != self.request_id:
                raise ValueError
        except (ValueError, AttributeError):
            raise ValueError("request_id must be a canonical lowercase UUID") from None
        if not self.text.strip():
            raise ValueError("text must not be whitespace-only")
        return self


class TerminalReadbackRequestV1(_Envelope):
    message_type: Literal["terminal_readback"]
    request_id: StrictStr
    task_id: StrictStr

    @model_validator(mode="after")
    def canonical_ids(self):
        for name in ("request_id", "task_id"):
            value = getattr(self, name)
            try:
                if str(UUID(value)) != value:
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError(f"{name} must be a canonical lowercase UUID") from None
        return self


class StopRequestV1(_Envelope):
    message_type: Literal["stop"]
    request_id: StrictStr
    task_id: Optional[StrictStr] = None
    submission_request_id: Optional[StrictStr] = None

    @model_validator(mode="after")
    def canonical_ids(self):
        if self.task_id is not None and self.submission_request_id is not None:
            raise ValueError("submission fencing belongs to global STOP")
        for name in ("request_id", "task_id", "submission_request_id"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                if str(UUID(value)) != value:
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError(f"{name} must be a canonical lowercase UUID") from None
        return self


class SettingsQueryV1(_Envelope):
    message_type: Literal["settings_query"]
    request_id: StrictStr

    @model_validator(mode="after")
    def canonical_request_id(self):
        _validate_id("request_id", self.request_id)
        return self


class SettingsEditQueryV1(_Envelope):
    message_type: Literal["settings_edit_query"]
    request_id: StrictStr

    @model_validator(mode="after")
    def canonical_id(self):
        _validate_id("request_id", self.request_id)
        return self


from pluma.config.settings_contract import SettingsSaveArgs, SettingsValues


class SettingsSaveV1(SettingsSaveArgs):
    protocol_version: Literal[1]
    message_type: Literal["settings_save"]
    request_id: StrictStr

    @model_validator(mode="after")
    def canonical_id(self):
        _validate_id("request_id", self.request_id)
        return self


class SettingsEditSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = 1
    message_type: Literal["settings_edit_snapshot"] = "settings_edit_snapshot"
    request_id: StrictStr
    revision: StrictStr = Field(pattern=r"^(?:absent|[0-9a-f]{64})$")
    persisted: SettingsValues
    effective: SettingsValues
    hotkeys_registered: StrictBool = False
    previous_revision: Optional[StrictStr] = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    editable_fields: list[StrictStr] = Field(default_factory=lambda: list(FIELDS))
    restart_fields: list[StrictStr] = Field(max_length=15)


class VoiceQueryV1(_Envelope):
    message_type: Literal["voice_query"]
    request_id: StrictStr
    stream_id: Optional[StrictStr] = None
    voice_id: Optional[StrictStr] = None

    @model_validator(mode="after")
    def ids(self):
        for name in ("request_id", "stream_id", "voice_id"):
            value = getattr(self, name)
            if value is not None:
                _validate_id(name, value)
        if self.voice_id is not None and self.stream_id is None:
            raise ValueError("A voice generation requires its stream identity.")
        return self


class VoiceMeterV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    amplitude: float = Field(ge=0, le=1)
    bands: list[float] = Field(min_length=32, max_length=32)
    speech_active: StrictBool
    silence_progress: float = Field(ge=0, le=1)
    sample_sequence: StrictInt = Field(default=0, ge=0)

    @model_validator(mode="after")
    def bounded(self):
        import math
        if any(not math.isfinite(x) or not 0 <= x <= 1 for x in self.bands):
            raise ValueError("Invalid measured spectrum")
        return self


class VoiceViewV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    voice_id: StrictStr
    task_id: StrictStr
    task_request_id: Optional[StrictStr]
    phase: Literal["STARTING", "LISTENING", "DECODING", "COMMITTED", "CLARIFICATION",
                   "EMPTY", "ERROR", "CANCELLED", "TIMED_OUT"]
    code: Optional[Literal["CAPTURE_DENIED", "CAPTURE_UNAVAILABLE", "VOICE_FAILED",
                           "LOW_CONFIDENCE_MATERIAL_TARGET"]]
    capture_active: Optional[StrictBool]
    boundary_complete: Optional[StrictBool]
    recognition_id: Optional[StrictStr]
    recognition_sequence: StrictInt = Field(ge=0, le=128)
    text: StrictStr
    meter: Optional[VoiceMeterV1] = None

    @model_validator(mode="after")
    def consistent(self):
        for name in ("voice_id", "task_id", "task_request_id", "recognition_id"):
            value = getattr(self, name)
            if value is not None:
                _validate_id(name, value)
        if ((self.phase == "COMMITTED") != (self.task_request_id is not None)
                or self.phase not in {"DECODING", "COMMITTED"} and self.text
                or len(self.text.encode("utf-8")) > 16384
                or self.phase != "LISTENING" and (self.capture_active is not None or self.boundary_complete is not None)
                or self.phase != "LISTENING" and self.meter is not None
                or self.recognition_id is None and self.recognition_sequence != 0
                or (self.phase == "CLARIFICATION") != (self.code == "LOW_CONFIDENCE_MATERIAL_TARGET")
                or self.phase == "ERROR" and self.code not in {"CAPTURE_DENIED", "CAPTURE_UNAVAILABLE", "VOICE_FAILED"}
                or self.phase not in {"ERROR", "CLARIFICATION"} and self.code is not None):
            raise ValueError("Inconsistent voice evidence")
        return self


class VoiceSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["voice_snapshot"] = "voice_snapshot"
    request_id: StrictStr
    stream_id: StrictStr
    reset_required: StrictBool
    voice: Optional[VoiceViewV1]

    @model_validator(mode="after")
    def ids(self):
        _validate_id("request_id", self.request_id)
        _validate_id("stream_id", self.stream_id)
        return self


class HistoryQueryV1(_Envelope):
    message_type: Literal["history_query"]
    request_id: StrictStr
    task_id: Optional[StrictStr] = None
    limit: StrictInt = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def canonical_ids(self):
        _validate_id("request_id", self.request_id)
        if self.task_id is not None:
            _validate_id("task_id", self.task_id)
        return self


class HistoryPageQueryV1(_Envelope):
    message_type: Literal["history_page_query"]
    request_id: StrictStr
    search: StrictStr = Field(default="", max_length=256)
    before_task_id: Optional[StrictStr] = None
    limit: StrictInt = Field(default=20, ge=1, le=20)

    @model_validator(mode="after")
    def ids(self):
        _validate_id("request_id", self.request_id)
        if self.before_task_id is not None:
            _validate_id("before_task_id", self.before_task_id)
        return self


class SavedHistoryTaskV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: StrictStr
    request_id: StrictStr
    input_mode: Literal["text", "voice"]
    command_text: Optional[StrictStr]
    created_at: StrictStr
    started_at: Optional[StrictStr]
    completed_at: Optional[StrictStr]
    final_state: Optional[Literal["CREATED", "RUNNING", "STOPPING", "ROLLING_BACK", "SUCCEEDED", "FAILED",
                                  "STOPPED", "STOPPED_WITH_RESIDUAL", "DEFERRED", "ABORTED_BY_CRASH"]]
    route: Optional[Literal["FAST", "SMART", "SCREEN", "DEEP"]]
    stop_reason: Optional[StrictStr]
    error_code: Optional[StrictStr]

    @model_validator(mode="after")
    def bounded(self):
        _validate_id("task_id", self.task_id)
        _validate_id("request_id", self.request_id)
        if self.command_text is not None and len(self.command_text.encode("utf-8")) > 8192:
            raise ValueError("Oversized saved command.")
        return self


class HistoryPageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["history_page"] = "history_page"
    request_id: StrictStr
    before_task_id: Optional[StrictStr]
    tasks: list[SavedHistoryTaskV1] = Field(max_length=20)
    has_more: StrictBool
    next_before_task_id: Optional[StrictStr]

    @model_validator(mode="after")
    def consistent(self):
        _validate_id("request_id", self.request_id)
        for value in (self.before_task_id, self.next_before_task_id):
            if value is not None:
                _validate_id("cursor", value)
        if (self.has_more != (self.next_before_task_id is not None)
                or self.has_more and (not self.tasks or self.next_before_task_id != self.tasks[-1].task_id)
                or len({item.task_id for item in self.tasks}) != len(self.tasks)):
            raise ValueError("Inconsistent saved history page.")
        return self


class TaskDetailQueryV1(_Envelope):
    message_type: Literal["task_detail_query"]
    request_id: StrictStr
    task_id: StrictStr
    after_action_id: StrictInt = Field(default=0, ge=0, le=9223372036854775807)
    limit: StrictInt = Field(default=10, ge=1, le=10)

    @model_validator(mode="after")
    def ids(self):
        _validate_id("request_id", self.request_id)
        _validate_id("task_id", self.task_id)
        return self


from pluma.memory.selection_contract import UndoSelection as UndoSelectionV1


class UndoSubmitV1(_Envelope):
    message_type: Literal["undo_submit"]
    request_id: StrictStr
    selection: UndoSelectionV1

    @model_validator(mode="after")
    def ids(self):
        _validate_id("request_id", self.request_id)
        return self


class HistoryFolderSubmitV1(_Envelope):
    message_type: Literal["history_folder_submit"]
    request_id: StrictStr
    task_id: StrictStr
    action_id: StrictInt = Field(ge=1, le=9223372036854775807)
    location: Literal["current", "target"] = "current"

    @model_validator(mode="after")
    def ids(self):
        _validate_id("request_id", self.request_id)
        _validate_id("task_id", self.task_id)
        return self


class SavedActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)
    action_id: StrictInt = Field(ge=1)
    step_index: StrictInt = Field(ge=0)
    tool: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    arguments: StrictStr = Field(max_length=65536)
    adapter: Optional[StrictStr]
    risk: Literal["READ", "LOW", "MEDIUM", "HIGH", "ADMIN", "DENY"]
    approval: Optional[StrictStr]
    started_at: Optional[StrictStr]
    ended_at: Optional[StrictStr]
    duration_ms: Optional[float] = Field(ge=0)
    factual_message: Optional[StrictStr]
    policy_reason: Optional[StrictStr]
    error_code: Optional[StrictStr]
    verified: StrictBool
    verification_method: Optional[StrictStr]
    verification_detail: Optional[StrictStr]
    undo_available: StrictBool
    rollback_attempted: StrictBool
    rollback_ok: Optional[StrictBool]
    rollback_code: Optional[StrictStr]
    claim_state: Optional[Literal["claimed", "verified", "unverified"]]
    effect_state: Optional[Literal["committed", "unknown", "not_executed"]]
    conflict_current: Optional[StrictStr]
    conflict_target: Optional[StrictStr]
    selection: Optional[UndoSelectionV1]


class TaskDetailV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["task_detail"] = "task_detail"
    request_id: StrictStr
    task_id: StrictStr
    task_request_id: StrictStr
    original_transcript: Optional[StrictStr]
    active_process: Optional[StrictStr]
    active_window: Optional[StrictStr]
    cleanup_complete: Optional[StrictBool]
    cleanup_unresolved: Optional[StrictInt] = Field(ge=0, le=512)
    residual_codes: list[StrictStr] = Field(max_length=512)
    actions: list[SavedActionV1] = Field(max_length=10)
    has_more: StrictBool
    next_action_id: StrictInt = Field(ge=0)


class ActivityQueryV1(_Envelope):
    message_type: Literal["activity_query"]
    request_id: StrictStr
    task_id: StrictStr
    after_action_id: StrictInt = Field(default=0, ge=0, le=9223372036854775807)
    limit: StrictInt = Field(default=25, ge=1, le=100)

    @model_validator(mode="after")
    def canonical_ids(self):
        _validate_id("request_id", self.request_id)
        _validate_id("task_id", self.task_id)
        return self


class ActionDetailQueryV1(_Envelope):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    message_type: Literal["action_detail_query"]
    request_id: StrictStr
    task_id: StrictStr
    action_id: StrictInt = Field(ge=1, le=9223372036854775807)

    @model_validator(mode="after")
    def canonical_ids(self):
        _validate_id("request_id", self.request_id)
        _validate_id("task_id", self.task_id)
        return self


class ActionVerificationQueryV1(ActionDetailQueryV1):
    message_type: Literal["action_verification_query"]


class ActionVerificationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["action_verification"] = "action_verification"
    request_id: StrictStr
    task_id: StrictStr
    task_request_id: StrictStr
    action_id: StrictInt = Field(gt=0)
    tool: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    verified: Optional[StrictBool]
    method: Optional[StrictStr] = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
    detail: Optional[StrictStr]

    @model_validator(mode="after")
    def consistent(self):
        for key in ("request_id", "task_id", "task_request_id"):
            _validate_id(key, getattr(self, key))
        if ((self.verified is None) != (self.method is None) or (self.method is None) != (self.detail is None)
                or self.detail is not None and len(self.detail.encode("utf-8")) > 1024):
            raise ValueError("Invalid verification evidence")
        return self


class RuntimeQueryV1(_Envelope):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    message_type: Literal["runtime_query"]
    request_id: StrictStr

    @model_validator(mode="after")
    def canonical_id(self):
        _validate_id("request_id", self.request_id)
        return self


class RuntimeTaskV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: StrictStr
    task_request_id: StrictStr
    state: Literal["CREATED", "RUNNING", "STOPPING", "ROLLING_BACK"]
    elapsed_ms: StrictInt = Field(ge=0)
    plan_revision: StrictInt = Field(ge=0)
    step: Optional[StrictInt] = Field(ge=1)
    total: Optional[StrictInt] = Field(ge=1)
    tool: Optional[StrictStr] = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    risk: Optional[Literal["READ", "LOW", "MEDIUM", "HIGH", "ADMIN", "DENY"]]
    phase: Optional[Literal["DISPATCHING", "EXECUTING", "VERIFYING", "RECORDING"]]
    tool_elapsed_ms: Optional[StrictInt] = Field(ge=0)
    arguments: Optional[StrictStr]
    rollback_step: Optional[StrictInt] = Field(ge=1)
    rollback_total: Optional[StrictInt] = Field(ge=1)
    rollback_recipe: Optional[StrictStr] = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")

    @model_validator(mode="after")
    def consistent(self):
        _validate_id("task_id", self.task_id)
        _validate_id("task_request_id", self.task_request_id)
        if (self.step is not None and (self.total is None or self.step > self.total)
                or (self.tool is None) != (self.phase is None) or (self.tool is None) != (self.risk is None)
                or self.phase == "DISPATCHING" and self.tool_elapsed_ms is not None
                or self.phase == "EXECUTING" and self.tool_elapsed_ms is None
                or self.arguments is not None and len(self.arguments.encode("utf-8")) > 1024
                or self.rollback_step is not None and (self.rollback_total is None or self.rollback_step > self.rollback_total)):
            raise ValueError("Inconsistent live task evidence")
        return self


class WorkerTerminationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: StrictStr
    task_request_id: StrictStr
    pid: StrictInt = Field(gt=0)
    creation_time: StrictInt = Field(gt=0)
    exit_code: StrictInt
    command_class: Literal["tool_worker"]

    @model_validator(mode="after")
    def ids(self):
        _validate_id("task_id", self.task_id)
        _validate_id("task_request_id", self.task_request_id)
        return self


class RuntimeSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["runtime_snapshot"] = "runtime_snapshot"
    request_id: StrictStr
    tasks: list[RuntimeTaskV1] = Field(max_length=256)
    terminations: list[WorkerTerminationV1] = Field(max_length=256)

    @model_validator(mode="after")
    def consistent(self):
        _validate_id("request_id", self.request_id)
        ids = [item.task_id for item in self.tasks]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate runtime task")
        return self


class ActionDetailV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["action_detail"] = "action_detail"
    request_id: StrictStr
    task_id: StrictStr
    task_request_id: StrictStr
    action_id: StrictInt = Field(ge=1, le=9223372036854775807)
    tool: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    factual_message: Optional[StrictStr]
    error_code: Optional[StrictStr] = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    policy_reason: Optional[StrictStr]

    @model_validator(mode="after")
    def bounded(self):
        for name in ("request_id", "task_id", "task_request_id"):
            _validate_id(name, getattr(self, name))
        for text in (self.factual_message, self.policy_reason):
            if text is not None and len(text.encode("utf-8")) > 1024:
                raise ValueError("Oversized action presentation")
        return self


class ActivityActionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    action_id: StrictInt = Field(ge=1)
    step_index: StrictInt = Field(ge=0, le=2147483647)
    tool: StrictStr = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    risk: Literal["READ", "LOW", "MEDIUM", "HIGH", "ADMIN", "DENY"]
    verified: StrictBool
    error_recorded: StrictBool
    policy_denied: StrictBool
    undo_available: StrictBool
    rollback_attempted: StrictBool
    rollback_ok: Optional[StrictBool]

    @model_validator(mode="after")
    def consistent_rollback(self):
        if not self.rollback_attempted and self.rollback_ok is not None:
            raise ValueError("Rollback result requires a recorded attempt")
        return self


class ActivityCleanupV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    complete: StrictBool
    unresolved_count: StrictInt = Field(ge=0, le=512)

    @model_validator(mode="after")
    def consistent(self):
        if self.complete != (self.unresolved_count == 0):
            raise ValueError("Inconsistent cleanup summary")
        return self


class ActivityPageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["activity_page"] = "activity_page"
    request_id: StrictStr
    task_id: StrictStr
    task_request_id: StrictStr
    saved_state: Optional[Literal["CREATED", "RUNNING", "STOPPING", "ROLLING_BACK", "SUCCEEDED",
                                  "FAILED", "STOPPED", "STOPPED_WITH_RESIDUAL", "ABORTED_BY_CRASH"]]
    route: Optional[Literal["FAST", "SMART", "SCREEN", "DEEP"]]
    actions: list[ActivityActionV1] = Field(max_length=100)
    next_action_id: StrictInt = Field(ge=0, le=9223372036854775807)
    has_more: StrictBool
    cleanup: Optional[ActivityCleanupV1]

    @model_validator(mode="after")
    def correlation(self):
        for name in ("request_id", "task_id", "task_request_id"):
            _validate_id(name, getattr(self, name))
        ids = [action.action_id for action in self.actions]
        if ids != sorted(set(ids)) or ids and self.next_action_id != ids[-1] or self.has_more and not ids:
            raise ValueError("Inconsistent action page")
        return self


class SubmissionAckV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["submission_ack"] = "submission_ack"
    request_id: StrictStr
    accepted: StrictBool
    task_id: Optional[StrictStr] = None
    error_code: Optional[StrictStr] = None
    message: StrictStr

    @model_validator(mode="after")
    def consistent_ack(self):
        if self.accepted and (self.task_id is None or self.error_code is not None):
            raise ValueError("acknowledgement fields are inconsistent")
        if not self.accepted and (self.task_id is not None or self.error_code is None):
            raise ValueError("a refusal requires an error code and no task ID")
        return self


class TerminalReadbackV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["terminal_readback"] = "terminal_readback"
    request_id: StrictStr
    task_id: StrictStr
    terminal: StrictBool
    final_state: StrictStr
    completion_verified: StrictBool
    terminal_persisted: Optional[StrictBool]
    has_residual: StrictBool
    route: Optional[StrictStr] = None
    message: StrictStr
    duration_ms: Optional[float] = None

    @model_validator(mode="after")
    def consistency(self):
        if not self.terminal and self.terminal_persisted is not None:
            raise ValueError("pending work cannot claim terminal persistence")
        if self.completion_verified and not self.terminal:
            raise ValueError("pending work cannot claim completion verification")
        return self


class ProtocolErrorV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["protocol_error"] = "protocol_error"
    error_code: StrictStr
    message: StrictStr


class SettingsSnapshotV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, protected_namespaces=())
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["settings_snapshot"] = "settings_snapshot"
    request_id: StrictStr
    submission_stop_fence: StrictBool = False
    text_hotkey: StrictStr
    stop_hotkey: StrictStr
    voice_hotkey: StrictStr
    max_plan_steps: StrictInt
    default_tool_timeout_seconds: StrictInt
    model_idle_unload_seconds: StrictInt
    stt_idle_unload_seconds: StrictInt
    ocr_idle_unload_seconds: StrictInt
    allow_short_warm_grace: StrictBool
    voice_required: StrictBool
    activation_default: StrictStr
    wake_phrase_enabled: StrictBool
    save_audio: StrictBool
    persist_screenshots: StrictBool
    ocr_enabled: StrictBool
    uia_first: StrictBool
    model_runtime: StrictStr
    model_profile: StrictStr
    planner_model_path: Optional[StrictStr] = None
    stt_model_path: Optional[StrictStr] = None
    confirm_high_risk: StrictBool
    redact_sensitive_logs: StrictBool
    activity_view_enabled: StrictBool

    @model_validator(mode="after")
    def canonical_request_id(self):
        _validate_id("request_id", self.request_id)
        return self


class TaskSummaryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    task_id: StrictStr
    request_id: StrictStr
    input_mode: Literal["text", "voice"]
    command_text: StrictStr
    created_at: StrictStr
    started_at: Optional[StrictStr] = None
    completed_at: Optional[StrictStr] = None
    final_state: Optional[StrictStr] = None
    route: Optional[StrictStr] = None
    stop_reason: Optional[StrictStr] = None
    error_code: Optional[StrictStr] = None

    @model_validator(mode="after")
    def canonical_ids(self):
        _validate_id("task_id", self.task_id)
        _validate_id("request_id", self.request_id)
        return self


class ActionHistoryV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    action_id: StrictInt = Field(ge=1)
    step_index: StrictInt = Field(ge=0)
    tool: StrictStr
    adapter: Optional[StrictStr] = None
    risk: StrictStr
    approval_state: Optional[StrictStr] = None
    started_at: StrictStr
    ended_at: Optional[StrictStr] = None
    duration_ms: Optional[float] = Field(default=None, ge=0)
    arguments: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    verified: StrictBool
    verification: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None
    undo_available: StrictBool
    rollback_attempted: StrictBool
    rollback_ok: Optional[StrictBool] = None
    rollback_result: Optional[Dict[str, Any]] = None


class HistoryReplyV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = PROTOCOL_VERSION
    message_type: Literal["history_reply"] = "history_reply"
    request_id: StrictStr
    task_id: Optional[StrictStr] = None
    tasks: list[TaskSummaryV1] = Field(max_length=100)
    actions: list[ActionHistoryV1] = Field(max_length=100)

    @model_validator(mode="after")
    def correlation(self):
        _validate_id("request_id", self.request_id)
        if self.task_id is not None:
            _validate_id("task_id", self.task_id)
            if len(self.tasks) > 1 or any(task.task_id != self.task_id for task in self.tasks):
                raise ValueError("task history response does not match its task ID")
        elif self.actions:
            raise ValueError("recent task history cannot contain unscoped actions")
        return self


class _ClientRequest(_Envelope):
    request_id: StrictStr
    client_id: StrictStr

    @model_validator(mode="after")
    def canonical_ids(self):
        for name in ("request_id", "client_id", "task_id", "confirmation_id"):
            if hasattr(self, name):
                _validate_id(name, getattr(self, name))
        return self


class ConfirmationQueryV1(_ClientRequest):
    message_type: Literal["confirmation_query"]


class ConfirmationDecisionV1(_ClientRequest):
    message_type: Literal["confirmation_decision"]
    task_id: StrictStr
    confirmation_id: StrictStr
    binding: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    approved: StrictBool


class ConfirmationDisconnectV1(_ClientRequest):
    message_type: Literal["confirmation_disconnect"]


class EventsQueryV1(_Envelope):
    message_type: Literal["events_query"]
    request_id: StrictStr
    stream_id: Optional[StrictStr] = None
    after_sequence: StrictInt = Field(default=0, ge=0, le=9223372036854775807)
    limit: StrictInt = Field(default=100, ge=1, le=100)

    @model_validator(mode="after")
    def canonical_ids(self):
        _validate_id("request_id", self.request_id)
        if self.stream_id is not None:
            _validate_id("stream_id", self.stream_id)
        elif self.after_sequence:
            raise ValueError("A cursor requires its stream identity.")
        return self


class _Reply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    protocol_version: Literal[1] = 1
    request_id: StrictStr


class ConfirmationViewV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    confirmation_id: StrictStr
    task_id: StrictStr
    binding: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    tool: StrictStr
    risk: Literal["MEDIUM", "HIGH"]
    arguments: Dict[str, Any]
    prompt: StrictStr
    target_summary: Optional[StrictStr]
    expires_at: StrictStr


class ConfirmationListV1(_Reply):
    message_type: Literal["confirmation_list"] = "confirmation_list"
    client_id: StrictStr
    confirmations: list[ConfirmationViewV1] = Field(max_length=32)


class ConfirmationAckV1(_Reply):
    message_type: Literal["confirmation_ack"] = "confirmation_ack"
    confirmation_id: StrictStr
    accepted: StrictBool
    approved: Optional[StrictBool]
    error_code: Optional[StrictStr]


class ConfirmationDisconnectedV1(_Reply):
    message_type: Literal["confirmation_disconnected"] = "confirmation_disconnected"
    client_id: StrictStr
    denied_count: StrictInt = Field(ge=0, le=32)


EventKind = Literal["task_recorded", "task_changed", "action_recorded", "action_changed",
                    "rollback_changed", "cleanup_recorded", "resource_changed", "screen_recorded"]


class LedgerEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    sequence: StrictInt = Field(ge=1)
    kind: EventKind
    occurred_at: StrictStr
    task_id: StrictStr
    request_id: Optional[StrictStr]
    record_id: Optional[StrictInt]


class EventBatchV1(_Reply):
    message_type: Literal["event_batch"] = "event_batch"
    stream_id: StrictStr
    first_sequence: StrictInt = Field(ge=0)
    last_sequence: StrictInt = Field(ge=0)
    next_sequence: StrictInt = Field(ge=0)
    reset_required: StrictBool
    has_more: StrictBool
    events: list[LedgerEventV1] = Field(max_length=100)


def _validate_id(name: str, value: str) -> None:
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except (ValueError, AttributeError):
        raise ValueError(f"{name} must be a canonical lowercase UUID") from None


def parse_versioned_request(payload: dict):
    """Parse a v1 message, return None for the existing legacy command envelope."""
    if "protocol_version" not in payload and "message_type" not in payload:
        return None
    if type(payload.get("protocol_version")) is not int or payload["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("UNSUPPORTED_PROTOCOL_VERSION")
    kind = payload.get("message_type")
    if not isinstance(kind, str):
        raise ValueError("INVALID_REQUEST")
    try:
        added = {"confirmation_query": ConfirmationQueryV1,
                 "confirmation_decision": ConfirmationDecisionV1,
                 "confirmation_disconnect": ConfirmationDisconnectV1,
                 "events_query": EventsQueryV1}
        if kind in added:
            return added[kind].model_validate(payload)
        if kind == "submit_text":
            return SubmitTextV1.model_validate(payload)
        if kind == "terminal_readback":
            return TerminalReadbackRequestV1.model_validate(payload)
        if kind == "stop":
            return StopRequestV1.model_validate(payload)
        if kind == "settings_query":
            return SettingsQueryV1.model_validate(payload)
        if kind == "settings_edit_query":
            return SettingsEditQueryV1.model_validate(payload)
        if kind == "settings_save":
            return SettingsSaveV1.model_validate(payload)
        if kind == "voice_query":
            return VoiceQueryV1.model_validate(payload)
        if kind == "history_query":
            return HistoryQueryV1.model_validate(payload)
        if kind == "task_detail_query":
            return TaskDetailQueryV1.model_validate(payload)
        if kind == "history_folder_submit":
            return HistoryFolderSubmitV1.model_validate(payload)
        if kind == "undo_submit":
            return UndoSubmitV1.model_validate(payload)
        if kind == "history_page_query":
            return HistoryPageQueryV1.model_validate(payload)
        if kind == "activity_query":
            return ActivityQueryV1.model_validate(payload)
        if kind == "action_detail_query":
            return ActionDetailQueryV1.model_validate(payload)
        if kind == "action_verification_query":
            return ActionVerificationQueryV1.model_validate(payload)
        if kind == "runtime_query":
            return RuntimeQueryV1.model_validate(payload)
    except ValidationError:
        raise ValueError("INVALID_REQUEST") from None
    raise ValueError("UNKNOWN_MESSAGE_TYPE")
