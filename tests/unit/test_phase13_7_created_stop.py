"""tests.unit.test_phase13_7_created_stop — Verify STOP is valid in CREATED state."""

import sys
import pytest

from pluma.core.task_supervisor import TaskSupervisor, TaskState

def test_stop_task_in_created_state():
    """Verify that calling stop_task while task is in CREATED state does not crash."""
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule(request_id="test-created-stop")
    
    assert capsule.state == TaskState.CREATED
    
    # Issue STOP command
    supervisor.stop_task(capsule.task_id)
    
    # State should transition cleanly to STOPPED without raising InvalidTaskTransition
    assert capsule.state == TaskState.STOPPED
    assert capsule.cancellation_token.is_cancelled is True
