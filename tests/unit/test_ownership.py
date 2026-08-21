"""tests.unit.test_ownership — Tests for OwnershipRegistry and crash-safe metadata."""

import os
import subprocess
import sys
from pathlib import Path

from pluma.core.ownership import OwnershipRegistry, get_process_creation_time
from pluma.core.task_supervisor import ResourceOwnership


def test_get_process_creation_time() -> None:
    # We can test with our own process
    pid = os.getpid()
    creation_time = get_process_creation_time(pid)
    
    if sys.platform == "win32":
        assert creation_time is not None
        assert isinstance(creation_time, int)
        assert creation_time > 0
    else:
        assert creation_time is None


def test_register_subprocess_metadata() -> None:
    registry = OwnershipRegistry()
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    try:
        res = registry.register_subprocess(
            task_id="task-123",
            pid=proc.pid,
            ownership=ResourceOwnership.PLUMA_CREATED,
            command_class="python_sleep",
        )
        
        assert res.resource_type == "subprocess"
        assert res.external_id == str(proc.pid)
        assert res.metadata["command_class"] == "python_sleep"
        if sys.platform == "win32":
            assert res.metadata["creation_time"] is not None
            
        # Verify it's retrieved
        owned = registry.get_owned_resources("task-123", ResourceOwnership.PLUMA_CREATED)
        assert len(owned) == 1
        assert owned[0] == res
    finally:
        proc.kill()
        proc.wait()


def test_temp_dir_creation_and_cleanup(tmp_path: Path, monkeypatch: object) -> None:
    # Mock LOCALAPPDATA to point to our pytest tmp_path
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # type: ignore[attr-defined]
    
    registry = OwnershipRegistry()
    task_id = "task-456"
    
    temp_dir = registry.create_task_temp_dir(task_id)
    assert temp_dir.exists()
    assert temp_dir.is_dir()
    
    # Create a file inside to ensure it gets cleaned up recursively
    (temp_dir / "test.txt").write_text("hello")
    
    registry.cleanup_task_resources(task_id)
    
    # Directory should be gone
    assert not temp_dir.exists()


def test_preexisting_resource_safety() -> None:
    registry = OwnershipRegistry()
    task_id = "task-789"
    
    # Register a preexisting "file"
    registry.register_resource(
        task_id=task_id,
        resource_type="temp_file",
        ownership=ResourceOwnership.PREEXISTING,
        external_id="C:\\important\\file.txt",
    )
    
    # This shouldn't do anything since we only clean PLUMA_CREATED
    # If it tried to clean C:\important\file.txt, it would either fail or we'd catch it.
    registry.cleanup_task_resources(task_id)
    
    owned = registry.get_owned_resources(task_id)
    assert len(owned) == 1
    assert owned[0].ownership == ResourceOwnership.PREEXISTING


def test_verify_pid_identity() -> None:
    registry = OwnershipRegistry()
    
    if sys.platform != "win32":
        return
        
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    try:
        creation_time = get_process_creation_time(proc.pid)
        assert creation_time is not None
        
        # Exact match passes
        assert registry.verify_pid_identity(proc.pid, creation_time) is True
        
        # Mismatched time fails
        assert registry.verify_pid_identity(proc.pid, creation_time + 1) is False
        
        # None expected time fails
        assert registry.verify_pid_identity(proc.pid, None) is False
    finally:
        proc.kill()
        proc.wait()
