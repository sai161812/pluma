"""Strict supported settings; security invariants remain outside editable fields."""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator
from pluma.config.settings import _hotkey

FIELD_PATHS = {
    "text_hotkey": "agent.text_hotkey", "stop_hotkey": "agent.stop_hotkey",
    "voice_hotkey": "agent.voice_hotkey", "max_plan_steps": "agent.max_plan_steps",
    "planner_model_path": "brain.model_path", "stt_model_path": "voice.model_path",
    "model_idle_unload_seconds": "runtime.model_idle_unload_seconds",
    "stt_idle_unload_seconds": "runtime.stt_idle_unload_seconds",
    "ocr_idle_unload_seconds": "runtime.ocr_idle_unload_seconds",
    "allow_short_warm_grace": "runtime.allow_short_warm_grace",
    "activation_default": "voice.activation_default", "model_runtime": "brain.runtime",
}
FIELDS = tuple(FIELD_PATHS)

class SettingsChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    recover_previous: Optional[Literal[True]] = None
    max_plan_steps: Optional[StrictInt] = Field(default=None, ge=1, le=20)
    text_hotkey: Optional[StrictStr] = Field(default=None, min_length=1, max_length=64)
    stop_hotkey: Optional[StrictStr] = Field(default=None, min_length=1, max_length=64)
    voice_hotkey: Optional[StrictStr] = Field(default=None, min_length=1, max_length=64)
    planner_model_path: Optional[StrictStr] = Field(default=None, min_length=1, max_length=4096)
    stt_model_path: Optional[StrictStr] = Field(default=None, min_length=1, max_length=4096)
    model_idle_unload_seconds: Optional[StrictInt] = Field(default=None, ge=0, le=30)
    stt_idle_unload_seconds: Optional[StrictInt] = Field(default=None, ge=0, le=30)
    ocr_idle_unload_seconds: Optional[StrictInt] = Field(default=None, ge=0, le=30)
    allow_short_warm_grace: Optional[StrictBool] = None
    activation_default: Optional[Literal["push_to_talk"]] = None
    model_runtime: Optional[Literal["llama_cpp"]] = None

    @field_validator("text_hotkey", "stop_hotkey", "voice_hotkey")
    @classmethod
    def binding(cls, value):
        if value is not None:
            _hotkey(value)
        return value

    @field_validator("planner_model_path", "stt_model_path")
    @classmethod
    def local_path(cls, value):
        from pathlib import Path
        if value is not None and (not Path(value).is_absolute() or value.startswith(("\\\\", "//")) or "\0" in value):
            raise ValueError("A local absolute model path is required.")
        return value

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("A settings change must contain supported, non-null values.")
        if self.recover_previous and self.model_fields_set != {"recover_previous"}:
            raise ValueError("Recovery cannot be mixed with edits.")
        return self

class SettingsSaveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: StrictStr = Field(pattern=r"^(?:absent|[0-9a-f]{64})$")
    changes: SettingsChanges
    previous_revision: Optional[StrictStr] = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def recovery_binding(self):
        if bool(self.changes.recover_previous) != (self.previous_revision is not None):
            raise ValueError("Recovery requires the exact previous source revision.")
        return self

class SettingsRecoveryArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    previous_revision: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

class SettingsValues(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    text_hotkey: StrictStr
    stop_hotkey: StrictStr
    voice_hotkey: StrictStr
    max_plan_steps: StrictInt = Field(ge=1, le=20)
    planner_model_path: StrictStr = ""
    stt_model_path: StrictStr = ""
    model_idle_unload_seconds: StrictInt = Field(default=30,ge=0,le=30)
    stt_idle_unload_seconds: StrictInt = Field(default=20,ge=0,le=30)
    ocr_idle_unload_seconds: StrictInt = Field(default=10,ge=0,le=30)
    allow_short_warm_grace: StrictBool = True
    activation_default: Literal["push_to_talk"] = "push_to_talk"
    model_runtime: Literal["llama_cpp"] = "llama_cpp"

    @field_validator("text_hotkey", "stop_hotkey", "voice_hotkey")
    @classmethod
    def known_binding_syntax(cls, value):
        _hotkey(value)
        return value

def values(config, planner_default="", stt_default=""):
    from pluma.config.loader import get
    defaults={"voice_hotkey":"ctrl+alt+v", "planner_model_path":planner_default, "stt_model_path":stt_default}
    return SettingsValues(**{key: get(config, *path.split("."), default=defaults.get(key))
                             for key,path in FIELD_PATHS.items()})

def patch(arguments):
    return {FIELD_PATHS[key]: value for key,value in arguments["changes"].items() if value is not None}
