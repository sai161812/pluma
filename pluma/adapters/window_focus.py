"""Exact native foreground changes; Windows foreground restrictions are respected."""
import time
from pluma.adapters import window_state as placement
from pluma.adapters.processes import _process


def foreground():
    import win32gui
    return win32gui.GetForegroundWindow()


def target(args, tool):
    if tool == 'focus_app' and args.get('app_name'):
        from pluma.adapters.app_targets import by_name
        return by_name(args['app_name'], window=True)
    return {key: args[key] for key in ('hwnd', 'pid', 'creation_time')}


def capture(args, tool):
    from pluma.adapters.app_windows import observe_window
    selected = target(args, tool)
    before = placement.observe(selected)
    previous = observe_window(foreground())
    previous = {key: previous[key] for key in ('hwnd', 'pid', 'creation_time')}
    previous['state'] = placement.observe(previous)
    return dict(action='window_focus', guard_version=1, tool=tool, **selected,
                before=before, previous=previous)


def _focus(selected, expected, token=None):
    import win32gui
    with _process(selected['pid'], selected['creation_time']):
        if placement.observe(selected) != expected:
            raise ValueError('Focus target identity or placement changed.')
        if token is not None: token.raise_if_cancelled()
        win32gui.SetForegroundWindow(selected['hwnd'])
        deadline = time.monotonic() + 1
        while True:
            if token is not None: token.raise_if_cancelled()
            if foreground() == selected['hwnd'] and placement.observe(selected) == expected:
                return
            if time.monotonic() >= deadline:
                raise TimeoutError('Windows did not grant the requested foreground transition.')
            time.sleep(.02)


def apply(state, token=None):
    previous = state['previous']
    if (foreground() != previous['hwnd'] or placement.observe(previous) != previous['state']
            or placement.observe(state) != state['before']):
        raise ValueError('Foreground or target changed after capture.')
    after = state['before']
    if after['placement']['show'] == 2:
        restored = placement.apply(dict(action='window_state', guard_version=1, tool='restore_window',
            active_target=False, **{key: state[key] for key in ('hwnd', 'pid', 'creation_time')}, before=after), token)
        after = restored['after']
    _focus(state, after, token)
    receipt = dict(state, after=after)
    if not verify(receipt): raise ValueError('Focus readback failed.')
    return receipt


def verify(state, *, restored=False):
    if state.get('action') != 'window_focus' or state.get('guard_version') != 1:
        return False
    if restored:
        previous = state['previous']
        return (foreground() == previous['hwnd'] and placement.observe(previous) == previous['state']
                and placement.observe(state) == state['before'])
    return foreground() == state['hwnd'] and placement.observe(state) == state['after']


def restore(state):
    previous = state['previous']
    if not verify(state) or placement.observe(previous) != previous['state']:
        raise ValueError('Newer foreground/placement conflicts with focus undo.')
    if state['before'] != state['after']:
        placement.restore(dict(state, action='window_state'))
    _focus(previous, previous['state'])
    if not verify(state, restored=True): raise ValueError('Focus inverse was not verified.')
