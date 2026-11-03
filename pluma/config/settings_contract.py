"""Public settings edit subset. Unsupported runtime/security fields are absent."""
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator

from pluma.config.settings import _hotkey

FIELDS = ("text_hotkey", "stop_hotkey", "voice_hotkey", "max_plan_steps")


class SettingsChanges(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_plan_steps: Optional[StrictInt] = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set or any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("A settings change must contain supported, non-null values.")
        return self


class SettingsSaveArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_revision: StrictStr = Field(pattern=r"^(?:absent|[0-9a-f]{64})$")
    changes: SettingsChanges


class SettingsValues(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    text_hotkey: StrictStr = Field(min_length=1, max_length=64)
    stop_hotkey: StrictStr = Field(min_length=1, max_length=64)
    voice_hotkey: StrictStr = Field(min_length=1, max_length=64)
    max_plan_steps: StrictInt = Field(ge=1, le=20)

    @field_validator("text_hotkey", "stop_hotkey", "voice_hotkey")
    @classmethod
    def known_binding_syntax(cls, value):
        _hotkey(value)
        return value


def values(config):
    from pluma.config.loader import get
    return SettingsValues(**{key: get(config, "agent", key,
        default="ctrl+alt+v" if key == "voice_hotkey" else None) for key in FIELDS})


def patch(arguments):
    return {"agent." + key: value for key, value in arguments["changes"].items() if value is not None}
