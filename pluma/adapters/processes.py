"""On-demand Windows process reads, retaining the original native process handle.

Imported by tool workers only. psutil uses native Windows process APIs; this
adapter never reads command lines/environments and never launches or kills a PID.
"""
from __future__ import annotations

from contextlib import contextmanager
import sys
import time


def _check_cancel(context):
    token = getattr(context, "cancellation_token", None)
    if token is not None:
        token.raise_if_cancelled()


@contextmanager
def _process(pid, creation_time=None):
    if sys.platform != "win32":
        raise NotImplementedError
    import _winapi
    from types import SimpleNamespace
    import psutil
    from pluma.core.job_object import owned_process_creation_time

    try:
        handle = _winapi.OpenProcess(0x1000 | 0x100000, False, pid)
    except OSError as exc:
        if exc.winerror == 5:
            raise PermissionError from None
        if exc.winerror == 87:
            raise ProcessLookupError from None
        raise
    try:
        identity = owned_process_creation_time(SimpleNamespace(sentinel=handle))
        if (not identity or (creation_time is not None and identity != creation_time)
                or _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_TIMEOUT):
            raise ProcessLookupError
        try:
            yield psutil.Process(pid), identity
        except psutil.AccessDenied:
            raise PermissionError from None
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            raise ProcessLookupError from None
        # A replacement PID cannot make the original process handle live.
        if (_winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_TIMEOUT
                or owned_process_creation_time(SimpleNamespace(sentinel=handle)) != identity):
            raise ProcessLookupError
    finally:
        _winapi.CloseHandle(handle)


def inspect_processes(tool, args, context=None):
    if sys.platform != "win32":
        raise NotImplementedError
    import psutil

    _check_cancel(context)
    observed = time.time_ns()
    if tool == "list_processes":
        pids = sorted(set(psutil.pids()))
        entries = []
        for pid in pids[:args["max_entries"]]:
            _check_cancel(context)
            try:
                with _process(pid) as (process, identity):
                    name = process.name()
                entry = dict(pid=pid, available=True, creation_time=identity,
                             name=name, unavailable_reason=None)
            except (PermissionError, ProcessLookupError, OSError) as exc:
                reason = ("access_denied" if isinstance(exc, PermissionError) else
                          "gone_or_changed" if isinstance(exc, ProcessLookupError) else "unavailable")
                entry = dict(pid=pid, available=False, creation_time=None,
                             name=None, unavailable_reason=reason)
            entries.append(entry)
        _check_cancel(context)
        return dict(observed_at_ns=observed, entries=entries, observed_pid_count=len(pids),
                    truncated=len(pids) > len(entries))
    with _process(args["pid"], args["creation_time"]) as (process, identity):
        data = dict(pid=args["pid"], creation_time=identity, observed_at_ns=observed)
        if tool == "process_info":
            data.update(name=process.name(), status=process.status(), parent_pid=process.ppid(),
                        thread_count=process.num_threads())
        elif tool == "process_usage":
            started = time.perf_counter()
            cpu = process.cpu_percent(interval=0.05)
            data.update(cpu_percent=float(cpu), sample_seconds=time.perf_counter()-started,
                        rss_bytes=process.memory_info().rss)
        else:
            raise ValueError("Unregistered inspection operation.")
        _check_cancel(context)
    return data
