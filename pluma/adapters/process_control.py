"""Explicit same-user process control; original native handles defeat PID reuse."""
from contextlib import contextmanager
import os
import time
from types import SimpleNamespace


def _api():
    import ctypes as c
    from ctypes import wintypes as w
    kernel = c.WinDLL('kernel32', use_last_error=True)
    for name, arguments, result in [
        ('IsProcessCritical', [w.HANDLE, c.POINTER(w.BOOL)], w.BOOL),
        ('ProcessIdToSessionId', [w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
        ('TerminateProcess', [w.HANDLE, w.UINT], w.BOOL),
        ('GetExitCodeProcess', [w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
    ]:
        function = getattr(kernel, name)
        function.argtypes, function.restype = arguments, result
    return c, w, kernel


@contextmanager
def _target(pid, creation_time, *, force=False, supervisor_pid=None):
    import _winapi
    import psutil
    from pluma.core.job_object import owned_process_creation_time
    if pid in (0, 4, os.getpid(), os.getppid(), supervisor_pid):
        raise ValueError('System and PLUMA supervision processes are not supported targets.')
    handle = _winapi.OpenProcess(0x1000 | 0x100000 | (1 if force else 0), False, pid)
    try:
        def check():
            if (_winapi.WaitForSingleObject(handle, 0) != _winapi.WAIT_TIMEOUT
                    or owned_process_creation_time(SimpleNamespace(sentinel=handle)) != creation_time):
                raise ProcessLookupError('Process identity is absent or changed.')
        check()
        c, w, kernel = _api()
        critical, session, own_session = w.BOOL(), w.DWORD(), w.DWORD()
        if not kernel.IsProcessCritical(handle, c.byref(critical)):
            raise c.WinError()
        if not kernel.ProcessIdToSessionId(pid, c.byref(session)) or not kernel.ProcessIdToSessionId(os.getpid(), c.byref(own_session)):
            raise c.WinError()
        if critical.value or session.value == 0 or session.value != own_session.value:
            raise PermissionError('Critical/system/other-session targets are unsupported.')
        if psutil.Process(pid).username().casefold() != psutil.Process(os.getpid()).username().casefold():
            raise PermissionError('Other-user process control is unsupported.')
        check()
        yield handle, check
    finally:
        _winapi.CloseHandle(handle)


def capture_intent(args, context=None, *, tool):
    token = getattr(context, 'cancellation_token', None)
    if token is not None:
        token.raise_if_cancelled()
    with _target(args['pid'], args['creation_time'], force=tool == 'terminate_process',
                 supervisor_pid=getattr(context, 'supervisor_pid', None)):
        return {'action': 'non_undoable_commit', 'non_undoable': True, 'tool': tool,
                'pid': args['pid'], 'creation_time': args['creation_time']}


def _close_windows(pid, check, token):
    c, w, _ = _api()
    user = c.WinDLL('user32', use_last_error=True)
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, w.LPARAM], w.BOOL
    user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    user.GetWindowThreadProcessId.restype = w.DWORD
    user.PostMessageW.argtypes, user.PostMessageW.restype = [w.HWND, w.UINT, w.WPARAM, w.LPARAM], w.BOOL
    targets, errors, count = [], [], 0
    def inspect(hwnd, unused):
        nonlocal count
        try:
            if token is not None:
                token.raise_if_cancelled()
            count += 1
            if count > 4096:
                raise ValueError('Window enumeration exceeds the bound.')
            owner = w.DWORD()
            if not user.GetWindowThreadProcessId(hwnd, c.byref(owner)):
                return True  # A disappearing unrelated window is not a target.
            if owner.value == pid:
                targets.append(hwnd)
                if len(targets) > 64:
                    raise ValueError('Target window count exceeds the bound.')
            return True
        except Exception as error:
            errors.append(error)
            return False
    enumerator = callback_type(inspect)
    if not user.EnumWindows(enumerator, 0) or errors:
        raise ValueError('Window targets could not be enumerated.')
    if not targets:
        raise ValueError('No native top-level window supports graceful close for this process.')
    sent = 0
    for hwnd in targets:
        if token is not None:
            token.raise_if_cancelled()
        try:
            check()
        except ProcessLookupError:
            break  # original-handle exit is independently read back by the caller
        owner = w.DWORD()
        if not user.GetWindowThreadProcessId(hwnd, c.byref(owner)) or owner.value != pid:
            continue  # an earlier WM_CLOSE may already have destroyed this view
        if not user.PostMessageW(hwnd, 0x10, 0, 0):  # WM_CLOSE, never WM_QUIT or force fallback
            if not user.GetWindowThreadProcessId(hwnd, c.byref(owner)) or owner.value != pid:
                continue  # never redirect a close to a replacement/foreign window
            raise c.WinError()
        sent += 1
    return sent


def execute_control(tool, args, context):
    import _winapi
    token = getattr(context, 'cancellation_token', None)
    if context is None:
        raise ValueError('A task-owned process intent is required.')
    intent = next(item['pre_state'] for item in reversed(context.undo_stack)
        if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
    expected = {'action': 'non_undoable_commit', 'non_undoable': True, 'tool': tool,
                'pid': args['pid'], 'creation_time': args['creation_time']}
    if intent != expected:
        raise ValueError('Process action does not match its journal.')
    c, w, kernel = _api()
    with _target(args['pid'], args['creation_time'], force=tool == 'terminate_process',
                 supervisor_pid=getattr(context, 'supervisor_pid', None)) as (handle, check):
        if token is not None:
            token.raise_if_cancelled()
        if tool == 'terminate_process':
            if args.get('allow_unsaved_data_loss') is not True:
                raise ValueError('Explicit data-loss acknowledgement is required.')
            check()
            if not kernel.TerminateProcess(handle, 1):
                raise c.WinError()
            sent = 0
        elif tool in ('graceful_close_process', 'close_app'):
            sent = _close_windows(args['pid'], check, token)
        else:
            raise ValueError('Unregistered process operation.')
        deadline = time.monotonic() + 4
        while True:
            if token is not None:
                token.raise_if_cancelled()
            observed = _winapi.WaitForSingleObject(handle, 0)
            if observed == _winapi.WAIT_OBJECT_0:
                break
            if observed != _winapi.WAIT_TIMEOUT:
                raise OSError('Original process exit could not be observed.')
            if time.monotonic() >= deadline:
                raise TimeoutError('Process did not exit. No force fallback was attempted.')
            time.sleep(.02)
        exit_code = w.DWORD()
        if not kernel.GetExitCodeProcess(handle, c.byref(exit_code)):
            raise c.WinError()
        return {'pid': args['pid'], 'creation_time': args['creation_time'], 'state': 'exited',
            'exit_code': exit_code.value, 'windows_signaled': sent, 'non_undoable': True}, {
            'original_handle_signaled': True, 'pid': args['pid'], 'creation_time': args['creation_time'],
            'exit_code': exit_code.value, 'tool': tool}
