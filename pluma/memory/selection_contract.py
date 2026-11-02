"""Shared typed saved-action identity, independent of IPC and adapters."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator


class UndoSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    target_task_id: StrictStr
    action_id: StrictInt = Field(ge=1, le=9223372036854775807)
    revision: StrictStr = Field(pattern=r'^[a-f0-9]{64}$')
    material: StrictStr = Field(min_length=1, max_length=4096)

    @model_validator(mode='after')
    def bounded_identity(self):
        if str(UUID(self.target_task_id)) != self.target_task_id or len(self.material.encode('utf-8')) > 4096:
            raise ValueError('Invalid saved selection identity or material bound.')
        return self
