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
import stat
from typing import Any, Dict, List, Optional

from pluma.core.task_supervisor import OwnedResource, ResourceOwnership

logger = logging.getLogger(__name__)


def capture_temp_identity(path: Path) -> Dict[str, int]:
    info = path.lstat()
    if getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        raise ValueError("Reparse point cannot be claimed as temporary storage.")
    return {"device": info.st_dev, "inode": info.st_ino,
            "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def subprocess_absent(pid: int, creation_time: Optional[int]) -> bool:
    """Read only; a replacement PID is never terminated or otherwise touched."""
    if sys.platform != "win32" or type(creation_time) is not int:
        return False
    import _winapi
    from types import SimpleNamespace
    from pluma.core.job_object import owned_process_creation_time
    try:
        handle = _winapi.OpenProcess(0x100000 | 0x1000, False, pid)
    except OSError as exc:
        return exc.winerror == 87  # absent PID, not access denied/unavailable
    try:
        if _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_OBJECT_0:
            return True
        return owned_process_creation_time(SimpleNamespace(sentinel=handle)) != creation_time
    finally:
        _winapi.CloseHandle(handle)


def cleanup_resources(resources: List[OwnedResource], *, deferred: bool = False):
    from pluma.core.cleanup import CleanupEvidence
    evidence = []
    for res in resources:
        if res.ownership != ResourceOwnership.PLUMA_CREATED:
            continue
        identity = {"resource_type": res.resource_type, "external_id": res.external_id,
                    "temp_identity": res.metadata.get("cleanup_identity"),
                    "creation_time": res.metadata.get("creation_time", res.metadata.get("creation_time_ns")),
                    "command_class": res.metadata.get("command_class")}
        check = CleanupEvidence(resource_id=res.resource_id, kind="resource", identity=identity,
                                code="RESOURCE_CLEANUP_UNVERIFIED")
        if res.released_at is not None:
            check.verified = True
            check.code = "RESOURCE_OWNERSHIP_ALREADY_RELEASED"
            evidence.append(check)
            continue  # the same path/PID may now belong to a different resource
        if deferred:
            check.code = "RESOURCE_CLEANUP_DEFERRED"
            evidence.append(check)
            continue
        if res.resource_type in ("temp_dir", "temp_file") and res.external_id:
            path = Path(res.external_id)
            try:
                try:
                    current = capture_temp_identity(path)
                except FileNotFoundError:
                    current = None
                expected = res.metadata.get("cleanup_identity")
                if current is None:
                    check.verified = True
                elif not expected or any(current[k] != expected.get(k) for k in ("device", "inode")):
                    check.code = "TEMP_IDENTITY_CHANGED_OR_MISSING"
                elif res.resource_type == "temp_file" and any(current[k] != expected.get(k) for k in ("size", "mtime_ns")):
                    check.code = "TEMP_FILE_CHANGED"
                else:
                    if res.resource_type == "temp_dir":
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    try:
                        path.lstat()
                    except FileNotFoundError:
                        check.verified = True
            except Exception:
                check.errors.append("TEMP_CLEANUP_OR_READBACK_FAILED")
        elif res.resource_type == "subprocess" and res.external_id:
            try:
                check.verified = subprocess_absent(int(res.external_id), identity["creation_time"])
            except Exception:
                check.errors.append("PROCESS_READBACK_FAILED")
        else:
            check.code = "RESOURCE_CLEANUP_ADAPTER_UNAVAILABLE"
        if check.verified:
            from datetime import datetime, timezone
            check.code = "RESOURCE_ABSENCE_VERIFIED"
            res.released_at = datetime.now(timezone.utc)
        evidence.append(check)
    return evidence

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


def adopt_contained_process(pid, creation_time, task_job):
    """Adopt only an exact live handle already contained by this task's Job.

    Reused/unowned PIDs are never assigned or terminated. A failed promotion
    stays inside the original worker/task containment for ordinary cleanup.
    """
    import _winapi
    import ctypes as c
    from ctypes import wintypes as w
    from types import SimpleNamespace
    from pluma.core.job_object import WindowsJobObject, owned_process_creation_time
    if type(pid) is not int or type(creation_time) is not int or not getattr(task_job, '_handle', None):
        raise ValueError('Exact process identity and task containment are required.')
    handle = _winapi.OpenProcess(0x101101, False, pid)
    job = None
    try:
        process = SimpleNamespace(sentinel=handle)
        if owned_process_creation_time(process) != creation_time or _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_TIMEOUT:
            raise ValueError('Process exited or its identity changed.')
        kernel = c.WinDLL('kernel32', use_last_error=True)
        kernel.IsProcessInJob.argtypes, kernel.IsProcessInJob.restype = [w.HANDLE, w.HANDLE, c.POINTER(w.BOOL)], w.BOOL
        member = w.BOOL()
        if not kernel.IsProcessInJob(handle, task_job._handle, c.byref(member)) or not member.value:
            raise ValueError('Process does not belong to the original task Job.')
        job = WindowsJobObject(kill_on_close=False)
        job.assign_process(process)
        return job
    except Exception:
        if job is not None:
            job.close()
        raise
    finally:
        _winapi.CloseHandle(handle)


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
        from pluma.config.paths import get_paths
        temp_dir = get_paths().task_temp_dir(task_id)
        # Never take ownership of an already existing user/recovery directory.
        temp_dir.mkdir(parents=True, exist_ok=False)
        
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
        safe_metadata = dict(metadata or {})
        if ownership == ResourceOwnership.PLUMA_CREATED and resource_type in ("temp_dir", "temp_file") and external_id:
            try:
                safe_metadata["cleanup_identity"] = capture_temp_identity(Path(external_id))
            except (OSError, ValueError):
                pass  # unknown identity is retained and fails cleanup closed
        resource = OwnedResource(
            resource_type=resource_type,
            ownership=ownership,
            external_id=external_id,
            metadata=safe_metadata,
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

    def is_owned_resource(self, task_id: str, resource_type: str, external_id: str) -> bool:
        """Check if a specific resource is recorded as owned by a task."""
        resources = self._resources_by_task.get(task_id, [])
        return any(r.resource_type == resource_type and r.external_id == external_id for r in resources)

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

    def cleanup_task_resources(self, task_id: str):
        """Close/delete PLUMA_CREATED temp directories and files.
        
        Does not terminate processes (TaskSupervisor does that via Job Objects).
        Leaves PREEXISTING resources untouched.
        """
        return cleanup_resources(self.get_owned_resources(task_id, ResourceOwnership.PLUMA_CREATED))
