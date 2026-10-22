"""Run clipboard acceptance in a fresh same-permission local logon context.

Explicit test runner only. No product adapter, elevation, profile loading,
account creation, real credentials or network access is involved.
"""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid


def token_state(process):
    import win32con
    import win32security as security
    token = security.OpenProcessToken(process, win32con.TOKEN_QUERY)
    try:
        return (security.ConvertSidToStringSid(security.GetTokenInformation(token, security.TokenUser)[0]),
                security.GetTokenInformation(token, security.TokenStatistics)['AuthenticationId'],
                security.ConvertSidToStringSid(security.GetTokenInformation(token, security.TokenIntegrityLevel)[0]))
    finally:
        token.Close()


def run(label):
    if not label.startswith(('clipboard-focused-', 'clipboard-regression-')) or not label.replace('-', '').isalnum():
        raise ValueError('Only the closed clipboard test suites are supported.')
    import win32api
    from pluma.core.job_object import owned_process_creation_time
    from pluma.core.task_supervisor import ResourceOwnership, TaskSupervisor, TaskState
    from tests.fixtures.clipboard_station import _api
    user, _ = _api()
    original_clipboard_sequence = user.GetClipboardSequenceNumber()
    original_token = token_state(win32api.GetCurrentProcess())
    root = Path.cwd()
    output = root / 'output/p11_power_actions' / (label + '-logon.json')
    supervisor = TaskSupervisor()
    capsule = supervisor.create_task('p11-native-clipboard-logon-fixture')
    supervisor.start_task(capsule.task_id)

    class Startup(c.Structure):
        _fields_ = [('cb', w.DWORD), ('reserved', w.LPWSTR), ('desktop', w.LPWSTR), ('title', w.LPWSTR),
            ('x', w.DWORD), ('y', w.DWORD), ('width', w.DWORD), ('height', w.DWORD),
            ('chars_x', w.DWORD), ('chars_y', w.DWORD), ('fill', w.DWORD), ('flags', w.DWORD),
            ('show', w.WORD), ('reserved_size', w.WORD), ('reserved_pointer', c.c_void_p),
            ('stdin', w.HANDLE), ('stdout', w.HANDLE), ('stderr', w.HANDLE)]
    class Process(c.Structure):
        _fields_ = [('handle', w.HANDLE), ('thread', w.HANDLE), ('pid', w.DWORD), ('tid', w.DWORD)]
    advanced, kernel = c.WinDLL('advapi32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    create = advanced.CreateProcessWithLogonW
    create.argtypes = [w.LPCWSTR, w.LPCWSTR, w.LPCWSTR, w.DWORD, w.LPCWSTR, w.LPWSTR,
                       w.DWORD, c.c_void_p, w.LPCWSTR, c.POINTER(Startup), c.POINTER(Process)]
    create.restype = w.BOOL
    kernel.ResumeThread.argtypes, kernel.ResumeThread.restype = [w.HANDLE], w.DWORD
    kernel.WaitForSingleObject.argtypes, kernel.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
    kernel.GetExitCodeProcess.argtypes, kernel.GetExitCodeProcess.restype = [w.HANDLE, c.POINTER(w.DWORD)], w.BOOL
    kernel.CloseHandle.argtypes, kernel.CloseHandle.restype = [w.HANDLE], w.BOOL
    kernel.TerminateProcess.argtypes, kernel.TerminateProcess.restype = [w.HANDLE, w.UINT], w.BOOL
    command = c.create_unicode_buffer(subprocess.list2cmdline([sys.executable,
        str(root / 'output/p11_power_actions/run_checks.py'), label]))
    environment = c.create_unicode_buffer('\0'.join(key + '=' + value for key, value in
        sorted(os.environ.items(), key=lambda item: item[0].upper())) + '\0\0')
    startup, process = Startup(), Process()
    startup.cb, startup.flags, startup.show = c.sizeof(Startup), 1, 0
    metadata = {'task_id': capsule.task_id, 'command_class': 'p11_clipboard_test_logon',
                'logon_flags': 2, 'profile_loaded': False, 'credentials': 'ephemeral_unused_network_identity'}
    resource, assigned = None, False
    try:
        # NETCREDENTIALS_ONLY keeps caller local permissions and creates a fresh
        # logon AuthenticationId. Dummy credentials are never used on a network.
        if not create('PLUMA_FIXTURE_NO_NETWORK', '.', uuid.uuid4().hex, 2, sys.executable,
                      command, 0x08000000 | 4 | 0x400, environment, str(root), c.byref(startup), c.byref(process)):
            raise c.WinError(c.get_last_error())
        identity = SimpleNamespace(sentinel=process.handle, pid=process.pid)
        creation = owned_process_creation_time(identity)
        metadata.update(pid=process.pid, creation_time=creation)
        resource = capsule.register_owned_resource('subprocess', ResourceOwnership.PLUMA_CREATED,
            str(process.pid), dict(metadata, lifetime='task'))
        capsule.job_object.assign_process(identity)
        assigned = True
        observed = token_state(process.handle)
        metadata.update(same_user=observed[0] == original_token[0],
                        new_logon=observed[1] != original_token[1],
                        same_integrity=observed[2] == original_token[2])
        assert metadata['same_user'] and metadata['new_logon'] and metadata['same_integrity']
        assert kernel.ResumeThread(process.thread) != 0xffffffff
        deadline = time.monotonic() + 270
        while kernel.WaitForSingleObject(process.handle, 250) == 258:
            if time.monotonic() >= deadline:
                raise TimeoutError('Owned clipboard test runner exceeded its deadline.')
        exit_code = w.DWORD()
        assert kernel.GetExitCodeProcess(process.handle, c.byref(exit_code))
        metadata['runner_exit'] = exit_code.value
    finally:
        # Drain only this suspended/registered process tree, even after startup
        # assertion failures. Read the actual Job count before closing it.
        if process.handle:
            if assigned:
                capsule.job_object.terminate()
            elif kernel.WaitForSingleObject(process.handle, 0) == 258:
                # Containment failed before resume. This is the original handle
                # returned by our own CreateProcess, never a reopened PID.
                assert kernel.TerminateProcess(process.handle, 1)
            assert kernel.WaitForSingleObject(process.handle, 3000) == 0
        metadata['remaining_owned_processes'] = capsule.job_object.active_process_count()
        assert metadata['remaining_owned_processes'] == 0
        if process.thread: assert kernel.CloseHandle(process.thread)
        if process.handle: assert kernel.CloseHandle(process.handle)
        if resource is not None:
            from datetime import datetime, timezone
            resource.released_at = datetime.now(timezone.utc)
        capsule.close_resources()
        metadata['interactive_clipboard_sequence_unchanged'] = user.GetClipboardSequenceNumber() == original_clipboard_sequence
        output.write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        assert metadata['interactive_clipboard_sequence_unchanged']
    supervisor.finalize_task(capsule.task_id, TaskState.SUCCEEDED)
    print(json.dumps(metadata))


if __name__ == '__main__':
    run(sys.argv[1])
