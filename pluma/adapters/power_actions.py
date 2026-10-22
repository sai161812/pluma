"""Lazy local Windows session/power initiation and separate native readback."""
from contextlib import contextmanager
import sys
import time


def _api():
    if sys.platform != 'win32':
        raise NotImplementedError('Windows system actions require Windows.')
    import ctypes as c
    from ctypes import wintypes as w
    return c, w


def session_state():
    c, w = _api()
    kernel, wts = c.WinDLL('kernel32', use_last_error=True), c.WinDLL('wtsapi32', use_last_error=True)
    kernel.GetCurrentProcessId.restype = w.DWORD
    kernel.ProcessIdToSessionId.argtypes, kernel.ProcessIdToSessionId.restype = [w.DWORD, c.POINTER(w.DWORD)], w.BOOL
    identifier = w.DWORD()
    if not kernel.ProcessIdToSessionId(kernel.GetCurrentProcessId(), c.byref(identifier)):
        raise c.WinError(c.get_last_error())
    class LevelOne(c.Structure):
        _fields_ = [('session_id', w.ULONG), ('session_state', c.c_int), ('flags', w.LONG),
            ('station', w.WCHAR * 33), ('user', w.WCHAR * 21), ('domain', w.WCHAR * 18),
            ('logon', c.c_longlong), ('connect', c.c_longlong), ('disconnect', c.c_longlong),
            ('last_input', c.c_longlong), ('current', c.c_longlong),
            ('incoming_bytes', w.DWORD), ('outgoing_bytes', w.DWORD), ('incoming_frames', w.DWORD),
            ('outgoing_frames', w.DWORD), ('incoming_compressed', w.DWORD), ('outgoing_compressed', w.DWORD)]
    class Data(c.Union):
        _fields_ = [('one', LevelOne)]
    class Info(c.Structure):
        _fields_ = [('level', w.DWORD), ('data', Data)]
    wts.WTSQuerySessionInformationW.argtypes = [w.HANDLE, w.DWORD, c.c_int, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)]
    wts.WTSQuerySessionInformationW.restype = w.BOOL
    wts.WTSFreeMemory.argtypes, wts.WTSFreeMemory.restype = [c.c_void_p], None
    pointer, size = c.c_void_p(), w.DWORD()
    if not wts.WTSQuerySessionInformationW(None, identifier.value, 25, c.byref(pointer), c.byref(size)):
        raise c.WinError(c.get_last_error())
    try:
        if size.value < c.sizeof(Info):
            raise ValueError('Extended session state is truncated.')
        value = c.cast(pointer, c.POINTER(Info)).contents
        row = value.data.one
        if value.level != 1 or row.session_id != identifier.value or row.flags not in (0, 1):
            raise ValueError('Session identity or lock state is unknown.')
        return {'session_id': identifier.value, 'connection_state': row.session_state, 'locked': row.flags == 0}
    finally:
        wts.WTSFreeMemory(pointer)


def sleep_times():
    c, w = _api()
    power = c.WinDLL('powrprof', use_last_error=True)
    power.CallNtPowerInformation.argtypes = [c.c_int, c.c_void_p, w.ULONG, c.c_void_p, w.ULONG]
    power.CallNtPowerInformation.restype = w.LONG
    output = {}
    for key, information in (('sleep_100ns', 15), ('wake_100ns', 14)):
        value = c.c_ulonglong()
        if power.CallNtPowerInformation(information, None, 0, c.byref(value), c.sizeof(value)) != 0:
            raise OSError('Native sleep/wake counter is unavailable.')
        output[key] = value.value
    return output


@contextmanager
def _shutdown_privilege():
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY | win32con.TOKEN_ADJUST_PRIVILEGES)
    previous = None
    privilege = None
    original_enabled = None
    try:
        privilege = security.LookupPrivilegeValue(None, security.SE_SHUTDOWN_NAME)
        original = dict(security.GetTokenInformation(token, security.TokenPrivileges))
        if privilege not in original:
            raise PermissionError('Shutdown privilege is not assigned to this worker.')
        original_enabled = bool(original[privilege] & security.SE_PRIVILEGE_ENABLED)
        previous = security.AdjustTokenPrivileges(token, False, [(privilege, security.SE_PRIVILEGE_ENABLED)])
        if win32api.GetLastError() == 1300:
            raise PermissionError('Shutdown privilege is unavailable to this worker.')
        yield
    finally:
        try:
            if previous is not None:
                security.AdjustTokenPrivileges(token, False, previous)
                observed = dict(security.GetTokenInformation(token, security.TokenPrivileges))
                if (privilege not in observed or
                        bool(observed[privilege] & security.SE_PRIVILEGE_ENABLED) != original_enabled):
                    raise RuntimeError('Worker shutdown privilege restoration was not verified.')
        finally:
            token.Close()


def initiate(kind, args, operation_id, *, token=None):
    if kind not in ('lock', 'sleep_request', 'restart_request', 'shutdown_request'):
        raise ValueError('No registered system initiation.')
    c, w = _api()
    if kind == 'lock':
        user = c.WinDLL('user32', use_last_error=True)
        user.LockWorkStation.argtypes, user.LockWorkStation.restype = [], w.BOOL
        if token is not None:
            token.raise_if_cancelled()
        if not user.LockWorkStation():
            raise c.WinError(c.get_last_error())
        return
    with _shutdown_privilege():
        if kind == 'sleep_request':
            power = c.WinDLL('powrprof', use_last_error=True)
            power.SetSuspendState.argtypes, power.SetSuspendState.restype = [c.c_ubyte] * 3, c.c_ubyte
            if token is not None:
                token.raise_if_cancelled()
            if not power.SetSuspendState(False, False, False):
                raise c.WinError(c.get_last_error())
        elif kind in ('restart_request', 'shutdown_request'):
            advanced = c.WinDLL('advapi32', use_last_error=True)
            function = advanced.InitiateSystemShutdownExW
            function.argtypes = [w.LPWSTR, w.LPWSTR, w.DWORD, w.BOOL, w.BOOL, w.DWORD]
            function.restype = w.BOOL
            marker = 'PLUMA ' + kind + ' ' + operation_id
            if token is not None:
                token.raise_if_cancelled()
            if not function(None, marker, args['delay_seconds'], False, kind == 'restart_request', 0x80040000):
                raise c.WinError(c.get_last_error())
        else:
            raise ValueError('No registered system initiation.')


def event_baseline():
    import win32evtlog as log
    handle = log.OpenEventLog(None, 'System')
    try:
        count = log.GetNumberOfEventLogRecords(handle)
        oldest = log.GetOldestEventLogRecord(handle)
        return max(0, oldest + count - 1) if count else 0
    finally:
        log.CloseEventLog(handle)


def shutdown_event(kind, operation_id, baseline):
    import win32evtlog as log
    import pywintypes
    handle = log.OpenEventLog(None, 'System')
    marker = 'PLUMA ' + kind + ' ' + operation_id
    try:
        try:
            records = log.ReadEventLog(handle, log.EVENTLOG_BACKWARDS_READ | log.EVENTLOG_SEQUENTIAL_READ, 0, 65536)
        except pywintypes.error as error:
            if error.winerror == 38:
                return None
            raise
        for record in records[:64]:
            if record.RecordNumber <= baseline:
                continue
            if ((record.EventID & 0xffff) == 1074 and record.SourceName.casefold() == 'user32'
                    and any(marker == value for value in (record.StringInserts or []))):
                return {'record_id': record.RecordNumber, 'event_id': 1074, 'operation_id': operation_id, 'kind': kind}
        return None
    finally:
        log.CloseEventLog(handle)


def capture(kind):
    if kind == 'lock':
        return session_state()
    if kind == 'sleep_request':
        return sleep_times()
    if kind in ('restart_request', 'shutdown_request'):
        return {'event_baseline': event_baseline()}
    raise ValueError('No registered system precondition.')


def run(state, context):
    token = context.cancellation_token
    kind, args = state['tool'], state['arguments']
    token.raise_if_cancelled()
    if kind in ('lock', 'sleep_request') and capture(kind) != state['before']:
        raise ValueError('System state changed after capture.')
    token.raise_if_cancelled()
    if kind != 'lock' or not state['before']['locked']:
        initiate(kind, args, state['operation_id'], token=token)
    deadline = time.monotonic() + 3
    while True:
        token.raise_if_cancelled()
        if kind == 'lock':
            observed = session_state()
            if observed['session_id'] == state['before']['session_id'] and observed['locked']:
                return observed
        elif kind == 'sleep_request':
            observed = sleep_times()
            if observed['sleep_100ns'] > state['before']['sleep_100ns'] and observed['wake_100ns'] >= observed['sleep_100ns']:
                return observed
        else:
            observed = shutdown_event(kind, state['operation_id'], state['before']['event_baseline'])
            if observed is not None:
                return observed
        if time.monotonic() >= deadline:
            raise TimeoutError('Native system effect was not independently observed.')
        time.sleep(.02)


def verify(state, observation):
    kind = state['tool']
    if kind == 'lock':
        return (observation['locked'] is True and observation['session_id'] == state['before']['session_id']
                and session_state() == observation)
    if kind == 'sleep_request':
        return (observation['sleep_100ns'] > state['before']['sleep_100ns']
                and observation['wake_100ns'] >= observation['sleep_100ns'] and sleep_times() == observation)
    return (observation == shutdown_event(kind, state['operation_id'], state['before']['event_baseline'])
            and observation['record_id'] > state['before']['event_baseline'])
