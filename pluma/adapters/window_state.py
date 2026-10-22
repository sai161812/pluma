"""On-demand native window placement, guarded by exact process/window identity."""
import hashlib
import time

from pluma.adapters.processes import _process
from pluma.adapters.window_geometry import _window_coordinates

TOOLS = {'minimize_window': 2, 'maximize_window': 3, 'restore_window': 1}


def _read(target, c, w, user):
    import win32gui
    hwnd = target['hwnd']
    owner, rectangle, name = w.DWORD(), w.RECT(), c.create_unicode_buffer(257)
    thread = user.GetWindowThreadProcessId(hwnd, c.byref(owner))
    if (not user.IsWindow(hwnd) or not thread or owner.value != target['pid']
            or user.GetAncestor(hwnd, 2) != hwnd):
        raise ValueError('Window identity changed or is not top-level.')
    if not user.GetWindowRect(hwnd, c.byref(rectangle)) or not user.GetClassNameW(hwnd, name, len(name)):
        raise c.WinError()
    dpi = user.GetDpiForWindow(hwnd)
    awareness = user.GetAwarenessFromDpiAwarenessContext(user.GetWindowDpiAwarenessContext(hwnd))
    if not dpi or awareness not in (0, 1, 2):
        raise ValueError('Window coordinate identity is unavailable.')
    flags, show, minimum, maximum, normal = win32gui.GetWindowPlacement(hwnd)
    if show not in (1, 2, 3) or flags & ~3 or not win32gui.IsWindowVisible(hwnd):
        raise ValueError('A visible normal, minimized or maximized window is required.')
    # Inactive automatic minimized coordinates are OS bookkeeping, not user
    # placement. They change after the first minimize even after a normal restore.
    if show != 2 and not flags & 1:
        minimum = (-1, -1)
    return {'identity': {'thread_id': thread, 'class_digest': list(hashlib.sha256(name.value.encode('utf-16-le')).digest()),
            'dpi': dpi, 'dpi_awareness': awareness},
        'placement': {'flags': flags, 'show': show, 'minimum': list(minimum), 'maximum': list(maximum), 'normal': list(normal)},
        'rectangle': [rectangle.left, rectangle.top, rectangle.right, rectangle.bottom]}


def observe(target):
    with _process(target['pid'], target['creation_time']):
        with _window_coordinates(target['hwnd']) as (c, w, user):
            first = _read(target, c, w, user)
            if _read(target, c, w, user) != first:
                raise ValueError('Window placement changed during observation.')
            return first


def capture(args, tool):
    if tool not in TOOLS:
        raise ValueError('Unsupported window operation.')
    active = args.get('hwnd') is None
    if active:
        import win32gui
        from pluma.adapters.app_windows import observe_window
        hwnd = win32gui.GetForegroundWindow()
        snapshot = observe_window(hwnd)
        target = {key: snapshot[key] for key in ('hwnd', 'pid', 'creation_time')}
    else:
        target = {key: args[key] for key in ('hwnd', 'pid', 'creation_time')}
    return dict(action='window_state', guard_version=1, tool=tool, active_target=active,
                **target, before=observe(target))


def _set(target, expected, placement, desired_show, token=None, *, exact=None, active=False):
    import win32gui
    with _process(target['pid'], target['creation_time']):
        with _window_coordinates(target['hwnd']) as (c, w, user):
            if _read(target, c, w, user) != expected:
                raise ValueError('Window changed; preserve newer placement.')
            if token is not None:
                token.raise_if_cancelled()
            if active and win32gui.GetForegroundWindow() != target['hwnd']:
                raise ValueError('Active window changed after capture.')
            win32gui.SetWindowPlacement(target['hwnd'], (placement['flags'] | 4, desired_show,
                tuple(placement['minimum']), tuple(placement['maximum']), tuple(placement['normal'])))
            deadline = time.monotonic() + 1.5
            stable, stable_since = None, None
            while True:
                if token is not None:
                    token.raise_if_cancelled()
                current = _read(target, c, w, user)
                if current['identity'] != expected['identity']:
                    raise ValueError('Window identity or DPI changed.')
                reached = current == exact if exact is not None else (
                    current['placement']['show'] == {7: 2, 4: 1}.get(desired_show, desired_show)
                    and current['placement']['normal'] == placement['normal'])
                if not reached or current != stable:
                    stable, stable_since = current, time.monotonic() if reached else None
                if reached and stable_since is not None and time.monotonic() - stable_since >= .15:
                    return current
                if time.monotonic() >= deadline:
                    raise TimeoutError('Window state did not read back.')
                time.sleep(.02)


def apply(state, token=None):
    import win32gui
    if state.get('active_target') and win32gui.GetForegroundWindow() != state['hwnd']:
        raise ValueError('Active window changed after capture.')
    before = state['before']
    placement = dict(before['placement'])
    show = TOOLS[state['tool']]
    if show != 2:
        placement['flags'] &= ~2
    elif before['placement']['show'] == 3:
        placement['flags'] |= 2
    after = _set(state, before, placement, {1: 4, 2: 7, 3: 3}[show], token, active=state['active_target'])
    return dict(state, after=after)


def verify(state, *, restored=False):
    return state.get('guard_version') == 1 and observe(state) == state['before' if restored else 'after']


def restore(state):
    if state.get('guard_version') != 1 or state.get('action') != 'window_state':
        raise ValueError('Window inverse lacks captured placement.')
    placement = state['before']['placement']
    _set(state, state['after'], placement, {1: 4, 2: 7, 3: 3}[placement['show']], exact=state['before'])
    if not verify(state, restored=True):
        raise ValueError('Window inverse readback failed.')
