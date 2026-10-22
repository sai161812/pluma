"""Bounded on-demand native plain-text clipboard reads; no persistence."""
from contextlib import contextmanager
import hashlib
import json
import sys
import time

MAX_BYTES = 1024 * 1024
TEXT_FORMATS = {1, 7, 13, 16}


def _api():
    if sys.platform != 'win32':
        raise NotImplementedError('Native clipboard access requires Windows.')
    import ctypes as c
    from ctypes import wintypes as w
    user = c.WinDLL('user32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    declarations = {
        'OpenClipboard': ([w.HWND], w.BOOL), 'CloseClipboard': ([], w.BOOL),
        'EnumClipboardFormats': ([w.UINT], w.UINT), 'GetClipboardData': ([w.UINT], w.HANDLE),
        'GetClipboardSequenceNumber': ([], w.DWORD), 'GetClipboardOwner': ([], w.HWND),
    }
    for name, (args, result) in declarations.items():
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    kernel.GlobalSize.argtypes, kernel.GlobalSize.restype = [w.HANDLE], c.c_size_t
    kernel.GlobalLock.argtypes, kernel.GlobalLock.restype = [w.HANDLE], c.c_void_p
    kernel.GlobalUnlock.argtypes, kernel.GlobalUnlock.restype = [w.HANDLE], w.BOOL
    return c, w, user, kernel


def _check(token):
    if token is not None:
        token.raise_if_cancelled()


@contextmanager
def _opened(api, token):
    c, w, user, kernel = api
    for attempt in range(5):
        _check(token)
        if user.OpenClipboard(None):
            break
        if attempt == 4:
            raise OSError('Clipboard is busy or inaccessible.')
        time.sleep(.02)
    try:
        _check(token)
        yield
    finally:
        if not user.CloseClipboard():
            raise c.WinError(c.get_last_error())


def _formats(c, user):
    result, previous = [], 0
    for _ in range(65):
        c.set_last_error(0)
        value = user.EnumClipboardFormats(previous)
        if not value:
            error = c.get_last_error()
            if error:
                raise c.WinError(error)
            return result
        if len(result) == 64 or value in result:
            raise ValueError('Clipboard format enumeration exceeded its bound.')
        result.append(value)
        previous = value
    raise ValueError('Clipboard format enumeration did not finish.')


def _global_bytes(api, format_id):
    c, w, user, kernel = api
    handle = user.GetClipboardData(format_id)
    if not handle:
        raise OSError('Clipboard format data is unavailable.')
    size = kernel.GlobalSize(handle)
    if not 0 < size <= MAX_BYTES:
        raise ValueError('Clipboard format data exceeds its safe bound.')
    pointer = kernel.GlobalLock(handle)
    if not pointer:
        raise c.WinError(c.get_last_error())
    try:
        return c.string_at(pointer, size)
    finally:
        c.set_last_error(0)
        unlocked = kernel.GlobalUnlock(handle)
        error = c.get_last_error()
        if not unlocked and error:
            raise c.WinError(error)


def _unicode(raw):
    if len(raw) % 2:
        raise ValueError('Clipboard Unicode text is malformed.')
    terminator = next((offset for offset in range(0, min(len(raw), 131074), 2)
                       if raw[offset:offset + 2] == b'\0\0'), None)
    if terminator is None or terminator > 131072:
        raise ValueError('Clipboard Unicode text is unterminated or exceeds its bound.')
    return raw[:terminator].decode('utf-16-le', errors='strict')


def observe(token=None):
    api = _api()
    c, w, user, kernel = api
    with _opened(api, token):
        available = _formats(c, user)
        payload, formats = {}, []
        if TEXT_FORMATS.intersection(available) - {16}:
            payload['unicode_text'] = _unicode(_global_bytes(api, 13))
            formats.append('unicode_text')
        _check(token)
        # Windows can synthesize Unicode representations during reads.
        # Capture the final native sequence and owner after those conversions.
        available = _formats(c, user)
        unsupported = sorted(set(available) - TEXT_FORMATS)
        data = {'formats': formats, 'unsupported_format_ids': unsupported,
                'is_empty': not available, 'clipboard_value': payload}
        encoded = json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode('utf-8')
        if len(encoded) > 2 * MAX_BYTES:
            raise ValueError('Clipboard aggregate data exceeds its safe bound.')
        proof = {'sequence': user.GetClipboardSequenceNumber(), 'owner': user.GetClipboardOwner() or 0,
                 'digest': hashlib.sha256(encoded).hexdigest()}
        return {'data': data, 'proof': proof}
