"""Native exact-window geometry; no foreground change, text, OCR or raw input."""
from contextlib import contextmanager
import hashlib
import time

from pluma.adapters.processes import _process


def _api():
    import ctypes as c
    from ctypes import wintypes as w
    user = c.WinDLL('user32', use_last_error=True)
    declarations = {
        'IsWindow': ([w.HWND], w.BOOL),
        'IsIconic': ([w.HWND], w.BOOL),
        'IsZoomed': ([w.HWND], w.BOOL),
        'GetWindowThreadProcessId': ([w.HWND, c.POINTER(w.DWORD)], w.DWORD),
        'GetWindowRect': ([w.HWND, c.POINTER(w.RECT)], w.BOOL),
        'GetAncestor': ([w.HWND, w.UINT], w.HWND),
        'GetClassNameW': ([w.HWND, w.LPWSTR, c.c_int], c.c_int),
        'GetDpiForWindow': ([w.HWND], w.UINT),
        'GetWindowDpiAwarenessContext': ([w.HWND], w.HANDLE),
        'GetAwarenessFromDpiAwarenessContext': ([w.HANDLE], c.c_int),
        'SetThreadDpiAwarenessContext': ([w.HANDLE], w.HANDLE),
        'SetWindowPos': ([w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT], w.BOOL),
    }
    for name, (arguments, result) in declarations.items():
        function = getattr(user, name)
        function.argtypes, function.restype = arguments, result
    return c, w, user


@contextmanager
def _window_coordinates(hwnd):
    c, w, user = _api()
    # Match the target's native coordinate space. Forcing physical awareness on
    # a legacy window introduces rounding and cannot promise exact pixel bounds.
    context = user.GetWindowDpiAwarenessContext(hwnd)
    if not context:
        raise c.WinError()
    previous = user.SetThreadDpiAwarenessContext(context)
    if not previous:
        raise c.WinError()
    try:
        yield c, w, user
    finally:
        if not user.SetThreadDpiAwarenessContext(previous):
            raise c.WinError()


def _read(user, c, w, target):
    hwnd = target['hwnd']
    owner = w.DWORD()
    thread = user.GetWindowThreadProcessId(hwnd, c.byref(owner))
    if not user.IsWindow(hwnd) or not thread or owner.value != target['pid']:
        raise ValueError('Window identity changed.')
    if user.GetAncestor(hwnd, 2) != hwnd:  # GA_ROOT: client-relative child moves are not screen geometry.
        raise ValueError('An exact top-level window is required.')
    if user.IsIconic(hwnd) or user.IsZoomed(hwnd):
        raise ValueError('A normal, non-minimized window is required.')
    rectangle, name = w.RECT(), c.create_unicode_buffer(257)
    if not user.GetWindowRect(hwnd, c.byref(rectangle)) or not user.GetClassNameW(hwnd, name, len(name)):
        raise c.WinError()
    dpi = user.GetDpiForWindow(hwnd)
    awareness = user.GetAwarenessFromDpiAwarenessContext(user.GetWindowDpiAwarenessContext(hwnd))
    if not dpi or awareness not in (0, 1, 2):
        raise c.WinError()
    return {'geometry': {'x': rectangle.left, 'y': rectangle.top,
            'width': rectangle.right - rectangle.left, 'height': rectangle.bottom - rectangle.top},
        'identity': {'thread_id': thread, 'class_digest': list(hashlib.sha256(name.value.encode('utf-16-le')).digest()),
                     'dpi': dpi, 'dpi_awareness': awareness}}


def observe(target):
    with _process(target['pid'], target['creation_time']):
        with _window_coordinates(target['hwnd']) as (c, w, user):
            first = _read(user, c, w, target)
            if _read(user, c, w, target) != first:
                raise ValueError('Window changed during observation.')
            return first


def capture(args, tool):
    target = {key: args[key] for key in ('hwnd', 'pid', 'creation_time')}
    observed = observe(target)
    after = dict(observed['geometry'])
    keys = ('x', 'y') if tool == 'move_window' else ('width', 'height')
    after.update({key: args[key] for key in keys})
    return {'action': 'window_geometry', 'guard_version': 1, 'tool': tool,
        **target, 'coordinate_space': 'window_dpi', 'identity': observed['identity'],
        'before': observed['geometry'], 'after': after}


def apply(state, token=None):
    with _process(state['pid'], state['creation_time']):
        with _window_coordinates(state['hwnd']) as (c, w, user):
            before = _read(user, c, w, state)
            if before != {'identity': state['identity'], 'geometry': state['before']}:
                raise ValueError('Window changed after capture; preserve newer state.')
            if token is not None:
                token.raise_if_cancelled()
            desired = state['after']
            flags = 4 | 0x10 | 0x4000  # NOZORDER | NOACTIVATE | ASYNCWINDOWPOS
            flags |= 1 if state['tool'] == 'move_window' else 2  # NOSIZE or NOMOVE
            if not user.SetWindowPos(state['hwnd'], None, desired['x'], desired['y'],
                    desired['width'], desired['height'], flags):
                raise c.WinError()
            deadline = time.monotonic() + 1.5
            while True:
                if token is not None:
                    token.raise_if_cancelled()
                current = _read(user, c, w, state)
                if current['identity'] != state['identity']:
                    raise ValueError('Window identity/DPI changed during geometry update.')
                if current['geometry'] == desired:
                    return
                if time.monotonic() >= deadline:
                    raise TimeoutError('Window did not reach the requested geometry.')
                time.sleep(.02)


def verify(state, *, restored=False):
    return observe(state) == {'identity': state['identity'], 'geometry': state['before' if restored else 'after']}


def restore(state):
    if state.get('guard_version') != 1:
        raise ValueError('Window undo lacks identity evidence.')
    apply(dict(state, before=state['after'], after=state['before']))
    if not verify(state, restored=True):
        raise ValueError('Window inverse readback failed.')
