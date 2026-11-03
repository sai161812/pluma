"""Thread-scoped native registrations; release only IDs this owner acquired."""
import ctypes
from ctypes import wintypes


class HotkeyRegistrationError(RuntimeError):
    pass


class NativeHotkeys:
    def __init__(self):
        self.api = ctypes.WinDLL("user32", use_last_error=True)
        self.owned = []

    def acquire(self, bindings):
        from pluma.voice.activation import parse_hotkey_string
        try:
            for identifier, binding in bindings:
                modifiers, key = parse_hotkey_string(binding)
                if not self.api.RegisterHotKey(None, identifier, modifiers | 0x4000, key):
                    raise HotkeyRegistrationError("HOTKEY_UNAVAILABLE")
                self.owned.append(identifier)
        except BaseException:
            self.close()
            raise

    def close(self):
        failed = []
        for identifier in reversed(self.owned):
            if not self.api.UnregisterHotKey(None, identifier):
                failed.append(identifier)
        self.owned = list(reversed(failed))
        if failed:
            raise HotkeyRegistrationError("HOTKEY_RELEASE_UNVERIFIED")

    def prepare_queue(self):
        self.api.PeekMessageW(ctypes.byref(wintypes.MSG()), None, 0, 0, 0)

    def next(self):
        message = wintypes.MSG()
        result = self.api.GetMessageW(ctypes.byref(message), None, 0, 0)
        if result == -1:
            raise HotkeyRegistrationError("HOTKEY_MESSAGE_FAILED")
        return None if result == 0 else (message.message, message.wParam)


def probe_changed(bindings):
    """Bounded synchronous native registration on a task worker, no key injection."""
    if not bindings:
        return
    owner = NativeHotkeys()
    try:
        owner.acquire([(0x3A00 + i, binding) for i, binding in enumerate(bindings)])
    finally:
        owner.close()
