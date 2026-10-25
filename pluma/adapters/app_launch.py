"""Closed native application launches owned before resume, outside transient workers."""
from contextlib import ExitStack
from pathlib import Path
import os
import subprocess
import time
from types import SimpleNamespace
import uuid

from pluma.adapters import file_identity as files
from pluma.adapters.commands import windows_directory, _literal_path
from pluma.adapters.processes import _process

APPLICATIONS = {'notepad': 'notepad.exe', 'paint': 'mspaint.exe', 'mspaint': 'mspaint.exe',
    'calculator': 'calc.exe', 'calc': 'calc.exe', 'charmap': 'charmap.exe',
    'snippingtool': 'SnippingTool.exe', 'taskmgr': 'taskmgr.exe'}


class _OriginalProcessOwner:
    """Retain the original handle if a pre-assignment native cleanup fails."""
    def __init__(self, handle): self.handle = handle
    @property
    def is_closed(self): return self.handle is None
    def active_process_count(self):
        import _winapi
        result = _winapi.WaitForSingleObject(self.handle, 0)
        if result not in (_winapi.WAIT_OBJECT_0, _winapi.WAIT_TIMEOUT): raise OSError('Native process state unavailable.')
        return int(result == _winapi.WAIT_TIMEOUT)
    def terminate(self, exit_code=1):
        import _winapi
        if self.active_process_count(): _winapi.TerminateProcess(self.handle, exit_code)
    def close(self):
        import _winapi
        if self.handle is not None: _winapi.CloseHandle(self.handle); self.handle = None


def binding(args):
    key = args['app_name'].casefold().removesuffix('.exe')
    if key not in APPLICATIONS or args.get('arguments'):
        raise ValueError('Only a registered application alias with fixed arguments is supported.')
    image = _literal_path(str(windows_directory() / 'System32' / APPLICATIONS[key]))
    cwd = _literal_path(args['working_dir']) if args.get('working_dir') else image.parent
    with files._open(cwd, parent=True) as handle:
        directory = files._parent_identity(handle)
    return {'argv': [str(image)], 'cwd': str(cwd), 'image_identity': files.snapshot(str(image)),
            'directory_identity': directory}


def capture(args, context):
    context.cancellation_token.raise_if_cancelled()
    return dict(action='app_launch', guard_version=1, tool='open_app',
                launch_id=str(uuid.uuid4()), app_name=args['app_name'], **binding(args))


def windows(pid, creation):
    from pluma.adapters.app_windows import _api
    import win32gui
    c, w, user = _api()
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, w.LPARAM], w.BOOL
    found, errors, count = [], [], 0
    def inspect(hwnd, ignored):
        nonlocal count
        try:
            count += 1
            if count > 4096: raise ValueError('Window enumeration exceeded its bound.')
            owner = w.DWORD()
            thread = user.GetWindowThreadProcessId(hwnd, c.byref(owner))
            if not thread or owner.value != pid or not user.IsWindowVisible(hwnd): return True
            if win32gui.GetWindowLong(hwnd, -20) & (0x80 | 0x08000000):
                return True  # tool/no-activate overlays are not an application view
            name = c.create_unicode_buffer(257)
            if not user.GetClassNameW(hwnd, name, len(name)): raise c.WinError()
            import hashlib
            found.append({'hwnd': hwnd, 'pid': pid, 'creation_time': creation, 'thread_id': thread,
                'class_digest': list(hashlib.sha256(name.value.encode('utf-16-le')).digest())})
            if len(found) > 16: raise ValueError('Application window count exceeded its bound.')
            return True
        except Exception as error:
            errors.append(error); return False
    c.set_last_error(0)
    result = user.EnumWindows(callback_type(inspect), 0)
    if errors or not result and c.get_last_error():
        raise ValueError('Native application window observation failed.')
    return sorted(found, key=lambda value: value['hwnd'])


def startup_info():
    import win32process
    return win32process.STARTUPINFO()


def create_process(image, argv, cwd, *, environment=None, new_console=False):
    import win32process
    info = startup_info()
    process, thread, pid, tid = win32process.CreateProcess(image, subprocess.list2cmdline(argv),
        None, None, False, 4 | (subprocess.CREATE_NEW_CONSOLE if new_console else subprocess.CREATE_NO_WINDOW),
        environment, cwd, info)
    return process.Detach(), thread.Detach(), pid, tid


def launch(state, context):
    import _winapi
    from pluma.core.job_object import WindowsJobObject, owned_process_creation_time
    from pluma.core.task_supervisor import ResourceOwnership
    from pluma.core.cleanup import cleanup_job
    token = context.cancellation_token
    job, handle, thread, resource, assigned = None, None, None, None, False
    pid, creation = None, None
    succeeded = False
    try:
        with ExitStack() as held:
            image, cwd = _literal_path(state['argv'][0]), _literal_path(state['cwd'])
            for parent in sorted(set(image.parents) | set(cwd.parents) | {cwd}, key=str):
                held.enter_context(files._open(parent, parent=True))
            held.enter_context(files._open(image))
            with files._open(cwd, parent=True) as directory:
                if files._parent_identity(directory) != state['directory_identity'] or files.snapshot(image) != state['image_identity']:
                    raise ValueError('Application image or working directory changed.')
            token.raise_if_cancelled()
            job = WindowsJobObject()  # crash/STOP containment until verified successful promotion
            environment = None
            if state.get('environment_class') == 'system_terminal':
                environment = dict(os.environ)
                environment['PSModulePath'] = str(windows_directory() / 'System32/WindowsPowerShell/v1.0/Modules')
                environment.pop('PSExecutionPolicyPreference', None)
            handle, thread, pid, tid = create_process(str(image), state['argv'], str(cwd), environment=environment,
                new_console=state.get('environment_class') == 'system_terminal')
            creation = owned_process_creation_time(SimpleNamespace(sentinel=handle))
            if not creation: raise ValueError('Original application creation time is unavailable.')
            resource = context.register_owned_resource('subprocess', ResourceOwnership.PLUMA_CREATED, str(pid), {
                'task_id': context.task_id, 'pid': pid, 'creation_time': creation, 'command_class': state['tool'],
                'persistent_job': job, 'promote_on_success': True, 'persistent_launch_id': state['launch_id']})
            job.assign_process(SimpleNamespace(sentinel=handle))
            assigned = True
            token.raise_if_cancelled()
            c, w, kernel = files._api()
            kernel.ResumeThread.argtypes, kernel.ResumeThread.restype = [w.HANDLE], w.DWORD
            if kernel.ResumeThread(thread) == 0xFFFFFFFF: raise c.WinError()
            _winapi.CloseHandle(thread); thread = None
        deadline = time.monotonic() + 4
        while True:
            token.raise_if_cancelled()
            if _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_TIMEOUT:
                token.raise_if_cancelled()
                from pluma.core.cleanup import CleanupEvidence
                context.cleanup_evidence.append(CleanupEvidence(resource_id='app-handoff:' + state['launch_id'],
                    kind='external', code='APP_HANDOFF_OR_EXIT_UNVERIFIED',
                    identity={'pid': pid, 'creation_time': creation, 'command_class': state['tool']}))
                raise ValueError('Launcher exited or handed off outside the owned process. No existing app is claimed.')
            if state.get('environment_class') == 'system_terminal':
                # CREATE_NEW_CONSOLE is a native creation contract. The console
                # host is not the PowerShell PID; do not claim its GUI windows.
                visible = []
                break
            visible = windows(pid, creation)
            if visible: break
            if time.monotonic() >= deadline: raise TimeoutError('Owned application window did not appear.')
            time.sleep(.02)
        receipt = dict(state, pid=pid, creation_time=creation, windows=visible)
        if not verify(receipt): raise ValueError('Application postcondition was not verified.')
        succeeded = True
        return receipt
    finally:
        try:
            if not succeeded:
                with context.work_lock:
                    if handle is not None and not assigned:
                        original = _OriginalProcessOwner(handle)
                        check = cleanup_job(original, 'app-handle:' + state['launch_id'], terminate=True)
                        context.cleanup_evidence.append(check)
                        if not check.verified:
                            if resource is None:
                                resource = context.register_owned_resource('subprocess', ResourceOwnership.PLUMA_CREATED,
                                    str(pid), {'pid': pid, 'creation_time': creation, 'task_id': context.task_id,
                                    'command_class': state['tool'], 'promote_on_success': True})
                            resource.metadata['persistent_job'] = original
                            resource.metadata['persistent_job_key'] = check.resource_id
                        handle = None  # closed or retained under the original handle, never reopened by PID
                    if job is not None and not job.is_closed:
                        key = ('persistent-job:' + resource.resource_id if resource is not None
                            and resource.metadata.get('persistent_job') is job else 'app-container:' + state['launch_id'])
                        check = cleanup_job(job, key, terminate=True)
                        context.cleanup_evidence.append(check)
                        if check.verified and resource is not None and resource.metadata.get('persistent_job') is job:
                            resource.metadata['persistent_job'] = None
        finally:
            if thread is not None: _winapi.CloseHandle(thread)
            if handle is not None: _winapi.CloseHandle(handle)


def verify(state, *, restored=False):
    from pluma.core.ownership import subprocess_absent
    if state.get('action') != 'app_launch' or state.get('guard_version') != 1: return False
    if restored:
        return subprocess_absent(state['pid'], state['creation_time'])
    with _process(state['pid'], state['creation_time']) as (process, creation):
        valid = (os.path.normcase(process.exe()) == os.path.normcase(state['argv'][0])
            and (state.get('environment_class') == 'system_terminal'
                or bool(state['windows']) and windows(state['pid'], creation) == state['windows']))
        return valid


def restore(state):
    import _winapi
    from pluma.adapters.process_control import _target, _close_windows
    if verify(state, restored=True): return
    if not verify(state): raise ValueError('Application ownership or windows changed; refuse inverse.')
    with _target(state['pid'], state['creation_time']) as (handle, check):
        if not _close_windows(state['pid'], check, None): raise ValueError('No owned window accepted graceful close.')
        deadline = time.monotonic() + 4
        while _winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_OBJECT_0:
            if time.monotonic() >= deadline: raise TimeoutError('Application refused graceful undo; no force fallback.')
            time.sleep(.02)
    if not verify(state, restored=True): raise ValueError('Application inverse was not verified.')
