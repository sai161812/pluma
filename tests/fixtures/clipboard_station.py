"""Native clipboard isolation in a new noninteractive window station; tests only."""
from contextlib import contextmanager
import ctypes as c
from ctypes import wintypes as w


def _api():
    user, kernel = c.WinDLL('user32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    declarations = {
        'GetProcessWindowStation': ([], w.HANDLE), 'SetProcessWindowStation': ([w.HANDLE], w.BOOL),
        'CreateWindowStationW': ([w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p], w.HANDLE),
        'OpenWindowStationW': ([w.LPCWSTR, w.BOOL, w.DWORD], w.HANDLE),
        'CloseWindowStation': ([w.HANDLE], w.BOOL), 'GetThreadDesktop': ([w.DWORD], w.HANDLE),
        'SetThreadDesktop': ([w.HANDLE], w.BOOL),
        'CreateDesktopW': ([w.LPCWSTR, w.LPCWSTR, c.c_void_p, w.DWORD, w.DWORD, c.c_void_p], w.HANDLE),
        'OpenDesktopW': ([w.LPCWSTR, w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        'CloseDesktop': ([w.HANDLE], w.BOOL), 'GetClipboardSequenceNumber': ([], w.DWORD),
        'CreateWindowExW': ([w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int,
                            c.c_int, c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p], w.HWND),
        'DestroyWindow': ([w.HWND], w.BOOL),
        'GetUserObjectInformationW': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)], w.BOOL),
    }
    for name, (args, result) in declarations.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    kernel.GetCurrentThreadId.restype = w.DWORD
    kernel.LocalFree.argtypes, kernel.LocalFree.restype = [w.HANDLE], w.HANDLE
    return user, kernel


def _require(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


@contextmanager
def private_security(kernel):
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()
    advanced = c.WinDLL('advapi32', use_last_error=True)
    function = advanced.ConvertStringSecurityDescriptorToSecurityDescriptorW
    function.argtypes, function.restype = [w.LPCWSTR, w.DWORD, c.POINTER(c.c_void_p), c.POINTER(w.DWORD)], w.BOOL
    descriptor = c.c_void_p()
    _require(function('D:P(A;;GA;;;SY)(A;;GA;;;' + sid + ')', 1, c.byref(descriptor), None))
    class Attributes(c.Structure):
        _fields_ = [('length', w.DWORD), ('descriptor', c.c_void_p), ('inherit', w.BOOL)]
    attributes = Attributes(c.sizeof(Attributes), descriptor, False)
    try:
        yield c.byref(attributes)
    finally:
        assert not kernel.LocalFree(descriptor), 'Fixture security descriptor cleanup failed.'


@contextmanager
def station(name=None):
    """Never SwitchDesktop, never access content on the interactive clipboard."""
    user, kernel = _api()
    original_station = _require(user.GetProcessWindowStation())
    original_desktop = _require(user.GetThreadDesktop(kernel.GetCurrentThreadId()))
    original_sequence = user.GetClipboardSequenceNumber()
    create = name is None
    if name is not None and (not name or len(name) > 256 or '\\' in name or name.casefold() == 'winsta0'):
        raise ValueError('An explicitly owned noninteractive fixture station is required.')
    # Naming a new station requires administrator membership. NULL asks Windows
    # for a logon-derived name; CREATE_ONLY refuses any pre-existing object.
    with private_security(kernel) as security:
        owned_station = _require(user.CreateWindowStationW(None, 1, 0x37f, security) if create
                                 else user.OpenWindowStationW(name, False, 0x37f))
    desktop, owner = None, None
    try:
        _require(user.SetProcessWindowStation(owned_station))
        if create:
            buffer, needed = c.create_unicode_buffer(257), w.DWORD()
            _require(user.GetUserObjectInformationW(owned_station, 2, buffer, c.sizeof(buffer), c.byref(needed)))
            name = buffer.value
            assert name and name.casefold() != 'winsta0' and needed.value <= c.sizeof(buffer)
        desktop = _require(user.CreateDesktopW('Fixture', None, None, 0, 0x1ff, None) if create
                           else user.OpenDesktopW('Fixture', 0, False, 0x1ff))
        _require(user.SetThreadDesktop(desktop))
        owner = _require(user.CreateWindowExW(0, 'STATIC', 'PLUMA clipboard fixture', 0,
                            0, 0, 0, 0, w.HWND(-3), None, None, None))
        yield name, owner
    finally:
        errors = []
        def cleanup(function, *args):
            try:
                if not function(*args):
                    errors.append(function.__name__)
            except Exception:
                errors.append(function.__name__)
        if owner:
            cleanup(user.DestroyWindow, owner)
        cleanup(user.SetProcessWindowStation, original_station)
        cleanup(user.SetThreadDesktop, original_desktop)
        if desktop:
            cleanup(user.CloseDesktop, desktop)
        cleanup(user.CloseWindowStation, owned_station)
        assert not errors, errors
        assert user.GetProcessWindowStation() == original_station
        assert user.GetThreadDesktop(kernel.GetCurrentThreadId()) == original_desktop
        assert user.GetClipboardSequenceNumber() == original_sequence, 'Original clipboard sequence changed during isolated fixture.'


def seed(owner, values):
    import win32clipboard as clipboard
    clipboard.OpenClipboard(owner)
    try:
        clipboard.EmptyClipboard()
        for format_id, value in values:
            clipboard.SetClipboardData(format_id, value)
    finally:
        clipboard.CloseClipboard()
