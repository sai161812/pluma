"""Owned runtime drain primitives. No device/model work starts at import or idle."""
from contextlib import contextmanager
from dataclasses import dataclass
import threading
import time
import uuid

from pluma.core.cancellation import TaskCancelledError


class WorkGate:
    """Admission and retained ownership for calls and their executor futures."""
    def __init__(self):
        self._condition = threading.Condition()
        self.closing = False
        self.active = 0
        self.futures = {}

    @contextmanager
    def enter(self):
        with self._condition:
            if self.closing:
                raise TaskCancelledError("Runtime is shutting down.")
            self.active += 1
        try:
            yield
        finally:
            with self._condition:
                self.active -= 1
                self._condition.notify_all()

    def submit(self, executor, fn, *args, task_id=None, command_class="tool", _task_context=None, **kwargs):
        from pluma.core.task_supervisor import TaskCapsule
        capsule = _task_context if isinstance(_task_context, TaskCapsule) else None
        with self._condition:
            if self.closing:
                raise TaskCancelledError("Runtime is shutting down.")
            identity = {"task_id": task_id, "command_class": command_class,
                        "resource_id": "inprocess:" + uuid.uuid4().hex}
            if capsule is not None:
                with capsule.work_lock:
                    capsule.owned_work[identity["resource_id"]] = {"future": None, "identity": identity}
            future = executor.submit(fn, *args, **kwargs)
            if capsule is not None:
                with capsule.work_lock:
                    capsule.owned_work[identity["resource_id"]]["future"] = future
            self.futures[future] = {**identity, "_capsule": capsule}
            future.add_done_callback(self._release)
            return future

    def _release(self, future):
        with self._condition:
            self.futures.pop(future, None)
            # The capsule retains its Future until supervisor readback. A
            # callback must not mutate terminal evidence after persistence.
            self._condition.notify_all()

    def begin_shutdown(self):
        with self._condition:
            self.closing = True
            for future in list(self.futures):
                future.cancel()  # running work stays owned until actual exit
            self._condition.notify_all()

    def pending_futures(self):
        with self._condition:
            return [{key: value for key, value in identity.items() if not key.startswith("_")}
                    for identity in self.futures.values()]

    def wait_idle(self, timeout_s=1.0):
        with self._condition:
            return self._condition.wait_for(lambda: self.active == 0 and not self.futures, timeout_s)


@dataclass(frozen=True)
class ShutdownResult:
    complete: bool
    stage: str
    code: str


class ShutdownSession:
    """One serialized stage worker, retained and joined across bounded close calls.

    A slow external driver cannot be safely killed as a Python thread. A timed
    out stage remains owned here; no later stage or storage close may begin.
    Repeated close awaits the SAME worker and resumes only after its exit.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.index = 0
        self.worker = None
        self.failed = False
        self.result = ShutdownResult(False, "intake", "NOT_STARTED")

    def run(self, stages, timeout_s=5.0):
        deadline = time.monotonic() + max(0, timeout_s)
        if not self._lock.acquire(timeout=max(0, deadline - time.monotonic())):
            return ShutdownResult(False, self.result.stage, "CLOSE_IN_PROGRESS")
        try:
            while self.index < len(stages):
                name, action = stages[self.index]
                if self.worker is None:
                    if time.monotonic() >= deadline:
                        self.result = ShutdownResult(False, name, "BUDGET_EXHAUSTED")
                        return self.result
                    self.failed = False
                    def run_stage(action=action):
                        try:
                            action()
                        except Exception:
                            self.failed = True  # fixed report, never exception/args
                    self.worker = threading.Thread(target=run_stage, name="PlumaShutdown:" + name)
                    self.result = ShutdownResult(False, name, "DRAINING")
                    self.worker.start()
                self.worker.join(timeout=max(0, deadline - time.monotonic()))
                if self.worker.is_alive():
                    self.result = ShutdownResult(False, name, "STAGE_PENDING")
                    return self.result
                self.worker = None
                if self.failed:
                    self.result = ShutdownResult(False, name, "STAGE_UNVERIFIED")
                    return self.result
                self.index += 1
            self.result = ShutdownResult(True, "closed", "CLOSED_VERIFIED")
            return self.result
        finally:
            self._lock.release()
