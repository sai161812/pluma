"""Version 1 typed request/acknowledgement/readback messages for local UI IPC."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr, ValidationError, model_validator


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

    @model_validator(mode="after")
    def canonical_ids(self):
        for name in ("request_id", "task_id"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                if str(UUID(value)) != value:
                    raise ValueError
            except (ValueError, AttributeError):
                raise ValueError(f"{name} must be a canonical lowercase UUID") from None
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


def parse_versioned_request(payload: dict) -> SubmitTextV1 | TerminalReadbackRequestV1 | StopRequestV1 | None:
    """Parse a v1 message, return None for the existing legacy command envelope."""
    if "protocol_version" not in payload and "message_type" not in payload:
        return None
    if type(payload.get("protocol_version")) is not int or payload["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("UNSUPPORTED_PROTOCOL_VERSION")
    kind = payload.get("message_type")
    try:
        if kind == "submit_text":
            return SubmitTextV1.model_validate(payload)
        if kind == "terminal_readback":
            return TerminalReadbackRequestV1.model_validate(payload)
        if kind == "stop":
            return StopRequestV1.model_validate(payload)
    except ValidationError:
        raise ValueError("INVALID_REQUEST") from None
    raise ValueError("UNKNOWN_MESSAGE_TYPE")
