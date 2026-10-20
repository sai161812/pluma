"""Windows handle-based, non-overwriting moves with bounded identity evidence."""
from contextlib import contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import stat

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TREE_ENTRIES = 512


def _api():
    import ctypes as c
    from ctypes import wintypes as w
    k = c.WinDLL('kernel32', use_last_error=True)
    declarations = {
        'CreateFileW': ([w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
        'CloseHandle': ([w.HANDLE], w.BOOL),
        'GetFileInformationByHandle': ([w.HANDLE, c.c_void_p], w.BOOL),
        'GetFileInformationByHandleEx': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
        'ReadFile': ([w.HANDLE, c.c_void_p, w.DWORD, c.POINTER(w.DWORD), c.c_void_p], w.BOOL),
        'SetFileInformationByHandle': ([w.HANDLE, c.c_int, c.c_void_p, w.DWORD], w.BOOL),
    }
    for name, (args, result) in declarations.items():
        fn = getattr(k, name)
        fn.argtypes, fn.restype = args, result
    return c, w, k


def _checked_path(value):
    target = Path(value)
    if not target.is_absolute():
        raise ValueError('An absolute path is required.')
    # Keep lexical paths; resolve() would silently follow a junction first.
    for parent in reversed(target.parents):
        info = parent.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse ancestors are unsupported.')
    return target


@contextmanager
def _open(path, *, delete=False, parent=False):
    c, w, k = _api()
    access = 0x80 if parent else 0x80000000 | (0x10000 if delete else 0)
    handle = k.CreateFileW(str(path), access, 3 if parent else 1, None, 3, 0x02200000, None)
    if handle == c.c_void_p(-1).value:
        raise c.WinError()
    try:
        if parent and _metadata(handle)['kind'] != 'directory':
            raise ValueError('A directory ancestor is required.')
        yield handle
    finally:
        if not k.CloseHandle(handle):
            raise c.WinError()


def _metadata(handle):
    c, w, k = _api()
    class Info(c.Structure):
        _fields_ = [('attrs', w.DWORD), ('created', w.FILETIME), ('accessed', w.FILETIME),
            ('modified', w.FILETIME), ('volume', w.DWORD), ('size_hi', w.DWORD), ('size_lo', w.DWORD),
            ('links', w.DWORD), ('id_hi', w.DWORD), ('id_lo', w.DWORD)]
    class Id(c.Structure):
        _fields_ = [('volume', c.c_ulonglong), ('identifier', c.c_ubyte * 16)]
    info, identity = Info(), Id()
    if not k.GetFileInformationByHandle(handle, c.byref(info)) or not k.GetFileInformationByHandleEx(handle, 18, c.byref(identity), c.sizeof(identity)):
        raise c.WinError()
    if info.attrs & 0x400:
        raise ValueError('Reparse targets are unsupported.')
    return {'volume': identity.volume, 'file_id': list(identity.identifier),
        'kind': 'directory' if info.attrs & 0x10 else 'file',
        'size_bytes': (info.size_hi << 32) | info.size_lo,
        'modified_100ns': (info.modified.dwHighDateTime << 32) | info.modified.dwLowDateTime}


def _observe(handle, path, token=None):
    c, w, k = _api()
    before = _metadata(handle)
    digest = hashlib.sha256()
    if before['kind'] == 'file':
        if before['size_bytes'] > MAX_FILE_BYTES:
            raise ValueError('File exceeds the bounded fingerprint size.')
        buffer, received, total = c.create_string_buffer(1024 * 1024), w.DWORD(), 0
        while True:
            if token is not None:
                token.raise_if_cancelled()
            if not k.ReadFile(handle, buffer, len(buffer), c.byref(received), None):
                raise c.WinError()
            if not received.value:
                break
            total += received.value
            if total > MAX_FILE_BYTES:
                raise ValueError('File grew beyond the fingerprint bound.')
            digest.update(buffer.raw[:received.value])
        if total != before['size_bytes']:
            raise ValueError('File size changed during inspection.')
    else:
        pending, records = [(Path(path), 0)], []
        while pending:
            directory, depth = pending.pop()
            if depth > 32:
                raise ValueError('Directory depth exceeds the bounded snapshot.')
            with ExitStack() as ancestors:
                current = Path(path)
                for part in directory.relative_to(path).parts:
                    current = current / part
                    ancestors.enter_context(_open(current, parent=True))
                entries = ancestors.enter_context(os.scandir(directory))
                for entry in entries:
                    if token is not None:
                        token.raise_if_cancelled()
                    if len(records) >= MAX_TREE_ENTRIES:
                        raise ValueError('Directory exceeds the bounded snapshot.')
                    child = Path(entry.path)
                    with _open(child) as child_handle:
                        identity = _metadata(child_handle)
                        if identity['kind'] == 'file':
                            identity = _observe(child_handle, child, token)
                        else:
                            pending.append((child, depth + 1))
                    records.append((str(child.relative_to(path)), identity))
        digest.update(json.dumps(sorted(records), sort_keys=True, separators=(',', ':')).encode('utf-8'))
        # Directory byte size is filesystem-dependent and not its content size.
        before['size_bytes'] = 0
    after = _metadata(handle)
    if before['kind'] == 'directory':
        after['size_bytes'] = 0
    if before != after:
        raise ValueError('Filesystem identity changed during inspection.')
    return dict(before, digest=list(digest.digest()))


def snapshot(path, token=None):
    target = _checked_path(path)
    with ExitStack() as held:
        for parent in reversed(target.parents):
            held.enter_context(_open(parent, parent=True))
        handle = held.enter_context(_open(target))
        return _observe(handle, target, token)


def capture(source, destination):
    source, destination = _checked_path(source), _checked_path(destination)
    if os.path.normcase(str(source)) == os.path.normcase(str(destination)) or os.path.lexists(destination):
        raise ValueError('A distinct absent destination is required.')
    if source in destination.parents:
        raise ValueError('A directory cannot move inside itself.')
    with ExitStack() as held:
        handles = {parent: held.enter_context(_open(parent, parent=True))
                   for parent in sorted(set(source.parents) | set(destination.parents), key=str)}
        return {'identity': snapshot(source), 'source_parent': _parent_identity(handles[source.parent]),
                'destination_parent': _parent_identity(handles[destination.parent])}


def _parent_identity(handle):
    info = _metadata(handle)
    return {'volume': info['volume'], 'file_id': info['file_id']}


def move(source, destination, expected, token=None, parents=None):
    source, destination = _checked_path(source), _checked_path(destination)
    if source in destination.parents:
        raise ValueError('A directory cannot move inside itself.')
    c, w, k = _api()
    with ExitStack() as held:
        handles = {parent: held.enter_context(_open(parent, parent=True))
                   for parent in sorted(set(source.parents) | set(destination.parents), key=str)}
        if parents is not None and (_parent_identity(handles[source.parent]) != parents[0]
                or _parent_identity(handles[destination.parent]) != parents[1]):
            raise ValueError('A parent directory was replaced after capture.')
        handle = held.enter_context(_open(source, delete=True))
        if _observe(handle, source, token) != expected:
            raise ValueError('Source differs from the captured identity.')
        if token is not None:
            token.raise_if_cancelled()
        name = str(destination).encode('utf-16-le')
        class Rename(c.Structure):
            _fields_ = [('flags', w.DWORD), ('root', w.HANDLE), ('length', w.DWORD), ('name', w.WCHAR * 1)]
        buffer = c.create_string_buffer(max(c.sizeof(Rename), Rename.name.offset + len(name) + 2))
        info = Rename.from_buffer(buffer)
        info.flags, info.root, info.length = 0, None, len(name)
        c.memmove(c.addressof(buffer) + Rename.name.offset, name, len(name))
        if not k.SetFileInformationByHandle(handle, 3, buffer, len(buffer)):
            raise c.WinError()
        # ReadFile starts at the current offset, so reopen only after releasing
        # this exclusive delete handle. Independent snapshot follows below.
    if not verify_move(source, destination, expected, token):
        raise ValueError('Move postcondition could not be verified.')


def verify_move(source, destination, expected, token=None):
    return not os.path.lexists(source) and snapshot(destination, token) == expected


def restore(state):
    source = state.get('source', state.get('original_path'))
    destination = state.get('destination', state.get('new_path'))
    if state.get('guard_version') != 1:
        raise ValueError('Captured identity is required.')
    move(destination, source, state['identity'], parents=(state['destination_parent'], state['source_parent']))


def verify_restore(state):
    source = state.get('source', state.get('original_path'))
    destination = state.get('destination', state.get('new_path'))
    return verify_move(destination, source, state['identity'])
