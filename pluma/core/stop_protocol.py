"""Typed STOP snapshots, independent of native transport framing.

A transport acknowledgement is never proof that cancellation cleaned up.
Models contain deterministic facts/copy, never exception text or tool arguments.
"""
from enum import Enum
import threading
import uuid
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pluma.core.cleanup import CleanupEvidence


class StopOutcome(str, Enum):
    PENDING = "pending"
    STOPPED = "stopped"
    RESIDUAL = "residual"
    ERROR = "error"
    TERMINAL = "terminal"


StopError = Literal["INVALID_TASK_ID", "TASK_NOT_FOUND", "STOP_CLEANUP_ERROR",
                    "STOP_START_FAILED", "EVIDENCE_BUSY",
                    "TERMINAL_HISTORY_UNVERIFIED", "TASK_FAILED"]


class StopCleanupEvidence(CleanupEvidence):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class StopTaskOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    task_id: str
    outcome: StopOutcome
    latch_acknowledged: bool
    final_state: Optional[Literal["CREATED", "RUNNING", "STOPPING", "ROLLING_BACK",
        "SUCCEEDED", "FAILED", "STOPPED", "STOPPED_WITH_RESIDUAL", "ABORTED_BY_CRASH"]] = None
    completion_verified: bool = False
    terminal_persisted: Optional[bool] = None
    cleanup_in_progress: bool = False
    cleanup_verified: bool = False
    has_residual: bool = False
    rollback_performed: bool = False
    rollback_success: Optional[bool] = None
    cleanup_evidence: list[StopCleanupEvidence] = Field(default_factory=list)
    error_code: Optional[StopError] = None

    @model_validator(mode="after")
    def require_clean_stop_proof(self):
        if self.outcome == StopOutcome.STOPPED and not (
            self.final_state == "STOPPED" and self.latch_acknowledged
            and self.completion_verified and self.terminal_persisted is True
            and self.cleanup_verified and not self.cleanup_in_progress
            and not self.has_residual and self.error_code is None
            and self.rollback_success is not False
            and all(item.verified for item in _latest(self.cleanup_evidence))
        ):
            raise ValueError("Clean STOP requires verified terminal, history and cleanup facts.")
        return self


def _latest(entries):
    return {(e.kind, e.resource_id): e for e in entries}.values()


class StopReply(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    status: Literal["ok", "error"] = "ok"
    stop_contract: Literal["pluma.stop.v1"] = "pluma.stop.v1"
    message: Literal["STOP request processed.", "A valid task ID is required."] = "STOP request processed."
    error_code: Optional[StopError] = None
    tasks: list[StopTaskOutcome] = Field(default_factory=list)

    stopped_tasks: list[str] = Field(default_factory=list)
    stopped_count: int = Field(default=0, ge=0)
    latch_acknowledged_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def verify_counts(self):
        # Server construction derives counts; parsing also rejects conflicting
        # compatibility fields rather than trusting a transport status.
        if len({t.task_id for t in self.tasks}) != len(self.tasks):
            raise ValueError("Duplicate STOP task identity.")
        if self.status == "error" and (self.tasks or self.error_code is None):
            raise ValueError("Request error must not imply task acknowledgement.")
        if self.status == "ok" and self.error_code is not None:
            raise ValueError("Task errors belong to their individual outcomes.")
        ids = [t.task_id for t in self.tasks if t.outcome == StopOutcome.STOPPED]
        values = {"stopped_tasks": ids, "stopped_count": len(ids),
                  "latch_acknowledged_count": sum(t.latch_acknowledged for t in self.tasks)}
        for name, value in values.items():
            if name in self.model_fields_set and getattr(self, name) != value:
                raise ValueError("STOP aggregate conflicts with task evidence.")
            object.__setattr__(self, name, value)
        return self

    def wire(self):
        return self.model_dump(mode="json")


class StopOperation:
    """One supervisor-retained cleanup owner, including after reply timeout.

    Thread creation is lazy. The supervisor publishes this object before start,
    joins before disposal/store close, and retains the affected capsules.
    """
    def __init__(self, capsules):
        self.operation_id = uuid.uuid4().hex
        self.capsules = capsules
        self.finished = set()
        self.thread = None
        self._start_finished = threading.Event()

    def start(self, run):
        self.thread = threading.Thread(target=run, name="PlumaStop:" + self.operation_id)
        try:
            self.thread.start()
        except Exception:
            self.thread = None  # no worker was admitted; supervisor records failure
            raise
        finally:
            self._start_finished.set()

    def join(self, timeout_s):
        if not self._start_finished.is_set():
            return False  # published owner may still be crossing thread.start
        if self.thread is not None:
            if self.thread is threading.current_thread():
                return False  # a reentrant STOP observes its existing owner
            self.thread.join(timeout=max(0, timeout_s))
            return not self.thread.is_alive()
        return True
