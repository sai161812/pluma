"""Bounded native folder observations, copying and directory creation."""
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat

from pluma.adapters import file_identity as identity


def _parents(source, destination, held):
    return {parent: held.enter_context(identity._open(parent, parent=True))
            for parent in sorted(set(Path(source).parents) | set(Path(destination).parents), key=str)}


def _binding(handles, source, destination, state):
    if (identity._parent_identity(handles[Path(source).parent]) != state['source_parent']
            or identity._parent_identity(handles[Path(destination).parent]) != state['destination_parent']):
        raise ValueError('A captured parent was replaced.')


def _basic(handle):
    c, w, k = identity._api()
    class Basic(c.Structure):
        _fields_ = [('created', c.c_longlong), ('accessed', c.c_longlong),
                    ('written', c.c_longlong), ('changed', c.c_longlong), ('attributes', w.DWORD)]
    value = Basic()
    if not k.GetFileInformationByHandleEx(handle, 0, c.byref(value), c.sizeof(value)):
        raise c.WinError()
    return {'changed_100ns': value.changed, 'attributes': value.attributes}


def _streams(handle):
    c, w, k = identity._api()
    # Native FILE_STREAM_INFO. Refuse an unbounded stream table rather than
    # silently hashing only the default stream. Names remain local to this call.
    buffer = c.create_string_buffer(65536)
    if not k.GetFileInformationByHandleEx(handle, 7, buffer, len(buffer)):
        raise c.WinError()
    result, offset = [], 0
    while True:
        if offset + 24 > len(buffer) or len(result) >= 32:
            raise ValueError('File stream table exceeds the bounded observation.')
        next_offset = c.c_uint32.from_buffer(buffer, offset).value
        name_bytes = c.c_uint32.from_buffer(buffer, offset + 4).value
        size = c.c_longlong.from_buffer(buffer, offset + 8).value
        if name_bytes % 2 or name_bytes > len(buffer) - offset - 24 or size < 0:
            raise ValueError('Invalid native stream metadata.')
        name = buffer.raw[offset + 24:offset + 24 + name_bytes].decode('utf-16-le')
        if not name.startswith(':') or not name.endswith(':$DATA') or any(char in name for char in '/\\\0'):
            raise ValueError('Unsupported file stream.')
        result.append((name, size))
        if not next_offset:
            return sorted(result)
        if next_offset < 24 + name_bytes:
            raise ValueError('Invalid native stream offset.')
        offset += next_offset


def _copy_observe(handle, path, token=None):
    before, streams = _basic(handle), _streams(handle)
    if sum(size for _, size in streams) > identity.MAX_FILE_BYTES:
        raise ValueError('File streams exceed the bounded fingerprint size.')
    ordinary, fingerprints = identity._observe(handle, path, token), []
    for name, size in streams:
        if name == '::$DATA':
            digest = ordinary['digest']
        else:
            with identity._open(str(path) + name) as stream_handle:
                observed = identity._observe(stream_handle, Path(str(path) + name), token)
                if observed['size_bytes'] != size:
                    raise ValueError('File stream size changed.')
                digest = observed['digest']
        fingerprints.append((name, size, digest))
    if _basic(handle) != before or _streams(handle) != streams:
        raise ValueError('File streams or metadata changed during observation.')
    encoded = json.dumps(fingerprints, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    return dict(ordinary, **before, streams_digest=list(hashlib.sha256(encoded).digest()))


def _copy_snapshot(path, token=None):
    target = identity._checked_path(path)
    with ExitStack() as held:
        for parent in reversed(target.parents):
            held.enter_context(identity._open(parent, parent=True))
        handle = held.enter_context(identity._open(target))
        return _copy_observe(handle, target, token)


def capture_copy(source, destination):
    info = Path(source).lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('A regular non-reparse source file is required.')
    state = identity.capture(source, destination)
    observed = _copy_snapshot(source)
    if any(observed[key] != value for key, value in state['identity'].items()):
        raise ValueError('Source changed during capture.')
    state['identity'] = observed
    return {'action': 'copy_file', 'source': str(Path(source)), 'destination': str(Path(destination)),
            'guard_version': 1, **state}


def copy_file(state, token=None):
    source, destination = state['source'], state['destination']
    c, w, k = identity._api()
    progress_type = c.WINFUNCTYPE(w.DWORD, c.c_longlong, c.c_longlong, c.c_longlong, c.c_longlong,
                                 w.DWORD, w.DWORD, w.HANDLE, w.HANDLE, c.c_void_p)
    k.CopyFileExW.argtypes = [w.LPCWSTR, w.LPCWSTR, progress_type, c.c_void_p, c.POINTER(w.BOOL), w.DWORD]
    k.CopyFileExW.restype = w.BOOL
    created = []
    def progress(total, transferred, stream_size, stream_done, number, reason, source_handle, target_handle, data):
        try:
            if token is not None and token.is_cancelled:
                return 1  # PROGRESS_CANCEL: native copy removes its partial target.
            if not created:
                created.append(identity._parent_identity(target_handle))
            return 0
        except Exception:
            return 1
    callback, cancel = progress_type(progress), w.BOOL(False)
    with ExitStack() as held:
        handles = _parents(source, destination, held)
        _binding(handles, source, destination, state)
        held.enter_context(identity._open(source))  # deny source writes/deletion during native copy
        if _copy_snapshot(source, token) != state['identity']:
            raise ValueError('Source changed after capture.')
        if token is not None:
            token.raise_if_cancelled()
        if not k.CopyFileExW(source, destination, callback, None, c.byref(cancel), 0x801):  # FAIL_IF_EXISTS | COPY_SYMLINK
            raise c.WinError()
        target = _copy_snapshot(destination, token)
        if (not created or {'volume': target['volume'], 'file_id': target['file_id']} != created[0]
                or target['digest'] != state['identity']['digest']
                or target['size_bytes'] != state['identity']['size_bytes']
                or target['streams_digest'] != state['identity']['streams_digest']
                or _copy_snapshot(source, token) != state['identity']):
            raise ValueError('Copied file identity/content was not verified.')
    return dict(state, created_identity=target)


def verify_copy(state):
    return (_copy_snapshot(state['source']) == state['identity']
            and _copy_snapshot(state['destination']) == state['created_identity']
            and state['created_identity']['digest'] == state['identity']['digest']
            and state['created_identity']['size_bytes'] == state['identity']['size_bytes'])


def _delete_exact(path, expected, *, directory=False, parent_identity=None):
    c, w, k = identity._api()
    with ExitStack() as held:
        target = identity._checked_path(path)
        for parent in reversed(target.parents):
            parent_handle = held.enter_context(identity._open(parent, parent=True))
        if parent_identity is not None and identity._parent_identity(parent_handle) != parent_identity:
            raise ValueError('Created target parent was replaced.')
        handle = held.enter_context(identity._open(target, delete=True))
        actual = identity._metadata(handle)
        if {'volume': actual['volume'], 'file_id': actual['file_id']} != {
                'volume': expected['volume'], 'file_id': expected['file_id']}:
            raise ValueError('Created target was replaced.')
        if not directory and _copy_observe(handle, target) != expected:
            raise ValueError('Created file was edited.')
        if directory and actual['kind'] != 'directory':
            raise ValueError('A captured directory is required.')
        # Native disposition refuses a nonempty directory. It does not recurse.
        class Disposition(c.Structure):
            _fields_ = [('delete', c.c_ubyte)]
        disposition = Disposition(True)
        if not k.SetFileInformationByHandle(handle, 4, c.byref(disposition), c.sizeof(disposition)):
            raise c.WinError()
    if os.path.lexists(path):
        raise ValueError('Target absence was not verified.')


def restore_copy(state):
    _delete_exact(state['destination'], state['created_identity'], parent_identity=state['destination_parent'])


def _entry(entry):
    # DirEntry.stat on Windows deliberately reports zero device/file IDs.
    # Use the same uncached lstat for enumeration and independent readback.
    info = Path(entry.path).lstat()
    kind = ('reparse' if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400
            else 'directory' if stat.S_ISDIR(info.st_mode) else 'file' if stat.S_ISREG(info.st_mode) else 'unsupported')
    return {'name': entry.name, 'kind': kind, 'file_id': info.st_ino, 'device': info.st_dev,
            'size_bytes': info.st_size if kind == 'file' else None, 'modified_ns': info.st_mtime_ns}


def list_folder(path, limit, token=None):
    target = identity._checked_path(path)
    with ExitStack() as held:
        for parent in (*reversed(target.parents), target):
            handle = held.enter_context(identity._open(parent, parent=True))
        before = identity._metadata(handle)
        rows, has_more = [], False
        with os.scandir(target) as entries:
            for entry in entries:
                if token is not None:
                    token.raise_if_cancelled()
                if len(rows) == limit:
                    has_more = True
                    break
                rows.append(_entry(entry))
        if identity._metadata(handle) != before:
            raise ValueError('Directory changed during enumeration.')
    rows.sort(key=lambda row: row['name'])
    return {'path': str(target), 'entries': rows, 'count': len(rows), 'max_entries': limit, 'has_more': has_more}, before


def verify_folder(data, captured):
    observed, metadata = list_folder(data['path'], data['max_entries'])
    return metadata == captured and observed == data


def capture_folder(path, exist_ok):
    target, missing = Path(path), []
    current = target
    while not os.path.lexists(current):
        missing.append(str(current))
        if len(missing) > 32:
            raise ValueError('Directory creation exceeds the bounded depth.')
        current = current.parent
    anchor = identity._checked_path(current)
    with ExitStack() as held:
        for parent in (*reversed(anchor.parents), anchor):
            handle = held.enter_context(identity._open(parent, parent=True))
        bound = identity._parent_identity(handle)
    return {'action': 'create_folder', 'path': str(target), 'guard_version': 1,
            'existed_before': not missing, 'exist_ok': exist_ok,
            'anchor_path': str(anchor), 'anchor_identity': bound, 'missing_paths': list(reversed(missing))}


@contextmanager
def _new_directory(path):
    """Create exclusively and retain the handle returned by that same call."""
    c, w, kernel = identity._api()
    native = c.WinDLL('ntdll')
    class Unicode(c.Structure):
        _fields_ = [('length', w.USHORT), ('maximum', w.USHORT), ('buffer', w.LPWSTR)]
    class Attributes(c.Structure):
        _fields_ = [('length', w.ULONG), ('root', w.HANDLE), ('name', c.POINTER(Unicode)),
                    ('flags', w.ULONG), ('security', c.c_void_p), ('qos', c.c_void_p)]
    class Status(c.Structure):
        _fields_ = [('status', c.c_void_p), ('information', c.c_size_t)]
    native.NtCreateFile.argtypes = [c.POINTER(w.HANDLE), w.DWORD, c.POINTER(Attributes),
        c.POINTER(Status), c.c_void_p, w.ULONG, w.ULONG, w.ULONG, w.ULONG, c.c_void_p, w.ULONG]
    native.NtCreateFile.restype = c.c_long
    native.RtlNtStatusToDosError.argtypes = [c.c_long]
    native.RtlNtStatusToDosError.restype = w.ULONG
    text = str(path)
    text = '\\??\\UNC\\' + text[2:] if text.startswith('\\\\') else '\\??\\' + text
    encoded = text.encode('utf-16-le')
    if len(encoded) > 65532:
        raise ValueError('Native directory path exceeds the bounded length.')
    buffer = c.create_unicode_buffer(text)
    name = Unicode(len(encoded), len(encoded) + 2, c.cast(buffer, w.LPWSTR))
    attributes = Attributes(c.sizeof(Attributes), None, c.pointer(name), 0x40, None, None)
    handle, status = w.HANDLE(), Status()
    result = native.NtCreateFile(c.byref(handle), 0x100080, c.byref(attributes), c.byref(status),
        None, 0x10, 3, 2, 0x200021, None, 0)  # FILE_CREATE, directory, synchronous, no reparse
    if result < 0:
        raise c.WinError(native.RtlNtStatusToDosError(result))
    try:
        yield handle.value
    finally:
        if not kernel.CloseHandle(handle):
            raise c.WinError()


def create_folder(state, token=None):
    anchor = identity._checked_path(state['anchor_path'])
    created = []
    with ExitStack() as held:
        for parent in (*reversed(anchor.parents), anchor):
            handle = held.enter_context(identity._open(parent, parent=True))
        if identity._parent_identity(handle) != state['anchor_identity']:
            raise ValueError('Creation anchor was replaced.')
        if state['existed_before'] and not state['exist_ok']:
            raise FileExistsError('Target already exists.')
        for path in state['missing_paths']:
            if token is not None:
                token.raise_if_cancelled()
            handle = held.enter_context(_new_directory(path))
            created.append({'path': path, 'identity': identity._parent_identity(handle)})
    return dict(state, created=created)


def verify_created_folder(state):
    with ExitStack() as held:
        anchor = identity._checked_path(state['anchor_path'])
        for parent in (*reversed(anchor.parents), anchor):
            handle = held.enter_context(identity._open(parent, parent=True))
        if identity._parent_identity(handle) != state['anchor_identity']:
            return False
        for record in state['created']:
            handle = held.enter_context(identity._open(record['path'], parent=True))
            if identity._parent_identity(handle) != record['identity']:
                return False
        return Path(state['path']).is_dir()


def restore_folder(state):
    if state['existed_before']:
        if not verify_created_folder(state):
            raise ValueError('Existing folder identity changed.')
        return
    for record in reversed(state['created']):
        _delete_exact(record['path'], record['identity'], directory=True)


def verify_restored(state):
    if state['action'] == 'copy_file':
        return not os.path.lexists(state['destination'])
    if state['existed_before']:
        return verify_created_folder(state)
    return bool(state['created']) and all(not os.path.lexists(item['path']) for item in state['created'])
