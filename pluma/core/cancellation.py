"""pluma.core.cancellation — Atomic stop latch and cancellation token.

Spec §12.1 requirements implemented here:
- The stop latch is set atomically (a parent Event, or an inherited Windows
  event when a task uses process workers).
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
from typing import Any, Optional


class ExecutorAdmission:
    """Spawn-inherited Windows stop event for actual process executor entry.

    A zero-time kernel read of the manual-reset event is the admission point.
    SetEvent and that read are ordered by Windows, without a child-held lock
    that could strand STOP when a worker crashes. Handles are duplicated only
    during owned spawn and closed at object/process lifetime end.
    """

    def __init__(self) -> None:
        import ctypes
        handle = self._kernel().CreateEventW(None, True, False, None)
        if not handle:
            raise ctypes.WinError()
        self._attach(handle)

    @property
    def is_closed(self) -> bool:
        return getattr(self, "_handle", None) is None

    def close(self) -> None:
        """Release the parent event handle after the owned worker has exited."""
        if self.is_closed:
            return
        finalizer = getattr(self, "_finalizer", None)
        if finalizer is not None and finalizer.still_active():
            finalizer()
        self._handle = None
        self._finalizer = None

    @staticmethod
    def _kernel():
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateEventW.restype = wintypes.HANDLE
        kernel.SetEvent.argtypes = [wintypes.HANDLE]
        kernel.SetEvent.restype = wintypes.BOOL
        return kernel

    def _attach(self, handle: int) -> None:
        import _winapi
        from multiprocessing.util import Finalize
        self._handle = handle
        self._finalizer = Finalize(self, _winapi.CloseHandle, (handle,), exitpriority=10)

    def __getstate__(self):
        from multiprocessing.context import assert_spawning, get_spawning_popen
        assert_spawning(self)
        return get_spawning_popen().duplicate_for_child(self._handle)

    def __setstate__(self, handle):
        self._attach(handle)

    def is_cancelled(self) -> bool:
        if self.is_closed:
            raise RuntimeError("Task worker admission handle is closed.")
        import _winapi
        state = _winapi.WaitForSingleObject(self._handle, 0)
        if state not in (_winapi.WAIT_OBJECT_0, _winapi.WAIT_TIMEOUT):
            raise OSError("Could not read task worker stop event.")
        return state == _winapi.WAIT_OBJECT_0

    def cancel(self) -> None:
        if self.is_closed:
            raise RuntimeError("Task worker admission handle is closed.")
        import ctypes
        if not self._kernel().SetEvent(self._handle):
            raise ctypes.WinError()

    def admit_executor(self) -> None:
        if self.is_cancelled():
            raise TaskCancelledError("Task was stopped before executor admission.")


class StopReason(str, Enum):
    """Why a cancellation was requested."""
    USER_STOP = "user_stop"         # Global STOP hotkey pressed
    TASK_TIMEOUT = "task_timeout"   # Task exceeded its hard wall-clock limit
    INTERNAL_ERROR = "internal_error"  # Orchestrator detected an unrecoverable state
    POLICY_DENY = "policy_deny"     # Policy engine rejected a required action


class _FrozenEvent:
    """Handle-free event state retained after a task's workers have exited."""

    def __init__(self, is_set: bool) -> None:
        self._is_set = is_set

    def is_set(self) -> bool:
        return self._is_set

    def set(self) -> None:
        self._is_set = True

    def wait(self, timeout: Optional[float] = None) -> bool:
        if self._is_set:
            return True
        if timeout is not None and timeout > 0:
            import time
            time.sleep(timeout)
        return False


class _NoopLock:
    """Lock-compatible terminal state after the task has no concurrent owners."""

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        return True

    def release(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class CancellationToken:
    """Thread-safe, one-way stop latch for one task's lifetime.

    Spec §12.1: "set an atomic stop latch first. After that exact moment,
    the orchestrator must reject every new step/tool start for the task."

    Thread-only tasks use a threading.Event. Process tasks publish a native
    manual-reset event as their canonical latch and inherit it at spawn.
    Once cancelled, the token stays cancelled — there is no resume.

    Native worker disposal also seals admission, without requesting parent
    cancellation. That fence has no reason or cancellation timestamp. A real
    subsequent cancellation still records its first explicit cause.
    """

    def __init__(self) -> None:
        self._event: Any = threading.Event()
        self._reason: Optional[StopReason] = None
        self._cancelled_at: Optional[datetime] = None
        self._lock: Any = threading.Lock()
        self._process_admission: Optional[ExecutorAdmission] = None
        self._retired = False

    # ------------------------------------------------------------------
    # Cancellation state
    # ------------------------------------------------------------------

    @property
    def is_cancelled(self) -> bool:
        """Return True if the latch has been set.

        Safe to call from any thread without holding the lock.
        """
        if self._process_admission is not None and not self._process_admission.is_closed:
            return self._process_admission.is_cancelled()
        return self._event.is_set()

    @property
    def reason(self) -> Optional[StopReason]:
        """First explicit cancellation cause; None for disposal-only fencing."""
        return self._reason

    @property
    def cancelled_at(self) -> Optional[datetime]:
        """UTC time of first explicit cancellation, or None for disposal only."""
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
            if self._process_admission is None:
                self._event.set()
            else:
                # The native event becomes the canonical latch when published.
                # Signal it first, then wake parent cooperative waiters. Neither
                # operation acquires a child-held lock or waits for tool I/O.
                self._process_admission.cancel()
                self._event.set()
            return True

    def admit_executor(self) -> None:
        """Admit on the executing thread, serialized with the STOP latch.

        This is the linearization point for starting a callable, not permission
        that may be granted on the submitter and carried through a work queue.
        Release the lock before the body so STOP never waits for tool completion.
        """
        with self._lock:
            self.raise_if_cancelled("Task was stopped before executor admission.")

    def process_admission(self) -> ExecutorAdmission:
        """Lazily allocate a gate to inherit at spawn, never send it on a pipe.

        Thread-only tasks allocate no native worker event. Gate
        creation is serialized with cancel, including cancellation before spawn.
        """
        with self._lock:
            if self._retired:
                raise RuntimeError("A terminal task cannot admit new worker processes.")
            if self._process_admission is None:
                gate = ExecutorAdmission()
                if self._event.is_set():
                    gate.cancel()
                self._process_admission = gate
            return self._process_admission

    def retire_after_task_completion(self) -> None:
        """Release Windows synchronization handles after all task workers exit.

        The supervisor calls this only after terminal cleanup and ledger
        readback. A completed task may remain in memory for recent history,
        so its synchronization state must no longer own native handles.
        """
        with self._lock:
            # Disposal seals native admission without inventing a STOP reason.
            cancelled = self.is_cancelled
            gate = self._process_admission
            if gate is not None:
                gate.close()
                self._process_admission = None
            self._event = _FrozenEvent(cancelled)
            self._lock = _NoopLock()
            self._retired = True

    # ------------------------------------------------------------------
    # Cooperative wait (read path)
    # ------------------------------------------------------------------

    def wait_for_cancel(self, timeout_s: Optional[float] = None) -> bool:
        """Block until parent cancellation is requested or *timeout_s* elapses.

        Returns True if cancelled, False if the timeout elapsed first.
        Useful for workers that must poll with a sleep rather than a tight loop.
        Disposal-only native admission fencing does not signal this waiter.
        """
        return self._event.wait(timeout=timeout_s)

    def raise_if_cancelled(self, message: str = "Task was stopped.") -> None:
        """Raise TaskCancelledError if the latch is set.

        Call this at the start of each tool step and at yield points inside
        long-running operations.
        """
        if self._retired:
            raise TaskCancelledError("Completed tasks cannot admit new work.", reason=self._reason)
        if self.is_cancelled:
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
