"""pluma.core.ownership — Subprocess and resource registry.

Spec §12.1, §13: Windows Job Objects for task-owned subprocess trees.
Spec §13: "Every subprocess records PID, creation time, command class, task_id."
Implemented in Phase 1 (Job Object wrapper and process registry).
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pluma.core.task_supervisor import OwnedResource, ResourceOwnership

logger = logging.getLogger(__name__)

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]

    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessTimes.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]


def get_process_creation_time(pid: int) -> Optional[int]:
    """Return the creation time of a PID as a 64-bit integer, or None if unavailable.
    
    This is used to verify PID identity and avoid terminating a reused PID
    after a crash/reboot.
    """
    if sys.platform != "win32":
        return None

    h_process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h_process:
        return None

    try:
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()

        result = kernel32.GetProcessTimes(
            h_process,
            ctypes.byref(creation),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        if result:
            # Combine high and low parts into a 64-bit int.
            return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
        return None
    finally:
        kernel32.CloseHandle(h_process)


class OwnershipRegistry:
    """Tracks PLUMA-owned resources, subprocesses, and temp directories."""

    def __init__(self, db_conn: Any = None) -> None:
        # In a full implementation, we'd sync this with the Activity Ledger.
        # For Phase 1, we keep it in memory and can seed it from DB during crash recovery.
        self._resources_by_task: Dict[str, List[OwnedResource]] = {}
        self._db_conn = db_conn

    def create_task_temp_dir(self, task_id: str) -> Path:
        """Create a task-isolated temporary directory.
        
        Spec §13: "Task temporary files live under a task-specific temp directory
        and are removed on success/stop unless intentionally promoted."
        """
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP") or "/tmp"
        temp_dir = Path(appdata) / "PLUMA" / "tasks" / task_id / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        self.register_resource(
            task_id=task_id,
            resource_type="temp_dir",
            ownership=ResourceOwnership.PLUMA_CREATED,
            external_id=str(temp_dir),
        )
        return temp_dir

    def register_subprocess(
        self,
        task_id: str,
        pid: int,
        ownership: ResourceOwnership,
        command_class: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OwnedResource:
        """Register a subprocess. Records creation time for PID reuse safety."""
        creation_time = get_process_creation_time(pid)
        full_meta = metadata or {}
        full_meta["creation_time"] = creation_time
        full_meta["command_class"] = command_class

        return self.register_resource(
            task_id=task_id,
            resource_type="subprocess",
            ownership=ownership,
            external_id=str(pid),
            metadata=full_meta,
        )

    def register_resource(
        self,
        task_id: str,
        resource_type: str,
        ownership: ResourceOwnership,
        external_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OwnedResource:
        """Register any resource (file, tab, process, etc.)."""
        resource = OwnedResource(
            resource_type=resource_type,
            ownership=ownership,
            external_id=external_id,
            metadata=metadata or {},
        )
        
        if task_id not in self._resources_by_task:
            self._resources_by_task[task_id] = []
        self._resources_by_task[task_id].append(resource)
        
        logger.debug("Registered %s resource %s (%s) for task %s", 
                     ownership.value, resource_type, external_id, task_id)
        return resource

    def get_owned_resources(
        self, task_id: str, ownership_filter: Optional[ResourceOwnership] = None
    ) -> List[OwnedResource]:
        """Return resources for a task, optionally filtered by ownership."""
        resources = self._resources_by_task.get(task_id, [])
        if ownership_filter:
            return [r for r in resources if r.ownership == ownership_filter]
        return resources

    def verify_pid_identity(self, pid: int, expected_creation_time: Optional[int]) -> bool:
        """Verify that a PID hasn't been recycled since we registered it.
        
        Spec §12.1: Cleanup refuses a PID without matching creation metadata.
        """
        if expected_creation_time is None:
            # If we couldn't get it originally, we can't safely verify it now.
            # Fail closed.
            return False
            
        current_time = get_process_creation_time(pid)
        if current_time is None:
            # Process doesn't exist anymore.
            return False
            
        return current_time == expected_creation_time

    def cleanup_task_resources(self, task_id: str) -> None:
        """Close/delete PLUMA_CREATED temp directories and files.
        
        Does not terminate processes (TaskSupervisor does that via Job Objects).
        Leaves PREEXISTING resources untouched.
        """
        resources = self.get_owned_resources(task_id, ResourceOwnership.PLUMA_CREATED)
        for res in resources:
            if res.resource_type == "temp_dir" and res.external_id:
                path = Path(res.external_id)
                if path.exists() and path.is_dir():
                    try:
                        shutil.rmtree(path)
                        logger.debug("Cleaned up temp_dir: %s", path)
                    except Exception as e:
                        logger.error("Failed to clean temp_dir %s: %s", path, e)
            elif res.resource_type == "temp_file" and res.external_id:
                path = Path(res.external_id)
                if path.exists() and path.is_file():
                    try:
                        path.unlink()
                        logger.debug("Cleaned up temp_file: %s", path)
                    except Exception as e:
                        logger.error("Failed to clean temp_file %s: %s", path, e)
