"""pluma.core.request — PlumaRequest and related value types.

Every command PLUMA receives — whether typed or spoken — becomes one PlumaRequest.
Voice and text are indistinguishable at this boundary; InputMode records which
path produced the transcript, but the pipeline logic is identical.

Nothing in this module imports ML libraries, adapters, or OS automation code.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class InputMode(str, Enum):
    """How the command reached PLUMA."""
    TEXT = "text"
    VOICE = "voice"


class RequestID(str):
    """Opaque identifier for a single inbound request.

    Wraps a UUID string so the type carries intent.
    """

    @classmethod
    def new(cls) -> "RequestID":
        return cls(str(uuid.uuid4()))

    def __repr__(self) -> str:  # pragma: no cover
        return f"RequestID({str(self)!r})"


class PlumaRequest(BaseModel):
    """Immutable representation of one user command.

    Created at the boundary between input capture and the execution pipeline.
    After creation the text is the canonical form for all downstream components;
    the original_transcript preserves the raw STT output when voice was used.

    Spec §6 step 1-2: voice transcript is normalized minimally; the original
    is retained in task metadata.
    """

    model_config = {"frozen": True}

    request_id: str = Field(default_factory=lambda: RequestID.new())
    input_mode: InputMode
    text: str = Field(min_length=1, max_length=4096)
    original_transcript: Optional[str] = Field(
        default=None,
        description="Raw STT output before normalization. Set only for voice input.",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    active_process: Optional[str] = Field(
        default=None,
        description="Name of the foreground process at request creation time.",
    )
    active_window_title: Optional[str] = Field(
        default=None,
        description="Title of the foreground window at request creation time.",
    )

    @field_validator("original_transcript")
    @classmethod
    def _transcript_only_for_voice(
        cls, v: Optional[str], info: object
    ) -> Optional[str]:
        # Access the already-validated input_mode via model_fields_set inspection.
        # Pydantic v2: use info.data for sibling field values.
        data = getattr(info, "data", {})
        mode = data.get("input_mode")
        if v is not None and mode is not None and mode != InputMode.VOICE:
            raise ValueError(
                "original_transcript must be None for non-voice input"
            )
        return v

    @field_validator("text")
    @classmethod
    def _text_not_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be whitespace-only")
        return v
