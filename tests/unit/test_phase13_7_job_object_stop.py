"""tests.unit.test_phase13_7_job_object_stop — Verify Job Object parenting on TaskCapsule."""

import sys
import os
import time
import pytest
import subprocess

from pluma.core.task_supervisor import TaskSupervisor, ResourceOwnership, TaskState
from pluma.tools.registry import get_default_tool_registry

def test_job_object_created_in_parent_and_stop_terminates():
    """Verify that Job Object is created in the parent process and STOP kills it."""
    if sys.platform != "win32":
        pytest.skip("Windows only Job Object test")

    registry = get_default_tool_registry()
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task_capsule(request_id="test-job-obj")
    
    # Pre-spawn an independent process to prove we don't kill unrelated processes
    independent = subprocess.Popen(["charmap.exe"], creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0))
    time.sleep(0.5)

    try:
        # We explicitly unset PLUMA_TEST_MODE here so open_app launches a real process
        old_test_mode = os.environ.get("PLUMA_TEST_MODE")
        if old_test_mode is not None:
            del os.environ["PLUMA_TEST_MODE"]
        
        try:
            res = registry.execute("open_app", {"app_name": "charmap.exe"}, task_context=capsule)
        finally:
            if old_test_mode is not None:
                os.environ["PLUMA_TEST_MODE"] = old_test_mode

        assert res.ok is True
        
        pid = res.data["pid"]
        
        # Verify the parent task capsule has the persistent job object
        assert len(capsule.owned_resources) == 1
        res_obj = capsule.owned_resources[0]
        assert res_obj.resource_type == "subprocess"
        assert res_obj.ownership == ResourceOwnership.PLUMA_CREATED
        assert "persistent_job" in res_obj.metadata
        assert res_obj.metadata["persistent_job"] is not None
        
        # Start the task, then STOP it
        supervisor.start_task(capsule.task_id)
        supervisor.stop_task(capsule.task_id, grace_s=0.0)
        
        assert capsule.state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
        
        time.sleep(1.0)
        
        # Check tasklist for the specific PID
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert "charmap.exe" not in out.lower(), f"PLUMA spawned process {pid} is still running!"
        
        # Verify the independent process is still running
        out_ind = subprocess.check_output(["tasklist", "/FI", f"PID eq {independent.pid}", "/NH"], text=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        assert "charmap.exe" in out_ind.lower(), f"Independent process {independent.pid} was incorrectly killed!"
        
    finally:
        try:
            independent.kill()
        except Exception:
            pass
