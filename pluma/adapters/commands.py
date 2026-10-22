"""Closed diagnostics and owner-configured commands; never planner shell text."""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import time
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, Field

from pluma.adapters import file_identity as identity
from pluma.adapters.file_operations import _copy_snapshot

MAX_OUTPUT = 65536


class OutputLimitError(ValueError):
    pass


def _literal_path(value):
    path = PureWindowsPath(value)
    if (not path.is_absolute() or len(value) > 32767 or '\0' in value
            or len(path.drive) != 2 or path.drive[1] != ':'
            or any(char in value for char in '*?"<>|')
            or any(part in ('.', '..') or ':' in part or part.endswith(('.', ' '))
                   or PureWindowsPath(part).is_reserved() for part in path.parts[1:])):
        raise ValueError('An explicit local literal filesystem path is required.')
    return identity._checked_path(value)


class CommandEntry(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    argv: list[str] = Field(min_length=1, max_length=32)
    timeout_s: int = Field(default=8, ge=1, le=15)
    inputs: list[str] = Field(default_factory=list, max_length=8)
    encoding: Literal['utf-8', 'oem'] = 'utf-8'


class Project(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    root: str
    commands: dict[str, CommandEntry] = Field(min_length=1, max_length=32)


class Catalog(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    version: Literal[1]
    projects: dict[str, Project] = Field(min_length=1, max_length=32)


def windows_directory():
    c, w, k = identity._api()
    k.GetWindowsDirectoryW.argtypes, k.GetWindowsDirectoryW.restype = [w.LPWSTR, w.UINT], w.UINT
    buffer = c.create_unicode_buffer(32768)
    count = k.GetWindowsDirectoryW(buffer, len(buffer))
    if not 0 < count < len(buffer):
        raise c.WinError()
    return Path(buffer.value)


def diagnostic(tool, command_id):
    system = windows_directory() / 'System32'
    cli = {'hostname': ('hostname.exe', []), 'identity': ('whoami.exe', ['/user', '/fo', 'csv', '/nh']),
           'network': ('ipconfig.exe', [])}
    ps = {'os_version': "[Environment]::OSVersion.Version.ToString()",
          'process_count': '(Microsoft.PowerShell.Management\\Get-Process | Microsoft.PowerShell.Utility\\Measure-Object).Count'}
    if tool == 'run_command':
        name, args = cli[command_id]
        argv = [str(system / name), *args]
    elif tool == 'run_powershell':
        argv = [str(system / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'),
            '-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
            "$ErrorActionPreference='Stop'; [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); " + ps[command_id]]
    else:
        raise ValueError('Unknown diagnostic tool.')
    return {'command_id': command_id, 'argv': argv, 'cwd': str(system), 'timeout_s': 8, 'read_only': True,
            'encoding': 'oem' if tool == 'run_command' else 'utf-8'}


@contextmanager
def _held(paths, *, directories=()):
    with ExitStack() as held:
        targets = [identity._checked_path(path) for path in paths]
        folders = [identity._checked_path(path) for path in directories]
        ancestors = {parent for target in targets + folders for parent in target.parents} | set(folders)
        for parent in sorted(ancestors, key=str):
            held.enter_context(identity._open(parent, parent=True))
        handles = {str(target): held.enter_context(identity._open(target)) for target in targets}
        yield handles


def _private_config(handle):
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        user = security.ConvertSidToStringSid(security.GetTokenInformation(token, security.TokenUser)[0])
    finally:
        token.Close()
    descriptor = security.GetSecurityInfo(handle, security.SE_FILE_OBJECT,
        security.OWNER_SECURITY_INFORMATION | security.DACL_SECURITY_INFORMATION)
    if security.ConvertSidToStringSid(descriptor.GetSecurityDescriptorOwner()) != user:
        raise ValueError('Command catalog must belong to the current user.')
    acl = descriptor.GetSecurityDescriptorDacl()
    if acl is None:
        raise ValueError('Command catalog has no write-protecting DACL.')
    trusted = {user, 'S-1-5-18', 'S-1-5-32-544'}
    for index in range(acl.GetAceCount()):
        ace = acl.GetAce(index)
        kind = ace[0][0]
        if kind not in (0, 1):
            raise ValueError('Unsupported command-catalog access rule.')
        if kind == 0 and ace[1] & 0x500D0156 and security.ConvertSidToStringSid(ace[-1]) not in trusted:
            raise ValueError('Command catalog is writable by an untrusted principal.')


def project_binding(catalog_path, args):
    if not catalog_path:
        raise ValueError('No executor-selected command catalog exists.')
    catalog_path = str(_literal_path(catalog_path))
    with _held([catalog_path]) as handles:
        metadata = identity._metadata(handles[catalog_path])
        if metadata['kind'] != 'file' or metadata['size_bytes'] > 65536:
            raise ValueError('Command catalog exceeds its size bound.')
        _private_config(handles[catalog_path])
        catalog = Catalog.model_validate_json(Path(catalog_path).read_bytes())
        project = catalog.projects[args['project_id']]
        command = project.commands[args['command_id']]
        root = _literal_path(project.root)
        if not root.is_dir():
            raise ValueError('Configured project directory is unavailable.')
        if any(not value or len(value) > 2048 or '\0' in value for value in command.argv):
            raise ValueError('Configured argument exceeds its literal bound.')
        for value in command.argv[1:]:
            if value.startswith(('-', '/')):
                option = value.lstrip('-/').split('=', 1)[0].replace('-', '_').casefold()
                if any(word in option for word in ('password', 'passwd', 'secret', 'token', 'credential', 'api_key', 'apikey', 'private_key')):
                    raise ValueError('Secret-valued command switches require an out-of-band credential interface.')
        executable = _literal_path(command.argv[0])
        if executable.suffix.lower() != '.exe':
            raise ValueError('Configured executable must be an exact native .exe path.')
        if executable.name.lower() in ('runas.exe', 'sudo.exe') or any(
                value.casefold() in ('-verb', 'runas', '-executionpolicy', 'bypass') for value in command.argv[1:]):
            raise ValueError('Configured commands cannot request elevation or policy bypass.')
        inputs = [str(_literal_path(path)) for path in command.inputs]
        if any(not Path(path).is_relative_to(root) for path in inputs):
            raise ValueError('Configured inputs must stay inside the selected project.')
        observed = {path: _copy_snapshot(path) for path in [str(executable), *inputs]}
        binding = {'command_id': args['command_id'], 'project_id': args['project_id'],
            'argv': command.argv, 'cwd': str(root), 'timeout_s': command.timeout_s,
            'encoding': command.encoding,
            'catalog_path': catalog_path, 'catalog_identity': _copy_snapshot(catalog_path),
            'input_identities': observed, 'read_only': False}
        with identity._open(root, parent=True) as parent:
            binding['directory_identity'] = identity._parent_identity(parent)
    from pluma.memory.redaction import redact_sensitive_data
    if redact_sensitive_data(binding) != binding:
        raise ValueError('Private command arguments cannot enter the approval/journal context.')
    return binding


def output_digest(output):
    return list(hashlib.sha256(json.dumps(output, ensure_ascii=True, sort_keys=True).encode()).digest())


def run(binding, context):
    """Start suspended, register/contain before resume; drain pipes without threads."""
    import _winapi
    from pluma.core.job_object import WindowsJobObject, owned_process_creation_time
    from pluma.core.cleanup import cleanup_job
    token = context.cancellation_token
    token.raise_if_cancelled()
    paths = list(binding.get('input_identities', {}))
    if not binding['read_only']:
        paths.append(binding['catalog_path'])
    with _held(paths, directories=[binding['cwd']]) as held:
        for path, expected in binding.get('input_identities', {}).items():
            if _copy_snapshot(path) != expected:
                raise ValueError('Configured executable/input changed after approval.')
        if not binding['read_only']:
            if _copy_snapshot(binding['catalog_path']) != binding['catalog_identity']:
                raise ValueError('Command catalog changed after approval.')
            with identity._open(binding['cwd'], parent=True) as parent:
                if identity._parent_identity(parent) != binding['directory_identity']:
                    raise ValueError('Project directory changed after approval.')
        job, handles, process, thread = WindowsJobObject(), [], None, None
        output = [bytearray(), bytearray()]
        started = time.monotonic()
        try:
            stdin = _winapi.CreateFile('NUL', 0x80000000, 3, 0, 3, 0x80, 0)
            handles.append(stdin)
            pipes = [_winapi.CreatePipe(None, 0), _winapi.CreatePipe(None, 0)]
            for pair in pipes:
                handles.extend(pair)
            for handle in [stdin, pipes[0][1], pipes[1][1]]:
                os.set_handle_inheritable(handle, True)
            startup = subprocess.STARTUPINFO()
            startup.dwFlags = subprocess.STARTF_USESTDHANDLES
            startup.hStdInput, startup.hStdOutput, startup.hStdError = stdin, pipes[0][1], pipes[1][1]
            startup.lpAttributeList = {'handle_list': [stdin, pipes[0][1], pipes[1][1]]}
            env = {key: value for key, value in os.environ.items() if not key.startswith('PLUMA_')}
            env['PSModulePath'] = str(windows_directory() / 'System32/WindowsPowerShell/v1.0/Modules')
            token.raise_if_cancelled()
            process, thread, pid, tid = _winapi.CreateProcess(binding['argv'][0],
                subprocess.list2cmdline(binding['argv']), None, None, True,
                subprocess.CREATE_NO_WINDOW | 4, env, binding['cwd'], startup)
            creation = owned_process_creation_time(SimpleNamespace(sentinel=process))
            context.register_owned_resource('subprocess', 'PLUMA_CREATED', str(pid), {
                'task_id': context.task_id, 'pid': pid, 'creation_time': creation,
                'lifetime': 'task',
                'command_class': 'read_only_diagnostic' if binding['read_only'] else 'configured_project_command'})
            job.assign_process(SimpleNamespace(sentinel=process))
            for handle in [stdin, pipes[0][1], pipes[1][1]]:
                _winapi.CloseHandle(handle)
                handles.remove(handle)
            token.raise_if_cancelled()
            c, w, kernel = identity._api()
            kernel.ResumeThread.argtypes, kernel.ResumeThread.restype = [w.HANDLE], w.DWORD
            if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                raise c.WinError()
            _winapi.CloseHandle(thread)
            thread = None
            eof = [False, False]
            while True:
                token.raise_if_cancelled()
                if time.monotonic() - started > binding['timeout_s']:
                    raise TimeoutError('Command exceeded its configured deadline.')
                for index, pair in enumerate(pipes):
                    if eof[index]:
                        continue
                    try:
                        # Anonymous byte pipes report total available first;
                        # bytes-left-in-message is always zero for byte mode.
                        available = _winapi.PeekNamedPipe(pair[0], 0)[0]
                        if available:
                            data, error = _winapi.ReadFile(pair[0], min(available, 4096))
                            if error:
                                raise OSError('Command output read failed.')
                            output[index].extend(data)
                            if sum(map(len, output)) > MAX_OUTPUT:
                                raise OutputLimitError('Command output exceeds its bound.')
                    except OSError as error:
                        if getattr(error, 'winerror', None) != 109:
                            raise
                        eof[index] = True
                if (_winapi.WaitForSingleObject(process, 0) == _winapi.WAIT_OBJECT_0 and all(eof)
                        and job.active_process_count() == 0):
                    break
                time.sleep(.005)
            exit_code = _winapi.GetExitCodeProcess(process)
            if exit_code != _winapi.GetExitCodeProcess(process) or job.active_process_count() != 0:
                raise ValueError('Native process-tree exit was not verified.')
            text = {'stdout': bytes(output[0]).decode(binding['encoding']),
                    'stderr': bytes(output[1]).decode(binding['encoding'])}
            return {'command_id': binding['command_id'], 'pid': pid, 'creation_time': creation,
                    'exit_code': exit_code, 'command_output': text,
                    'output_encoding': binding['encoding'],
                    'stdout_bytes': len(output[0]), 'stderr_bytes': len(output[1])}, {
                        'exit_readback': exit_code, 'digest': output_digest(text), 'tree_empty': True}
        finally:
            check = cleanup_job(job, 'command-job:' + context.task_id, terminate=True, timeout_s=.5)
            if process is not None:
                _winapi.CloseHandle(process)
            if thread is not None:
                _winapi.CloseHandle(thread)
            for handle in handles:
                _winapi.CloseHandle(handle)
            if not check.verified:
                raise RuntimeError('Owned command cleanup was not verified.')
