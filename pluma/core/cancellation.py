"""pluma.core.cancellation — Atomic stop latch and cancellation token.

Spec §12.1 requirements implemented here:
- The stop latch is set atomically (threading.Event under the hood).
- Once set, the token is permanently cancelled; it cannot be reset.
- Every component that can be interrupted must check token.is_cancelled()
  before starting new work and periodically during long operations.
- The token carries a StopReason so the ledger can record why the task ended.

No ML, OS-automation or adapter code in this module.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StopReason(str, Enum):
    """Why a cancellation was requested."""
    USER_STOP = "user_stop"         # Global STOP hotkey pressed
    TASK_TIMEOUT = "task_timeout"   # Task exceeded its hard wall-clock limit
    INTERNAL_ERROR = "internal_error"  # Orchestrator detected an unrecoverable state
    POLICY_DENY = "policy_deny"     # Policy engine rejected a required action


class CancellationToken:
    """Thread-safe, one-way stop latch for one task's lifetime.

    Spec §12.1: "set an atomic stop latch first. After that exact moment,
    the orchestrator must reject every new step/tool start for the task."

    The latch is a threading.Event: set() is atomic on CPython and all
    threads see the state change immediately. Once cancelled, the token
    stays cancelled — there is no resume.
    """

    def __init__(self) -> None:
        self._event: threading.Event = threading.Event()
        self._reason: Optional[StopReason] = None
        self._cancelled_at: Optional[datetime] = None
        self._lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Cancellation state
    # ------------------------------------------------------------------

    @property
    def is_cancelled(self) -> bool:
        """Return True if the latch has been set.

        Safe to call from any thread without holding the lock.
        """
        return self._event.is_set()

    @property
    def reason(self) -> Optional[StopReason]:
        """The reason the latch was set, or None if not yet cancelled."""
        return self._reason

    @property
    def cancelled_at(self) -> Optional[datetime]:
        """UTC timestamp when the latch was first set, or None."""
        return self._cancelled_at

    # ------------------------------------------------------------------
    # Latch control (write path)
    # ------------------------------------------------------------------

    def cancel(self, reason: StopReason = StopReason.USER_STOP) -> bool:
        """Set the stop latch.

        Returns True if this call was the one that set it (i.e. it was not
        already cancelled). Returns False if already cancelled — the first
        caller wins; subsequent calls are silent no-ops.
        """
        with self._lock:
            if self._event.is_set():
                return False          # Already cancelled; first caller wins.
            self._reason = reason
            self._cancelled_at = datetime.now(timezone.utc)
            self._event.set()         # Atomic from all observer threads' perspectives.
            return True

    # ------------------------------------------------------------------
    # Cooperative wait (read path)
    # ------------------------------------------------------------------

    def wait_for_cancel(self, timeout_s: Optional[float] = None) -> bool:
        """Block until the latch is set or *timeout_s* elapses.

        Returns True if cancelled, False if the timeout elapsed first.
        Useful for workers that must poll with a sleep rather than a tight loop.
        """
        return self._event.wait(timeout=timeout_s)

    def raise_if_cancelled(self, message: str = "Task was stopped.") -> None:
        """Raise TaskCancelledError if the latch is set.

        Call this at the start of each tool step and at yield points inside
        long-running operations.
        """
        if self._event.is_set():
            raise TaskCancelledError(message, reason=self._reason)

    def __repr__(self) -> str:  # pragma: no cover
        state = f"cancelled({self._reason})" if self.is_cancelled else "active"
        return f"CancellationToken({state})"


class TaskCancelledError(RuntimeError):
    """Raised when a component detects that its task's stop latch is set.

    This is the cooperative path. Workers should catch it, clean up, and
    propagate or let the Task Supervisor handle it.
    """

    def __init__(self, message: str, reason: Optional[StopReason] = None) -> None:
        super().__init__(message)
        self.reason = reason
