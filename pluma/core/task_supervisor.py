"""pluma.core.task_supervisor — TaskCapsule, TaskState, and TaskSupervisor.

Spec §12: Every user command becomes one TaskCapsule. All tool calls,
subprocesses, temporary resources, undo records and screen snapshots belong
to that capsule. The TaskSupervisor owns the state machine and the
cancellation tree.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pluma.core.cancellation import CancellationToken, StopReason

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
    TaskState.CREATED: frozenset({TaskState.RUNNING, TaskState.FAILED, TaskState.ABORTED_BY_CRASH}),
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

    # Job Object wrapper for process containment (not serializable)
    job_object: Any = Field(default=None, exclude=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    @property
    def stop_latch_set(self) -> bool:
        return self.cancellation_token.is_cancelled


class TaskSupervisor:
    """Highest-priority runtime authority for task lifecycle and cancellation.
    
    Spec §12: Owns task state, cancellation, child processes, stop and cleanup.
    """

    def __init__(
        self,
        ownership_registry: Any = None,
        ledger: Any = None,
        rollback_engine: Any = None,
    ) -> None:
        self._registry = ownership_registry
        self._ledger = ledger
        self._rollback_engine = rollback_engine
        self._tasks: Dict[str, TaskCapsule] = {}
        self._lock = threading.RLock()

    def create_task(self, request_id: str) -> TaskCapsule:
        """Create a new TaskCapsule in CREATED state."""
        with self._lock:
            capsule = TaskCapsule(request_id=request_id)
            
            # Create a Job Object for this task's worker tree
            try:
                from pluma.core.job_object import WindowsJobObject
                capsule.job_object = WindowsJobObject(name=f"pluma-task-{capsule.task_id}")
            except Exception as e:
                logger.warning("Failed to create Job Object for task %s: %s", capsule.task_id, e)

            self._tasks[capsule.task_id] = capsule
            return capsule

    def start_task(self, task_id: str) -> None:
        """Transition task from CREATED to RUNNING."""
        with self._lock:
            capsule = self._get_task(task_id)
            self._transition(capsule, TaskState.RUNNING)

    def get_task(self, task_id: str) -> TaskCapsule:
        with self._lock:
            return self._get_task(task_id)

    def transition(self, task_id: str, new_state: TaskState) -> None:
        """Explicitly transition a task to a new state."""
        with self._lock:
            capsule = self._get_task(task_id)
            self._transition(capsule, new_state)
            if new_state in _TERMINAL_STATES and self._ledger:
                try:
                    self._ledger.update_task(
                        task_id,
                        final_state=new_state.value,
                        completed_at=datetime.now(timezone.utc).isoformat(),
                    )
                except Exception as e:
                    logger.error("Failed to update task %s final state in ledger: %s", task_id, e)

    def mark_succeeded(self, task_id: str) -> None:
        self.transition(task_id, TaskState.SUCCEEDED)

    def mark_failed(self, task_id: str) -> None:
        self.transition(task_id, TaskState.FAILED)

    def stop_task(self, task_id: str, reason: StopReason = StopReason.USER_STOP) -> None:
        """Execute the deterministic STOP sequence (Spec §12.2)."""
        with self._lock:
            capsule = self._get_task(task_id)
            
            if capsule.state in frozenset({TaskState.STOPPED, TaskState.STOPPING, 
                                           TaskState.STOPPED_WITH_RESIDUAL, TaskState.ABORTED_BY_CRASH,
                                           TaskState.SUCCEEDED, TaskState.FAILED}):
                # Already terminal or stopping.
                # Spec §12.1: "The latch is set even if the state transition fails (already terminal)."
                capsule.cancellation_token.cancel(reason)
                return

            # 1. Atomic task.stop_latch = true (and request graceful cancellation)
            capsule.cancellation_token.cancel(reason)
            
            # 2. Transition state (blocks new ToolCalls/replans)
            self._transition(capsule, TaskState.STOPPING)
            
        # The following steps are executed outside the lock to avoid deadlocks 
        # during cleanup or rollback.
        
        # 3. Terminate unresponsive PLUMA-owned Job Object workers
        if capsule.job_object:
            try:
                capsule.job_object.terminate(exit_code=1)
                capsule.job_object.close()
                capsule.job_object = None
            except Exception as e:
                logger.error("Failed to terminate job object for %s: %s", task_id, e)

        # 4. Rollback safe reversible actions in reverse order (Spec §13)
        has_residual = any(u.get("non_undoable", False) for u in capsule.undo_stack)
        with self._lock:
            self._transition(capsule, TaskState.ROLLING_BACK)

        if self._rollback_engine is not None:
            try:
                rollback_res = self._rollback_engine.rollback_task(
                    task_id=task_id,
                    cancellation_token=capsule.cancellation_token,
                    memory_undo_stack=capsule.undo_stack,
                )
                if rollback_res.has_residual:
                    has_residual = True
            except Exception as e:
                logger.error("Rollback execution error on task %s: %s", task_id, e)
                has_residual = True
        elif capsule.undo_stack:
            # Fallback basic rollback if engine not injected
            try:
                from pluma.rollback.recipes import RollbackRecipes
                recipes = RollbackRecipes()
                for undo_item in reversed(capsule.undo_stack):
                    action_name = undo_item.get("action", "")
                    res = recipes.apply(action_name, undo_item)
                    if not res.ok:
                        has_residual = True
            except Exception as e:
                logger.error("Basic fallback rollback error on task %s: %s", task_id, e)
                has_residual = True
        
        # 5. Close/delete task-owned temporary resources
        if self._registry:
            self._registry.cleanup_task_resources(task_id)
        
        # 6. Mark final state
        final_state = TaskState.STOPPED_WITH_RESIDUAL if has_residual else TaskState.STOPPED
        with self._lock:
            self._transition(capsule, final_state)

        # 7. Update ledger if present
        if self._ledger:
            try:
                self._ledger.update_task(
                    task_id,
                    final_state=final_state.value,
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    stop_reason=reason.value,
                )
            except Exception as e:
                logger.error("Failed to update task %s final state in ledger: %s", task_id, e)

    def stop_all_active_tasks(self) -> None:
        """Emergency stop for all non-terminal tasks."""
        with self._lock:
            active_ids = [
                task_id for task_id, cap in self._tasks.items()
                if cap.state not in frozenset({
                    TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL, 
                    TaskState.SUCCEEDED, TaskState.FAILED, TaskState.ABORTED_BY_CRASH
                })
            ]
        for tid in active_ids:
            self.stop_task(tid)

    def _get_task(self, task_id: str) -> TaskCapsule:
        if task_id not in self._tasks:
            raise KeyError(f"Task {task_id} not found.")
        return self._tasks[task_id]

    def _transition(self, capsule: TaskCapsule, new_state: TaskState) -> None:
        allowed = _TRANSITIONS.get(capsule.state, frozenset())
        if new_state not in allowed:
            raise InvalidTaskTransition(
                f"Cannot transition from {capsule.state.value} to {new_state.value}"
            )
        capsule.state = new_state
        if new_state == TaskState.RUNNING and capsule.started_at is None:
            capsule.started_at = datetime.now(timezone.utc)
        if new_state in _TERMINAL_STATES:
            capsule.completed_at = datetime.now(timezone.utc)
