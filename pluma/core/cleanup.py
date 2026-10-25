"""Deterministic cleanup evidence. Never store exceptions, tool arguments or handles."""
from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field


class CleanupEvidence(BaseModel):
    resource_id: str
    kind: str
    verified: bool = False
    code: str
    identity: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


def cleanup_job(job, resource_id: str, *, terminate: bool, timeout_s: float = 0.3) -> CleanupEvidence:
    """Read an empty owned job before closing the only containment handle.

    Termination failure may be resolved by a positive empty-job readback, but
    neither a call return nor an unavailable/closed handle establishes absence.
    """
    errors = []
    if terminate:
        try:
            job.terminate(exit_code=1)
        except Exception:
            errors.append("JOB_TERMINATION_FAILED")
    deadline = time.monotonic() + timeout_s
    verified = False
    observed_count = None
    closed = None
    try:
        while True:
            count = job.active_process_count()
            if type(count) is not int or count < 0:
                raise ValueError("Invalid job readback")
            observed_count = count
            if count == 0:
                verified = True
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    except Exception:
        errors.append("JOB_READBACK_FAILED")
    if verified:
        try:
            job.close()
            closed = job.is_closed
            if closed is not True:
                raise ValueError("Job handle closure unverified")
        except Exception:
            errors.append("JOB_CLOSE_FAILED")
            verified = False
    return CleanupEvidence(resource_id=resource_id, kind="job", verified=verified,
                           code="JOB_EMPTY_AND_CLOSED" if verified else "JOB_CLEANUP_UNVERIFIED",
                           identity={"active_processes": observed_count, "handle_closed": closed},
                           errors=errors)


def latest_unresolved(evidence: list[CleanupEvidence]) -> list[CleanupEvidence]:
    latest = {(item.kind, item.resource_id): item for item in evidence}
    return [item for item in latest.values() if not item.verified]
