"""pluma.core.task_supervisor — TaskCapsule, TaskState, and TaskSupervisor.

Spec §12: Every user command becomes one TaskCapsule. All tool calls,
subprocesses, temporary resources, undo records and screen snapshots belong
to that capsule. The TaskSupervisor owns the state machine and the
cancellation tree.
"""

from __future__ import annotations

import logging
import threading
import time
from time import monotonic as _stop_clock
import uuid
import weakref
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
from pluma.core.cleanup import CleanupEvidence, cleanup_job, latest_unresolved

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """Lifecycle states for a TaskCapsule."""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    ROLLING_BACK = "ROLLING_BACK"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    STOPPED_WITH_RESIDUAL = "STOPPED_WITH_RESIDUAL"
    ABORTED_BY_CRASH = "ABORTED_BY_CRASH"


_TERMINAL_STATES: frozenset[TaskState] = frozenset({
    TaskState.SUCCEEDED,
    TaskState.FAILED,
    TaskState.STOPPED,
    TaskState.STOPPED_WITH_RESIDUAL,
    TaskState.ABORTED_BY_CRASH,
})

_TRANSITIONS: Dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.RUNNING, TaskState.FAILED, TaskState.ABORTED_BY_CRASH, TaskState.STOPPING}),
    TaskState.RUNNING: frozenset({
        TaskState.STOPPING, TaskState.SUCCEEDED, TaskState.FAILED,
        TaskState.ABORTED_BY_CRASH,
    }),
    TaskState.STOPPING: frozenset({
        TaskState.ROLLING_BACK, TaskState.STOPPED,
        TaskState.STOPPED_WITH_RESIDUAL, TaskState.ABORTED_BY_CRASH,
        TaskState.FAILED,
    }),
    TaskState.ROLLING_BACK: frozenset({
        TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL,
        TaskState.ABORTED_BY_CRASH, TaskState.FAILED,
    }),
    TaskState.SUCCEEDED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.STOPPED: frozenset(),
    TaskState.STOPPED_WITH_RESIDUAL: frozenset(),
    TaskState.ABORTED_BY_CRASH: frozenset(),
}


class ResourceOwnership(str, Enum):
    """Whether a resource existed before the task or was created by PLUMA."""
    PREEXISTING = "PREEXISTING"
    PLUMA_CREATED = "PLUMA_CREATED"


class OwnedResource(BaseModel):
    """Metadata for a resource claimed or created by a TaskCapsule."""
    resource_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    resource_type: str
    ownership: ResourceOwnership
    external_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    released_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False}


class TaskStep(BaseModel):
    """A discrete operation within a TaskCapsule."""
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    success: Optional[bool] = None

    model_config = {"frozen": False}


class InvalidTaskTransition(Exception):
    """Raised when an illegal task state transition is attempted."""
    pass


class TaskCapsule(BaseModel):
    """Runtime capsule for a single user task.
    
    Mutable state machine updated only by the TaskSupervisor.
    """
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_id: str
    state: TaskState = TaskState.CREATED
    cancellation_token: CancellationToken = Field(default_factory=CancellationToken)
    
    # We maintain an undo stack for rollback.
    undo_stack: List[Dict[str, Any]] = Field(default_factory=list)
    steps: List[TaskStep] = Field(default_factory=list)
    owned_resources: List[OwnedResource] = Field(default_factory=list)

    cleanup_evidence: List[CleanupEvidence] = Field(default_factory=list)
    cleanup_finalized: bool = False
    terminal_persisted: Optional[bool] = None
    history_expected: bool = True
    stop_error: Optional[str] = Field(default=None, exclude=True)
    voice_session: Any = Field(default=None, exclude=True)
    owned_work: Dict[str, Any] = Field(default_factory=dict, exclude=True)
    work_lock: Any = Field(default_factory=threading.RLock, exclude=True)
    terminal_ready: Any = Field(default_factory=threading.Event, exclude=True)

    @property
    def cleanup_pending(self) -> bool:
        return bool(latest_unresolved(self.cleanup_evidence))

    def outcome_details(self) -> Dict[str, Any]:
        """Deterministic, redacted facts shared by result and IPC projections."""
        from pluma.memory.redaction import redact_sensitive_data
        rollback = [item for item in self.cleanup_evidence if item.kind == "rollback"]
        return {
            "final_state": self.state.value,
            "completion_verified": self.terminal_ready.is_set(),
            "terminal_persisted": self.terminal_persisted,
            "has_residual": self.cleanup_pending,
            "rollback_performed": bool(rollback) and not rollback[-1].code.startswith("ROLLBACK_DEFERRED"),
            "rollback_success": rollback[-1].verified if rollback else None,
            "cleanup_evidence": redact_sensitive_data([item.model_dump() for item in self.cleanup_evidence]),
        }

    def terminal_summary(self) -> str:
        if not self.terminal_ready.is_set():
            return "Task cleanup is still pending."
        if self.state == TaskState.STOPPED_WITH_RESIDUAL:
            return "Task stopped. Residual effects or unverified cleanup remain."
        if self.state == TaskState.STOPPED:
            return "Task stopped. Cleanup verified."
        if self.state == TaskState.FAILED:
            return "Task failed. Cleanup or history could not be verified." if self.cleanup_pending else "Task failed."
        if self.state == TaskState.SUCCEEDED:
            return "Task completed successfully."
        return "Task was interrupted."

    # Job Object wrapper for process containment (not serializable)
    job_object: Any = Field(default=None, exclude=True)

    # Snapshot registry for UI grounding — not serializable, cleared on terminal transition
    snapshot_registry: Any = Field(default=None, exclude=True)

    # Active task-owned ToolRegistry worker controller (not serializable)
    worker_controller: Any = Field(default=None, exclude=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @property
    def stop_latch_set(self) -> bool:
        return self.cancellation_token.is_cancelled

    def register_owned_resource(
        self,
        resource_type: str,
        ownership: ResourceOwnership,
        external_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OwnedResource:
        """Register an owned resource directly on this task capsule."""
        metadata = dict(metadata or {})
        if ownership == ResourceOwnership.PLUMA_CREATED and resource_type in ("temp_dir", "temp_file") and external_id:
            from pathlib import Path
            from pluma.core.ownership import capture_temp_identity
            try:
                metadata["cleanup_identity"] = capture_temp_identity(Path(external_id))
            except (OSError, ValueError):
                pass
        res = OwnedResource(
            resource_type=resource_type,
            ownership=ownership,
            external_id=external_id,
            metadata=metadata or {},
        )
        self.owned_resources.append(res)
        return res

    def close_resources(self, *, stopping: bool = False) -> List[CleanupEvidence]:
        """Clean only owned handles; retain unknown/failed ownership for retry."""
        checks = []
        session = self.voice_session
        if session is not None:
            check = session.cleanup(stopping=stopping)
            checks.append(check)
            if check.verified and session.idle:
                self.voice_session = None
        with self.work_lock:
            for resource_id, work in list(self.owned_work.items()):
                verified = work["future"] is not None and work["future"].done()
                self.cleanup_evidence.append(CleanupEvidence(resource_id=resource_id, kind="worker",
                    code="INPROCESS_WORK_EXITED" if verified else "INPROCESS_WORK_PENDING",
                    verified=verified, identity=work["identity"]))
                if verified:
                    self.owned_work.pop(resource_id, None)
        worker = self.worker_controller
        worker_errors = []
        if worker is not None:
            try:
                dispose = getattr(worker, "dispose_owned_worker", None)
                if callable(dispose):
                    dispose()
                else:
                    worker.terminate_and_join()
            except Exception:
                worker_errors.append("WORKER_TERMINATION_FAILED")
        if self.job_object is not None:
            check = cleanup_job(self.job_object, "task-job:" + self.task_id, terminate=True)
            checks.append(check)
            if check.verified:
                self.job_object = None
        for res in self.owned_resources:
            if res.ownership != ResourceOwnership.PLUMA_CREATED:
                continue
            job = res.metadata.get("persistent_job")
            if job is None:
                continue
            if stopping:
                check = cleanup_job(job, "persistent-job:" + res.resource_id, terminate=True)
            else:
                check = CleanupEvidence(resource_id="persistent-job:" + res.resource_id,
                                        kind="job", code="PERSISTENT_HANDLE_CLOSE_UNVERIFIED")
                try:
                    job.close()  # kill_on_close=False, preserve deliberately launched app
                    check.verified = job.is_closed is True
                except Exception:
                    check.errors.append("JOB_CLOSE_FAILED")
                if check.verified:
                    check.code = "PERSISTENT_HANDLE_CLOSED_APP_PRESERVED"
            checks.append(check)
            if check.verified:
                res.metadata["persistent_job"] = None
        if worker is not None:
            identity = {"task_id": self.task_id}
            recorded = getattr(worker, "worker_identity", None)
            if isinstance(recorded, dict):
                identity.update({k: recorded[k] for k in ("pid", "creation_time", "command_class", "ownership", "exit_code") if k in recorded})
            verified = False
            try:
                verified = worker.verify_cleanup() is True
            except Exception:
                worker_errors.append("WORKER_READBACK_FAILED")
            owned_checks = getattr(worker, "cleanup_evidence", None)
            if isinstance(owned_checks, list):
                checks.extend(item for item in owned_checks if isinstance(item, CleanupEvidence))
            if verified:
                registry = getattr(self, "_tool_registry", None)
                if registry is not None:
                    try:
                        registry.cleanup_task(self.task_id, recycle=False)
                    except Exception:
                        worker_errors.append("REGISTRY_WORKER_RELEASE_FAILED")
                        verified = False
            check = CleanupEvidence(resource_id="worker:" + self.task_id, kind="worker", identity=identity,
                verified=verified, code="WORKER_ABSENCE_VERIFIED" if verified else "WORKER_CLEANUP_UNVERIFIED",
                errors=worker_errors)
            checks.append(check)
            if verified:
                self.worker_controller = None
        if self.snapshot_registry is not None:
            check = CleanupEvidence(resource_id="snapshots:" + self.task_id, kind="snapshots", code="SNAPSHOT_RELEASE_UNVERIFIED")
            try:
                self.snapshot_registry.clear()
                if len(self.snapshot_registry) != 0:
                    raise RuntimeError("Snapshot release readback failed.")
                self.snapshot_registry = None
                check.verified = True
                check.code = "SNAPSHOTS_RELEASED"
            except Exception:
                check.errors.append("SNAPSHOT_RELEASE_FAILED")
            checks.append(check)
        self.cleanup_evidence.extend(checks)
        return checks



MAX_TERMINAL_TASKS_RETAINED: int = 50


class TaskSupervisor:
    """Highest-priority runtime authority for task lifecycle and cancellation.
    
    Spec §12: Owns task state, cancellation, child processes, stop and cleanup.
    """

    def __init__(
        self,
        ownership_registry: Any = None,
        ledger: Any = None,
        rollback_engine: Any = None,
        paths: Any = None,
        max_retained_terminal_tasks: int = MAX_TERMINAL_TASKS_RETAINED,
    ) -> None:
        self._registry = ownership_registry
        self._ledger = ledger
        self._rollback_engine = rollback_engine
        self._paths = paths
        self._max_retained_terminal_tasks = max_retained_terminal_tasks
        self._tasks: Dict[str, TaskCapsule] = {}
        self._retained_preparations: Dict[str, TaskCapsule] = {}
        self._lock = threading.RLock()
        # Short publication/state/latch boundary. Never hold this lock during
        # resource construction, grace, worker I/O, rollback or final cleanup.
        # Code needing both locks acquires _lock before _admission_lock.
        self._admission_lock = threading.RLock()
        self._global_stop_depth = 0
        self._stop_generation = 0
        self._closing = False
        self._stop_operations = {}
        self._preparing = 0
        from pluma.core.shutdown import WorkGate
        self.execution_gate = WorkGate()

    def prune_terminal_tasks(self, keep_count: Optional[int] = None) -> int:
        """Evict oldest terminal tasks from memory to prevent memory leaks."""
        limit = keep_count if keep_count is not None else self._max_retained_terminal_tasks
        with self._lock:
            with self._admission_lock:
                stop_owned_ids = {tid for op in self._stop_operations.values() for tid in op.capsules}
            terminal_ids = [
                tid for tid, cap in self._tasks.items()
                if cap.state in _TERMINAL_STATES and cap.terminal_ready.is_set() and not cap.cleanup_pending and not cap.owned_work and cap.voice_session is None
                and cap.task_id not in stop_owned_ids
            ]
            if len(terminal_ids) <= limit:
                return 0

            # Evict oldest terminal tasks first
            excess = len(terminal_ids) - limit
            to_remove = terminal_ids[:excess]
            for tid in to_remove:
                with self._admission_lock:
                    cap = self._tasks.pop(tid, None)
                if cap is not None:
                    cap.close_resources()
            return len(to_remove)

    def create_task(self, request_id: str) -> TaskCapsule:
        """Create a new TaskCapsule in CREATED state."""
        return self.create_task_capsule(request_id=request_id)

    def create_task_capsule(self, task_id: Optional[str] = None, request_id: str = "req-default", *, history_expected: bool = True) -> TaskCapsule:
        with self._admission_lock:
            if self._closing:
                raise TaskCancelledError("Runtime is shutting down.")
            self._preparing += 1
            generation = self._stop_generation
        try:
            return self._prepare_task_capsule(task_id, request_id, history_expected, generation)
        finally:
            with self._admission_lock:
                self._preparing -= 1

    def _prepare_task_capsule(self, task_id: Optional[str], request_id: str, history_expected: bool, generation: int) -> TaskCapsule:
        """Create a new TaskCapsule in CREATED state, optionally with explicit task_id."""
        with self._admission_lock:
            if self._global_stop_depth or self._closing or generation != self._stop_generation:
                raise TaskCancelledError("New task rejected across STOP or shutdown.")
        with self._lock:
            self.prune_terminal_tasks()
            capsule = TaskCapsule(request_id=request_id, history_expected=history_expected)
            if task_id:
                capsule.task_id = task_id

            capsule.cancellation_token.task_id = capsule.task_id
            capsule.cancellation_token._capsule = weakref.ref(capsule)
            # Create a Job Object for this task's worker tree
            try:
                from pluma.core.job_object import WindowsJobObject
                capsule.job_object = WindowsJobObject(name=f"pluma-task-{capsule.task_id}")
            except Exception as e:
                logger.warning("Failed to create Job Object for task %s: %s", capsule.task_id, e)

            # Create a task-scoped snapshot registry for UI grounding
            try:
                from pluma.perception.snapshot_registry import SnapshotRegistry
                capsule.snapshot_registry = SnapshotRegistry()
            except Exception as e:
                logger.debug("Failed to create SnapshotRegistry for task %s: %s", capsule.task_id, e)

            with self._admission_lock:
                if not self._closing and not self._global_stop_depth and generation == self._stop_generation:
                    self._tasks[capsule.task_id] = capsule
                    return capsule
                # Preparation straddled a STOP, even if its cleanup has already
                # returned. Do not publish a stale request as new active work.
                capsule.cancellation_token.cancel(StopReason.USER_STOP)
        capsule.close_resources()
        if capsule.cleanup_pending:
            with self._admission_lock:
                self._retained_preparations[capsule.task_id] = capsule
            self._persist_cleanup_report(capsule)
        raise TaskCancelledError("Task creation was cancelled by global STOP.")


    def attach_voice_session(self, capsule, session) -> None:
        with self._admission_lock:
            capsule.cancellation_token.raise_if_cancelled()
            if self._closing or capsule.state != TaskState.CREATED:
                raise TaskCancelledError("Voice task admission closed.")
            capsule.voice_session = session

    def refresh_voice_cleanup(self, capsule) -> None:
        """Read back the retained voice owner after its admitted handler exits.

        Preserve an earlier residual outcome; never repeat rollback or turn a
        pending result into a fabricated clean STOP. Storage remains owned by
        the resident entry gate throughout this readback.
        """
        with self._lock:
            if capsule.terminal_ready.is_set() and capsule.voice_session is not None:
                capsule.close_resources(stopping=capsule.cancellation_token.is_cancelled)
                self._persist_terminal(capsule)
                self.prune_terminal_tasks()

    def start_task(self, task_id: str) -> None:
        """Transition task from CREATED to RUNNING."""
        with self._lock:
            capsule = self._get_task(task_id)
            with self._admission_lock:
                if self._global_stop_depth or self._closing:
                    capsule.cancellation_token.cancel(StopReason.USER_STOP)
                capsule.cancellation_token.raise_if_cancelled()
                self._transition(capsule, TaskState.RUNNING)

    def get_task(self, task_id: str) -> TaskCapsule:
        with self._lock:
            return self._get_task(task_id)

    def get_task_capsule(self, task_id: str) -> TaskCapsule:
        """Alias for get_task."""
        return self.get_task(task_id)

    def transition(self, task_id: str, new_state: TaskState) -> None:
        """Explicitly transition a task to a new state."""
        with self._lock:
            capsule = self._get_task(task_id)
            self._transition(capsule, new_state)
            if new_state in _TERMINAL_STATES:
                self._persist_terminal(capsule)
                capsule.terminal_ready.set()
                self.prune_terminal_tasks()

    def bind_execution(self, ledger: Any = None, rollback_engine: Any = None) -> None:
        """Keep route execution and terminal persistence on the same owners."""
        if ledger is not None:
            if self._ledger is not None and self._ledger is not ledger:
                raise ValueError("Task supervisor already has a different ledger.")
            self._ledger = ledger
        if self._rollback_engine is None and rollback_engine is not None:
            self._rollback_engine = rollback_engine

    def finalize_task(self, task_id: str, requested: TaskState) -> TaskCapsule:
        """Project one authoritative outcome; never overwrite an earlier STOP.

        Terminal commitment and STOP claiming share the short admission lock.
        An overlapping cleanup is awaited outside the resource/state lock. A
        bounded wait that expires exposes the actual nonterminal state.
        """
        if requested not in _TERMINAL_STATES:
            raise ValueError("A terminal state is required.")
        with self._lock:
            capsule = self._get_task(task_id)
            if capsule.state in _TERMINAL_STATES:
                if capsule.terminal_ready.is_set() and capsule.terminal_persisted is False:
                    self._persist_terminal(capsule)
                return capsule
            if capsule.state not in (TaskState.STOPPING, TaskState.ROLLING_BACK):
                try:
                    self._transition(capsule, requested)
                except (TaskCancelledError, InvalidTaskTransition):
                    if not capsule.cancellation_token.is_cancelled:
                        raise
                    # Latch/STOP claim won the commitment race.
                else:
                    self._persist_terminal(capsule)
                    capsule.terminal_ready.set()
                    self.prune_terminal_tasks()
                    return capsule
        self.stop_task(task_id)
        capsule.terminal_ready.wait(timeout=5.0)
        return capsule

    def fail_task_with_rollback(self, task_id: str) -> TaskCapsule:
        """Use the STOP cleanup owner for failed multi-step recovery too."""
        with self._admission_lock:
            capsule = self._get_task(task_id)
            capsule.cancellation_token.cancel(StopReason.INTERNAL_ERROR)
            claimed = self._claim_stop_cleanup(capsule)
        if claimed:
            self._cleanup_stopped_task(capsule, capsule.cancellation_token.reason, 0, failed=True)
        else:
            capsule.terminal_ready.wait(timeout=5.0)
        return capsule

    def _persist_terminal(self, capsule: TaskCapsule) -> None:
        if self._ledger is None:
            return
        # Queued SQLite writes can commit after an acknowledgement timeout.
        # A conservative retry is queued AFTER that write, with the same owner
        # and timestamp. A route must never enqueue its former local outcome.
        for attempt in range(2):
            try:
                persist = self._ledger.finalize_task if capsule.history_expected else self._ledger.finalize_pre_execution
                persist(
                    capsule.task_id, final_state=capsule.state.value,
                    completed_at=capsule.completed_at.isoformat(),
                    stop_reason=capsule.cancellation_token.reason.value if capsule.cancellation_token.reason else None,
                    error_code=("TERMINAL_PERSISTENCE_UNVERIFIED" if capsule.terminal_persisted is False
                                else "TOOL_FAILED" if capsule.state == TaskState.FAILED else None),
                    entries=[item.model_dump() for item in capsule.cleanup_evidence],
                )
                capsule.terminal_persisted = True
                return
            except Exception:
                capsule.terminal_persisted = False
                if attempt == 0:
                    if not any(item.code == "TERMINAL_PERSISTENCE_UNVERIFIED" for item in capsule.cleanup_evidence):
                        capsule.cleanup_evidence.append(CleanupEvidence(resource_id="terminal-ledger:" + capsule.task_id,
                            kind="persistence", code="TERMINAL_PERSISTENCE_UNVERIFIED"))
                    with self._admission_lock:
                        if capsule.state == TaskState.SUCCEEDED:
                            capsule.state = TaskState.FAILED
                        elif capsule.state == TaskState.STOPPED:
                            capsule.state = TaskState.STOPPED_WITH_RESIDUAL

    def mark_succeeded(self, task_id: str) -> None:
        self.transition(task_id, TaskState.SUCCEEDED)

    def mark_failed(self, task_id: str) -> None:
        self.transition(task_id, TaskState.FAILED)

    def stop_task(self, task_id: str, reason: StopReason = StopReason.USER_STOP, grace_s: float = 0.5) -> None:
        """Execute the deterministic STOP sequence (Spec §12.2)."""
        with self._admission_lock:
            capsule = self._get_task(task_id)
            capsule.cancellation_token.cancel(reason)
            if not self._claim_stop_cleanup(capsule):
                return
        self._cleanup_stopped_task(capsule, reason, grace_s)

    def _claim_stop_cleanup(self, capsule: TaskCapsule) -> bool:
        """Claim once under _admission_lock, after the token is latched."""
        if capsule.state in _TERMINAL_STATES or capsule.state in (
            TaskState.STOPPING, TaskState.ROLLING_BACK,
        ):
            return False
        self._transition(capsule, TaskState.STOPPING)
        return True

    def _cleanup_stopped_task(self, capsule: TaskCapsule, reason: StopReason, grace_s: float, *, failed: bool = False) -> None:
        """One STOP claim, with positive evidence before clean terminal state."""
        task_id = capsule.task_id
        if grace_s > 0:
            time.sleep(grace_s)
        capsule.close_resources(stopping=True)
        with self._lock:
            self._transition(capsule, TaskState.ROLLING_BACK)

        # An executor whose absence is unknown can still mutate files. Preserve
        # pre-state/temp resources; never race rollback/deletion against it.
        unsafe = any(item.kind in ("worker", "job") for item in latest_unresolved(capsule.cleanup_evidence))
        irreversible = any(item.get("non_undoable", False) for item in capsule.undo_stack)
        if irreversible:
            capsule.cleanup_evidence.append(CleanupEvidence(resource_id="commits:" + task_id,
                kind="irreversible", code="NON_UNDOABLE_EFFECT_REMAINS"))
        if unsafe:
            capsule.cleanup_evidence.append(CleanupEvidence(resource_id="rollback:" + task_id,
                kind="rollback", code="ROLLBACK_DEFERRED_WORKER_UNVERIFIED"))
            self._defer_temporary_resources(capsule, "TEMP_CLEANUP_DEFERRED_WORKER_UNVERIFIED")
        else:
            rollback = CleanupEvidence(resource_id="rollback:" + task_id, kind="rollback", code="ROLLBACK_UNVERIFIED")
            try:
                from pluma.rollback.engine import RollbackEngine, RollbackResult
                engine = self._rollback_engine or RollbackEngine()
                reversible = [item for item in capsule.undo_stack if not item.get("non_undoable", False)]
                remaining = list(reversible)
                result = engine.rollback_task(task_id=task_id, cancellation_token=capsule.cancellation_token,
                                               memory_undo_stack=remaining)
                if not isinstance(result, RollbackResult):
                    raise ValueError("Rollback evidence missing")
                rollback.verified = (result.all_ok is True and result.has_residual is False
                    and result.steps_failed == 0 and result.steps_attempted == result.steps_succeeded
                    and not remaining)
                rollback.identity = {"attempted": result.steps_attempted, "succeeded": result.steps_succeeded,
                                     "failed": result.steps_failed,
                                     "actions": [item.action for item in result.step_results]}
                rollback.code = "ROLLBACK_VERIFIED" if rollback.verified else "ROLLBACK_RESIDUAL"
                for item in reversible:
                    if item not in remaining and item in capsule.undo_stack:
                        capsule.undo_stack.remove(item)
            except Exception:
                rollback.errors.append("ROLLBACK_FAILED")
            capsule.cleanup_evidence.append(rollback)
            if rollback.verified:
                self._cleanup_temporary_resources(capsule)
            else:
                self._defer_temporary_resources(capsule, "TEMP_CLEANUP_DEFERRED_ROLLBACK_UNVERIFIED")

        self._persist_cleanup_report(capsule)
        final_state = TaskState.STOPPED_WITH_RESIDUAL if capsule.cleanup_pending else TaskState.STOPPED
        if failed and reason in (StopReason.INTERNAL_ERROR, StopReason.TASK_TIMEOUT):
            final_state = TaskState.FAILED
        capsule.cleanup_finalized = True
        with self._lock:
            self._transition(capsule, final_state)
            self._persist_terminal(capsule)
            capsule.terminal_ready.set()
            self.prune_terminal_tasks()

    def _persist_cleanup_report(self, capsule: TaskCapsule) -> None:
        if self._ledger is None:
            return
        try:
            self._ledger.record_cleanup(capsule.task_id, [item.model_dump() for item in capsule.cleanup_evidence])
        except Exception:
            capsule.cleanup_evidence.append(CleanupEvidence(resource_id="ledger:" + capsule.task_id,
                kind="persistence", code="CLEANUP_PERSISTENCE_UNVERIFIED"))
            try:
                self._ledger.record_cleanup(capsule.task_id, [item.model_dump() for item in capsule.cleanup_evidence])
            except Exception:
                pass  # retain ownership/evidence even while storage is unavailable

    def _cleanup_temporary_resources(self, capsule: TaskCapsule) -> None:
        if any(item.kind in ("worker", "job") for item in latest_unresolved(capsule.cleanup_evidence)):
            self._defer_temporary_resources(capsule, "TEMP_CLEANUP_DEFERRED_WORKER_UNVERIFIED")
            return
        from pluma.core.ownership import cleanup_resources
        checks = cleanup_resources(capsule.owned_resources)
        capsule.cleanup_evidence.extend(checks)
        if self._registry is not None:
            try:
                result = self._registry.cleanup_task_resources(capsule.task_id)
                if not isinstance(result, list) or any(not isinstance(item, CleanupEvidence) for item in result):
                    raise ValueError("Resource cleanup evidence missing")
                capsule.cleanup_evidence.extend(result)
            except Exception:
                capsule.cleanup_evidence.append(CleanupEvidence(resource_id="registry:" + capsule.task_id,
                    kind="resources", code="RESOURCE_CLEANUP_UNVERIFIED"))
                self._defer_temporary_resources(capsule, "REGISTRY_RESOURCE_CLEANUP_UNVERIFIED")

    def _defer_temporary_resources(self, capsule: TaskCapsule, code: str) -> None:
        from pluma.core.ownership import cleanup_resources
        resources = list(capsule.owned_resources)
        if self._registry is not None:
            try:
                resources.extend(self._registry.get_owned_resources(capsule.task_id))
            except Exception:
                capsule.cleanup_evidence.append(CleanupEvidence(resource_id="registry-identity:" + capsule.task_id,
                    kind="resources", code="RESOURCE_IDENTITY_READBACK_UNAVAILABLE"))
        capsule.cleanup_evidence.extend(cleanup_resources(resources, deferred=True))
        capsule.cleanup_evidence.append(CleanupEvidence(resource_id="temporary:" + capsule.task_id,
            kind="resources", code=code))

    def begin_shutdown(self) -> None:
        """Permanently reject admission and latch all owners before any drain."""
        with self._admission_lock:
            if not self._closing:
                self._closing = True
                self._stop_generation += 1
            for cap in list(self._tasks.values()) + list(self._retained_preparations.values()):
                if cap.state not in _TERMINAL_STATES or cap.cleanup_pending:
                    cap.cancellation_token.cancel(StopReason.USER_STOP)
        self.execution_gate.begin_shutdown()

    def drain_shutdown_tasks(self) -> None:
        if not self.join_stop_operations(1.0):
            raise RuntimeError("STOP cleanup owners remain active.")
        with self._admission_lock:
            capsules = list(self._tasks.values())
        for cap in capsules:
            if cap.state not in _TERMINAL_STATES:
                self.stop_task(cap.task_id, grace_s=0)
                if not cap.terminal_ready.wait(1.0):
                    raise RuntimeError("Task finalization remains pending.")

    def finalize_shutdown(self) -> None:
        """Read back retained owners and persist after callers have drained."""
        if not self.execution_gate.wait_idle(1.0):
            raise RuntimeError("Execution handlers remain active.")
        if not self.join_stop_operations(1.0):
            raise RuntimeError("STOP cleanup owners remain active.")
        with self._lock:
            with self._admission_lock:
                if self._preparing:
                    raise RuntimeError("Task preparation remains active.")
                capsules = list(self._tasks.values())
                preparations = list(self._retained_preparations.values())
            for cap in capsules + preparations:
                if cap.worker_controller is not None or cap.job_object is not None or cap.snapshot_registry is not None or cap.owned_work or cap.voice_session is not None:
                    cap.close_resources(stopping=True)
                if cap in preparations:
                    if self._ledger is not None:
                        self._ledger.record_cleanup(cap.task_id, [item.model_dump() for item in cap.cleanup_evidence])
                else:
                    if cap.state not in _TERMINAL_STATES or not cap.terminal_ready.is_set():
                        raise RuntimeError("Task outcome remains pending.")
                    self._persist_terminal(cap)
                    if self._ledger is not None and cap.terminal_persisted is not True:
                        raise RuntimeError("Terminal history remains unverified.")
                persistent_jobs = [r for r in cap.owned_resources if r.ownership == ResourceOwnership.PLUMA_CREATED
                                   and r.metadata.get("job_object") is not None]
                if cap.worker_controller is not None or cap.job_object is not None or persistent_jobs or cap.owned_work or cap.voice_session is not None:
                    raise RuntimeError("Owned worker or job remains unverified.")

    def get_active_tasks(self) -> List[TaskCapsule]:
        """Return all tasks in non-terminal states."""
        with self._lock:
            return [
                cap for cap in self._tasks.values()
                if cap.state not in frozenset({
                    TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL, 
                    TaskState.SUCCEEDED, TaskState.FAILED, TaskState.ABORTED_BY_CRASH
                })
            ]

    def stop_all_active_tasks(self) -> List[str]:
        """Latch the whole affected set before any cleanup; return candidate IDs.

        Publication is serialized with the snapshot/latches. Requests preparing
        across this generation are rejected; creation while a global STOP is
        active is rejected. New explicit requests can proceed after it returns.
        Overlapping calls share cleanup claims and keep admission closed until
        the last global caller finishes. Candidate IDs are not terminal proof
        (the separate STOP result/IPC contract is repaired in P08).
        """
        registered = False
        try:
            with self._admission_lock:
                self._global_stop_depth += 1
                registered = True
                self._stop_generation += 1
                affected = [cap for cap in self._tasks.values() if cap.state not in _TERMINAL_STATES]
                for capsule in affected:
                    capsule.cancellation_token.cancel(StopReason.USER_STOP)
                claimed = [cap for cap in affected if self._claim_stop_cleanup(cap)]
            for capsule in claimed:
                try:
                    self._cleanup_stopped_task(capsule, StopReason.USER_STOP, 0.5)
                except Exception as e:
                    logger.error("Error stopping task %s during stop_all: %s", capsule.task_id, e)
            return [cap.task_id for cap in affected]
        finally:
            if registered:
                with self._admission_lock:
                    self._global_stop_depth -= 1

    def join_stop_operations(self, timeout_s=0.0) -> bool:
        """Join retained STOP workers within one shared budget, then release."""
        deadline = _stop_clock() + max(0, timeout_s)
        with self._admission_lock:
            operations = list(self._stop_operations.values())
        complete = True
        for operation in operations:
            if not operation.join(deadline - _stop_clock()):
                complete = False
                continue
            with self._admission_lock:
                self._stop_operations.pop(operation.operation_id, None)
        return complete

    def request_stop(self, task_id=None, *, wait_s=0.1):
        """Latch/claim synchronously; bound acknowledgement separately from cleanup.

        Legacy internal stop methods keep their synchronous contracts. IPC owns
        its cleanup independently of the client connection, with the same claims,
        latch-all generation boundary and deterministic cleanup implementation.
        """
        from pluma.core.stop_protocol import StopOperation, StopReply
        self.join_stop_operations(0)
        global_stop = task_id is None
        with self._admission_lock:
            if global_stop:
                self._global_stop_depth += 1
                self._stop_generation += 1
                affected = [cap for cap in self._tasks.values() if cap.state not in _TERMINAL_STATES]
            else:
                cap = self._tasks.get(task_id)
                affected = [cap] if cap is not None else []
            # Never turn a completed success/failure into a new STOP event.
            active = [cap for cap in affected if cap.state not in _TERMINAL_STATES]
            for cap in active:
                cap.cancellation_token.cancel(StopReason.USER_STOP)
            claimed = []
            for cap in active:
                try:
                    if self._claim_stop_cleanup(cap):
                        claimed.append(cap)
                except Exception:
                    self._stop_error(cap, "STOP_CLEANUP_ERROR")
            operation = StopOperation({cap.task_id: cap for cap in claimed})
            if claimed:
                self._stop_operations[operation.operation_id] = operation
            elif global_stop:
                self._global_stop_depth -= 1

        if claimed:
            def clean():
                try:
                    for cap in claimed:
                        try:
                            self._cleanup_stopped_task(cap, cap.cancellation_token.reason, 0)
                        except Exception:
                            self._stop_error(cap, "STOP_CLEANUP_ERROR")
                            self._persist_cleanup_report(cap)
                        finally:
                            with self._admission_lock:
                                operation.finished.add(cap.task_id)
                finally:
                    if global_stop:
                        with self._admission_lock:
                            self._global_stop_depth -= 1
            try:
                operation.start(clean)
            except Exception:
                with self._admission_lock:
                    for cap in claimed:
                        self._stop_error(cap, "STOP_START_FAILED")
                    if global_stop:
                        self._global_stop_depth -= 1
            operation.join(min(0.1, max(0, wait_s)))
            self.join_stop_operations(0)
        if not affected and not global_stop:
            from pluma.core.stop_protocol import StopOutcome, StopTaskOutcome
            return StopReply(tasks=[StopTaskOutcome(task_id=task_id,
                outcome=StopOutcome.ERROR, latch_acknowledged=False, error_code="TASK_NOT_FOUND")])
        return StopReply(tasks=[self._stop_snapshot(cap) for cap in affected])

    def _stop_error(self, cap, code):
        # Fixed diagnostics only. Never retain raw cleanup exceptions/arguments.
        cap.stop_error = code
        cap.cleanup_evidence.append(CleanupEvidence(resource_id="stop:" + cap.task_id,
            kind="resources", code=code))

    def _stop_snapshot(self, cap):
        from pluma.core.stop_protocol import StopCleanupEvidence, StopOutcome, StopTaskOutcome
        # Resource/ledger owners may hold _lock during external work. An
        # acknowledgement must not wait behind them or infer clean evidence.
        acquired = self._lock.acquire(blocking=False)
        try:
            with self._admission_lock:
                latched = cap.cancellation_token.is_cancelled
                state = cap.state.value
                busy = any(cap.task_id in op.capsules and cap.task_id not in op.finished
                           for op in self._stop_operations.values())
                if not acquired:
                    return StopTaskOutcome(task_id=cap.task_id, outcome=StopOutcome.PENDING,
                        latch_acknowledged=latched, final_state=state,
                        cleanup_in_progress=busy, error_code="EVIDENCE_BUSY")
                details = cap.outcome_details()
                ready = cap.state in _TERMINAL_STATES and cap.terminal_ready.is_set()
                no_owners = (not cap.owned_work and cap.voice_session is None
                    and cap.worker_controller is None and cap.job_object is None
                    and cap.snapshot_registry is None
                    and not any(r.ownership == ResourceOwnership.PLUMA_CREATED
                        and r.metadata.get("persistent_job") is not None for r in cap.owned_resources))
                clean = ready and not busy and no_owners and not details["has_residual"]
                error = cap.stop_error
                if error:
                    outcome = StopOutcome.ERROR
                elif not ready or busy:
                    outcome = StopOutcome.PENDING
                elif cap.state == TaskState.STOPPED_WITH_RESIDUAL or details["has_residual"] or not no_owners:
                    outcome = StopOutcome.RESIDUAL
                elif cap.terminal_persisted is not True:
                    outcome, error = StopOutcome.ERROR, "TERMINAL_HISTORY_UNVERIFIED"
                elif cap.state == TaskState.STOPPED and latched and clean:
                    outcome = StopOutcome.STOPPED
                elif cap.state == TaskState.FAILED:
                    outcome, error = StopOutcome.ERROR, "TASK_FAILED"
                else:
                    outcome = StopOutcome.TERMINAL
                return StopTaskOutcome(task_id=cap.task_id, outcome=outcome,
                    latch_acknowledged=latched, final_state=state,
                    completion_verified=ready, terminal_persisted=cap.terminal_persisted,
                    cleanup_in_progress=busy or (not ready and error is None),
                    cleanup_verified=clean, has_residual=details["has_residual"] or (ready and not no_owners),
                    rollback_performed=details["rollback_performed"], rollback_success=details["rollback_success"],
                    cleanup_evidence=[StopCleanupEvidence.model_validate(item) for item in details["cleanup_evidence"]],
                    error_code=error)
        finally:
            if acquired:
                self._lock.release()

    def _get_task(self, task_id: str) -> TaskCapsule:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found.")
        return self._tasks[task_id]

    def _transition(self, capsule: TaskCapsule, new_state: TaskState) -> None:
        # All state writers share the short latch boundary. Terminal resource
        # work below must not delay a global/single-task latch on another task.
        with self._admission_lock:
            allowed = _TRANSITIONS.get(capsule.state, frozenset())
            if new_state not in allowed:
                raise InvalidTaskTransition(
                    f"Cannot transition from {capsule.state.value} to {new_state.value}"
                )
            if new_state in (TaskState.SUCCEEDED, TaskState.FAILED) and not capsule.cleanup_finalized:
                capsule.cancellation_token.raise_if_cancelled()
            capsule.state = new_state
            if new_state == TaskState.RUNNING and capsule.started_at is None:
                capsule.started_at = datetime.now(timezone.utc)
            if new_state in _TERMINAL_STATES:
                capsule.completed_at = datetime.now(timezone.utc)
        if new_state in _TERMINAL_STATES:
            if not capsule.cleanup_finalized:
                capsule.close_resources(stopping=new_state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL))
                self._cleanup_temporary_resources(capsule)
                self._persist_cleanup_report(capsule)
                if capsule.cleanup_pending and new_state in (TaskState.SUCCEEDED, TaskState.STOPPED):
                    # Finalize this same terminal operation conservatively;
                    # cleanup failure cannot establish success/clean STOP.
                    with self._admission_lock:
                        capsule.state = (TaskState.FAILED if new_state == TaskState.SUCCEEDED
                                         else TaskState.STOPPED_WITH_RESIDUAL)
                capsule.cleanup_finalized = True
            # Unresolved handles/evidence must survive terminal pruning. No
            # computed, unregistered directory is recursively deleted here.
            self.prune_terminal_tasks()
