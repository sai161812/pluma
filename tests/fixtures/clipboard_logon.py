"""Run clipboard acceptance in a fresh same-permission local logon context.

Explicit test runner only. No product adapter, elevation, profile loading,
account creation, real credentials or network access is involved.
"""
import ctypes as c
from ctypes import wintypes as w
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
from types import SimpleNamespace
import uuid
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[2]
REGRESSION = ("test_clipboard_native.py", "test_clipboard_write.py", "test_tools_clipboard.py",
    "test_brain_prompt_builder.py", "test_brain_tool_subset.py", "test_redaction.py",
    "test_policy_boundary.py", "test_tool_runner_ledger.py", "test_executor_admission.py",
    "test_worker_cancellation.py", "test_runtime_shutdown.py", "test_manual_undo.py",
    "test_memory_tools.py", "test_rollback_engine.py", "test_rollback_recipes.py",
    "test_mutation_journal.py", "test_verification_ownership.py")


def validate_label(label):
    if not label.startswith(('clipboard-focused-', 'clipboard-regression-')) or not label.replace('-', '').isalnum():
        raise ValueError('Only the closed clipboard test suites are supported.')


def new_output_directory(label, output_dir=None):
    validate_label(label)
    parent = (ROOT / 'output').resolve()
    base = Path(output_dir).resolve() if output_dir else parent / 'clipboard-acceptance'
    if not base.is_relative_to(parent):
        raise ValueError('Clipboard reports must remain under ignored output.')
    directory = base / label
    directory.mkdir(parents=True, exist_ok=False)
    return directory


def accepted_test_exit(code, suites):
    """A skip, xfail, empty report or inconsistent JUnit is never acceptance."""
    if code != 0:
        return code
    if not suites or sum(int(row.get('tests', 0)) for row in suites) == 0:
        return 1
    return 1 if any(int(row.get(key, 0)) for row in suites
                    for key in ('skipped', 'failures', 'errors')) else 0


def run_checks(label, directory):
    """Closed child selection, executed only inside the parent's owned Job."""
    validate_label(label)
    directory = Path(directory).resolve()
    if not directory.is_relative_to((ROOT / 'output').resolve()) or directory.name != label:
        raise ValueError('An owned clipboard evidence directory is required.')
    targets = REGRESSION if label.startswith('clipboard-regression-') else ('test_clipboard_native.py',)
    command = [sys.executable, '-m', 'pytest', *('tests/unit/' + name for name in targets),
        '-q', '--runxfail', '-o', 'junit_family=xunit1', '-p', 'no:cacheprovider',
        '-W', 'error::pytest.PytestUnhandledThreadExceptionWarning',
        '--junitxml=' + str(directory / 'tests.xml')]
    environment = {key: value for key, value in os.environ.items() if not key.startswith('PLUMA_')}
    private = Path(tempfile.mkdtemp(prefix='pluma-clipboard-'))
    for key in ('APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP'):
        path = private / key
        path.mkdir()
        environment[key] = str(path)
    started = time.monotonic()
    metadata = {'command': command, 'source_commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_hashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ('pluma', 'tests') for path in (ROOT / folder).rglob('*.py')}}
    try:
        with (directory / 'tests.txt').open('x', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, env=environment,
                stdout=log, stderr=subprocess.STDOUT, timeout=240)
        suites = [row.attrib for row in ET.parse(directory / 'tests.xml').getroot().iter('testsuite')]
        metadata.update(exit=accepted_test_exit(result.returncode, suites), pytest_exit=result.returncode, junit=suites)
    except subprocess.TimeoutExpired:
        metadata.update(exit=124, error='CLIPBOARD_SUITE_TIMEOUT')
    metadata['wall_seconds'] = round(time.monotonic() - started, 3)
    with (directory / 'tests.json').open('x', encoding='utf-8') as report:
        json.dump(metadata, report, indent=2)
    return metadata['exit']


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


def recorded_test_exit(path):
    """A successfully closed runner is not evidence that its pytest run passed."""
    report = json.loads(path.read_text(encoding='utf-8'))
    code = report.get('exit')
    if type(code) is not int or code < 0:
        raise ValueError('Missing or invalid clipboard test exit status.')
    return code


def run(label, output_dir=None):
    directory = new_output_directory(label, output_dir)
    import win32api
    from pluma.core.job_object import owned_process_creation_time
    from pluma.core.task_supervisor import ResourceOwnership, TaskSupervisor, TaskState
    from tests.fixtures.clipboard_station import _api
    user, _ = _api()
    original_clipboard_sequence = user.GetClipboardSequenceNumber()
    original_token = token_state(win32api.GetCurrentProcess())
    root = ROOT
    output = directory / 'logon.json'
    test_report = directory / 'tests.json'
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
        '-m', 'tests.fixtures.clipboard_logon', label, '--child', '--output-dir', str(directory)]))
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
        metadata['test_exit'] = recorded_test_exit(test_report)
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
        with output.open('x', encoding='utf-8') as report:
            json.dump(metadata, report, indent=2)
        assert metadata['interactive_clipboard_sequence_unchanged']
    passed = metadata['runner_exit'] == 0 and metadata['test_exit'] == 0
    supervisor.finalize_task(capsule.task_id, TaskState.SUCCEEDED if passed else TaskState.FAILED)
    print(json.dumps(metadata))
    return 0 if passed else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label')
    parser.add_argument('--output-dir')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    options = parser.parse_args()
    raise SystemExit(run_checks(options.label, options.output_dir) if options.child
                     else run(options.label, options.output_dir))
