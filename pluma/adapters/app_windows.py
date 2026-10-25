"""On-demand native top-level window/application reads; never launch or focus."""
import hashlib
import sys
import time

from pluma.adapters.processes import _process, _check_cancel
from pluma.adapters.window_geometry import _api as _window_api, _window_coordinates


def _api():
    if sys.platform != 'win32':
        raise NotImplementedError('Native application inspection requires Windows.')
    c, w, user = _window_api()
    for name, args, result in (
        ('IsWindowVisible', [w.HWND], w.BOOL),
        ('GetWindowTextLengthW', [w.HWND], c.c_int),
        ('GetWindowTextW', [w.HWND, w.LPWSTR, c.c_int], c.c_int),
    ):
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    return c, w, user


def _title(c, user, hwnd):
    c.set_last_error(0)
    length = user.GetWindowTextLengthW(hwnd)
    if length < 0 or not length and c.get_last_error():
        raise c.WinError(c.get_last_error())
    buffer = c.create_unicode_buffer(min(length, 2048) + 1)
    c.set_last_error(0)
    copied = user.GetWindowTextW(hwnd, buffer, len(buffer))
    if not copied and c.get_last_error():
        raise c.WinError(c.get_last_error())
    return buffer.value, length > 2048


def observe_window(hwnd, expected_creation=None):
    c, w, user = _api()
    pid = w.DWORD()
    thread = user.GetWindowThreadProcessId(hwnd, c.byref(pid))
    if not thread or not user.IsWindow(hwnd) or user.GetAncestor(hwnd, 2) != hwnd:
        raise ProcessLookupError('Window disappeared or changed.')
    with _process(pid.value, expected_creation) as (process, creation):
        name = process.name()
        with _window_coordinates(hwnd):
            def read():
                owner = w.DWORD()
                current_thread = user.GetWindowThreadProcessId(hwnd, c.byref(owner))
                rectangle, class_name = w.RECT(), c.create_unicode_buffer(257)
                if (not user.IsWindow(hwnd) or current_thread != thread or owner.value != pid.value
                        or not user.GetWindowRect(hwnd, c.byref(rectangle))
                        or not user.GetClassNameW(hwnd, class_name, len(class_name))):
                    raise ProcessLookupError('Window identity changed.')
                title, truncated = _title(c, user, hwnd)
                return dict(available=True, hwnd=hwnd, pid=pid.value, creation_time=creation, name=name,
                    title=title, title_truncated=truncated, thread_id=thread,
                    class_digest=hashlib.sha256(class_name.value.encode('utf-16-le')).hexdigest(),
                    visible=bool(user.IsWindowVisible(hwnd)), minimized=bool(user.IsIconic(hwnd)),
                    maximized=bool(user.IsZoomed(hwnd)),
                    rectangle=[rectangle.left, rectangle.top, rectangle.right, rectangle.bottom])
            observed = read()
            if read() != observed:
                raise ValueError('Window changed during inspection.')
            return observed


def enumerate_windows(args, context=None, *, apps=False):
    _check_cancel(context)
    c, w, user = _api()
    rows, errors = [], []
    scanned, limited = 0, False
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, w.LPARAM], w.BOOL

    def callback(hwnd, ignored):
        nonlocal scanned, limited
        try:
            _check_cancel(context)
            if scanned == args['max_scan_entries'] or len(rows) == args['max_entries']:
                limited = True
                return False
            scanned += 1
            if args['visible_only'] and not user.IsWindowVisible(hwnd):
                return True
            if not apps and args['filter'] is not None:
                title, truncated = _title(c, user, hwnd)
                if truncated and args['filter'].casefold() not in title.casefold():
                    raise ValueError('Window caption exceeds the bounded filter observation.')
                if args['filter'].casefold() not in title.casefold():
                    return True
            try:
                observed = observe_window(hwnd)
            except (OSError, ProcessLookupError, PermissionError, ValueError) as error:
                pid = w.DWORD()
                user.GetWindowThreadProcessId(hwnd, c.byref(pid))
                reason = 'access_denied' if isinstance(error, PermissionError) else 'gone_or_changed' if isinstance(error, ProcessLookupError) else 'unavailable'
                observed = dict(available=False, hwnd=hwnd, pid=pid.value, reason=reason)
            if observed['available']:
                if args['visible_only'] and not observed['visible']:
                    return True
                value = observed['name'] if apps else observed['title']
                if args['filter'] is not None and args['filter'].casefold() not in value.casefold():
                    return True
            rows.append(observed)
            return True
        except BaseException as error:
            errors.append(error)
            return False

    result = user.EnumWindows(callback_type(callback), 0)
    if errors:
        raise errors[0]
    if not result and not limited:
        raise OSError('Native window enumeration failed.')
    _check_cancel(context)
    rows.sort(key=lambda row: row['hwnd'])
    return dict(observed_at_ns=time.time_ns(), windows=rows, count=len(rows), scanned_windows=scanned,
                limited=limited, **args)


def verify_windows(data):
    # This validates each observed snapshot, not an assertion that no new user
    # window can appear after enumeration. Empty lists remain scoped observations.
    for row in data['windows']:
        if row['available']:
            if observe_window(row['hwnd'], row['creation_time']) != row:
                return False
        else:
            try:
                observe_window(row['hwnd'])
            except (OSError, ProcessLookupError, PermissionError, ValueError):
                continue
            return False
    return True


def status(args):
    from pluma.core.ownership import subprocess_absent
    try:
        with _process(args['pid'], args['creation_time']) as (process, identity):
            data = dict(args, state='running', running=True, name=process.name())
        return data
    except ProcessLookupError:
        if subprocess_absent(args['pid'], args['creation_time']):
            return dict(args, state='gone_or_changed', running=False, name=None)
        raise
