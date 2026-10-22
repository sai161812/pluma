"""On-demand Windows recycle-only transfer and exact, non-overwriting restore.

No RemoveItem, shell command, permanent deletion or global Recycle Bin undo.
Files and bounded directory trees on fixed NTFS volumes are supported.
"""
from contextlib import contextmanager, ExitStack
import os
import hashlib
import json
from pathlib import Path
import stat

from pluma.adapters import file_identity as identity
from pluma.adapters.file_operations import _copy_snapshot, _copy_observe, _basic, _streams


def _volume(path):
    c, w, k = identity._api()
    k.GetDriveTypeW.argtypes, k.GetDriveTypeW.restype = [w.LPCWSTR], w.UINT
    k.GetVolumePathNameW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD]
    k.GetVolumePathNameW.restype = w.BOOL
    k.GetVolumeInformationW.argtypes = [w.LPCWSTR, w.LPWSTR, w.DWORD,
        c.POINTER(w.DWORD), c.POINTER(w.DWORD), c.POINTER(w.DWORD), w.LPWSTR, w.DWORD]
    k.GetVolumeInformationW.restype = w.BOOL
    root, filesystem = c.create_unicode_buffer(32768), c.create_unicode_buffer(32)
    if not k.GetVolumePathNameW(str(path), root, len(root)):
        raise c.WinError()
    if (k.GetDriveTypeW(root.value) != 3 or not k.GetVolumeInformationW(
            root.value, None, 0, None, None, None, filesystem, len(filesystem))
            or filesystem.value != 'NTFS' or Path(root.value) != Path(Path(path).anchor)):
        raise ValueError('Only an ordinary fixed NTFS volume is supported.')
    return Path(root.value)


def _sid():
    import win32api
    import win32con
    import win32security
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        return win32security.ConvertSidToStringSid(win32security.GetTokenInformation(token, win32security.TokenUser)[0])
    finally:
        token.Close()


def _eligible(path, *, allow_recycled=False):
    path = identity._checked_path(path)
    root = _volume(path)
    info = path.lstat()
    if (not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))
            or (stat.S_ISREG(info.st_mode) and info.st_nlink != 1)
            or getattr(info, 'st_file_attributes', 0) & (0x400 | 0x1000 | 0x4000)
            or (not allow_recycled and any(part.casefold() == '$recycle.bin' for part in path.parts))):
        raise ValueError('Only local non-reparse, online, unencrypted files and folders are supported; hard links are refused.')
    return path, root


def _directory_has_streams(path):
    return identity._directory_has_streams(path)


def _snapshot(path, token=None):
    """Hold every observed tree entry; hash names/content only in worker memory."""
    path = identity._checked_path(path)
    if not path.is_dir():
        return _copy_snapshot(path, token)
    records, directory_checks, total = [], [], 0
    with ExitStack() as held:
        for parent in reversed(path.parents):
            held.enter_context(identity._open(parent, parent=True))
        pending = [(path, 0)]
        root = None
        while pending:
            target, depth = pending.pop()
            if token is not None:
                token.raise_if_cancelled()
            if depth > 32 or len(records) >= identity.MAX_TREE_ENTRIES:
                raise ValueError('Directory snapshot bound exceeded.')
            _eligible(target, allow_recycled=True)
            handle = held.enter_context(identity._open(target))
            metadata = identity._metadata(handle)
            if metadata['kind'] == 'directory':
                if _directory_has_streams(target):
                    raise ValueError('Directory data streams are unsupported; no mutation performed.')
                observed = dict(metadata, **_basic(handle), size_bytes=0)
                directory_checks.append((handle, observed))
                with os.scandir(target) as entries:
                    for entry in entries:
                        if len(pending) + len(records) >= identity.MAX_TREE_ENTRIES:
                            raise ValueError('Directory snapshot entry bound exceeded.')
                        pending.append((Path(entry.path), depth + 1))
            else:
                sizes = _streams(handle)
                total += sum(size for _, size in sizes)
                if total > identity.MAX_FILE_BYTES:
                    raise ValueError('Directory data exceeds the total bounded fingerprint size.')
                observed = _copy_observe(handle, target, token)
            if target == path:
                root = observed
            else:
                records.append((str(target.relative_to(path)), observed))
        for handle, expected in directory_checks:
            actual = dict(identity._metadata(handle), **_basic(handle), size_bytes=0)
            if actual != expected:
                raise ValueError('Directory changed during inspection.')
    encoded = json.dumps(sorted(records), ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
    stable = json.dumps(sorted((name, _content(observed)) for name, observed in records),
        ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()
    return dict(root, tree_digest=list(hashlib.sha256(stable).digest()),
        tree_revision_digest=list(hashlib.sha256(encoded).digest()), tree_entries=len(records), tree_bytes=total)


def capture(path):
    path, _ = _eligible(path)
    _sid()  # Resolve native identity before any mutation.
    with identity._open(path.parent, parent=True) as parent:
        return {'action': 'safe_delete', 'guard_version': 1, 'path': str(path),
                'source_parent': identity._parent_identity(parent), 'identity': _snapshot(path)}


def _content(value):
    # Shell transfer updates change times for descendants too. Keep a separate
    # revision digest for exact before-dispatch/current-receipt conflict checks;
    # file IDs, attributes, stream bytes, names and last-write times must survive.
    return {key: item for key, item in value.items() if key not in ('changed_100ns', 'tree_revision_digest')}


@contextmanager
def _shell(token=None):
    # Imports and COM initialization happen only inside an admitted tool worker.
    import ctypes as c
    import pythoncom
    from comtypes import IUnknown, GUID, COMMETHOD, HRESULT, COMObject
    from win32com.shell import shell

    class Advise(IUnknown):
        _iid_ = GUID(str(shell.IID_ITransferAdviseSink))
        _methods_ = [
            COMMETHOD([], HRESULT, 'UpdateProgress', *[(['in'], typ, name) for typ, name in
                [(c.c_ulonglong, 'a'), (c.c_ulonglong, 'b'), (c.c_int, 'd'),
                 (c.c_int, 'e'), (c.c_int, 'f'), (c.c_int, 'g')]]),
            COMMETHOD([], HRESULT, 'UpdateTransferState', (['in'], c.c_ulong, 'state')),
            COMMETHOD([], HRESULT, 'ConfirmOverwrite', (['in'], c.c_void_p, 'item'),
                (['in'], c.c_void_p, 'parent'), (['in'], c.c_wchar_p, 'name')),
            COMMETHOD([], HRESULT, 'ConfirmEncryptionLoss', (['in'], c.c_void_p, 'item')),
            COMMETHOD([], HRESULT, 'FileFailure', (['in'], c.c_void_p, 'item'),
                (['in'], c.c_wchar_p, 'name'), (['in'], HRESULT, 'error'),
                (['out'], c.POINTER(c.c_void_p), 'new_name')),
            COMMETHOD([], HRESULT, 'SubStreamFailure', (['in'], c.c_void_p, 'item'),
                (['in'], c.c_wchar_p, 'name'), (['in'], HRESULT, 'error')),
            COMMETHOD([], HRESULT, 'PropertyFailure', (['in'], c.c_void_p, 'item'),
                (['in'], c.c_void_p, 'key'), (['in'], HRESULT, 'error')),
        ]

    class Sink(COMObject):
        _com_interfaces_ = [Advise]

        def UpdateProgress(self, *args):
            return -2147467260 if token is not None and token.is_cancelled else 0

        UpdateTransferState = UpdateProgress

        def ConfirmOverwrite(self, *args):
            return -2147467260

        ConfirmEncryptionLoss = FileFailure = SubStreamFailure = PropertyFailure = ConfirmOverwrite

    pythoncom.CoInitialize()
    try:
        sink = Sink()
        pointer = sink.QueryInterface(Advise)
        wrapped = pythoncom.ObjectFromAddress(c.cast(pointer, c.c_void_p).value, pythoncom.IID_IUnknown)
        yield shell, wrapped
    finally:
        pythoncom.CoUninitialize()


def _transfer(shell, sink, source, destination, *, restore=False, name=None, token=None, expected=None):
    if token is not None:
        token.raise_if_cancelled()
    source_item = shell.SHCreateItemFromParsingName(str(source), None, shell.IID_IShellItem)
    parent = source_item.GetParent()
    transfer = parent.BindToHandler(None, shell.BHID_Transfer, shell.IID_ITransferSource)
    cookie = transfer.Advise(sink)
    try:
        target = shell.SHCreateItemFromParsingName(str(destination), None, shell.IID_IShellItem)
        if expected is not None and _snapshot(source, token) != expected:
            raise ValueError('Transfer source changed after Shell binding.')
        if token is not None:
            token.raise_if_cancelled()
        # TSF_FAIL_EXIST=0. Never retry with overwrite/rename, RemoveItem,
        # copy/delete, elevation, UI prompts or a permanent-delete operation.
        hr, item = (transfer.MoveItem(source_item, target, name, 0) if restore else
                    transfer.RecycleItem(source_item, target, 0))
        if hr < 0 or item is None:
            raise ValueError('Windows did not return an exact transferred item.')
        return item.GetDisplayName(0x80058000)  # SIGDN_FILESYSPATH
    finally:
        transfer.Unadvise(cookie)


def _receipt_path(state):
    source, root = Path(state['path']), _volume(state['path'])
    recycled = identity._checked_path(state['recycled_path'])
    if (recycled.parent != root / '$Recycle.Bin' / _sid()
            or not recycled.name.startswith('$R') or source == recycled):
        raise ValueError('An exact current-user Recycle Bin receipt is required.')
    return recycled


def recycle(state, token=None):
    source, _ = _eligible(state['path'])
    with ExitStack() as held:
        handles = {parent: held.enter_context(identity._open(parent, parent=True)) for parent in reversed(source.parents)}
        if (identity._parent_identity(handles[source.parent]) != state['source_parent']
                or _snapshot(source, token) != state['identity']):
            raise ValueError('Source or parent changed after capture.')
        with _shell(token) as (shell, sink):
            recycled = _transfer(shell, sink, source, 'shell:RecycleBinFolder', token=token,
                                 expected=state['identity'])
    receipt = dict(state, recycled_path=recycled)
    _receipt_path(receipt)
    receipt['recycled_identity'] = _snapshot(recycled)
    if not verify(receipt):
        raise ValueError('Recycle postcondition could not be verified; original intent remains journaled.')
    return receipt


def verify(state, *, restored=False):
    recycled = _receipt_path(state)
    source = Path(state['path'])
    with identity._open(source.parent, parent=True) as parent:
        if identity._parent_identity(parent) != state['source_parent']:
            return False
        if restored:
            return not os.path.lexists(recycled) and _content(_snapshot(source)) == _content(state['identity'])
        return (not os.path.lexists(source) and _snapshot(recycled) == state['recycled_identity']
                and _content(state['recycled_identity']) == _content(state['identity']))


def restore(state, token=None):
    if state.get('guard_version') != 1 or not verify(state):
        raise ValueError('Recycle receipt, source path or parent conflicts with undo.')
    source, recycled = Path(state['path']), _receipt_path(state)
    with identity._open(source.parent, parent=True) as parent:
        if identity._parent_identity(parent) != state['source_parent'] or os.path.lexists(source):
            raise ValueError('Restore target is occupied or replaced.')
        with _shell(token) as (shell, sink):
            result = _transfer(shell, sink, recycled, source.parent, restore=True, name=source.name, token=token,
                               expected=state['recycled_identity'])
        if Path(result) != source or not verify(state, restored=True):
            raise ValueError('Restore readback failed.')


def recover_pending(state, token=None):
    """Resolve durable intent by exact native identity, never basename guessing.

    Called only after the original executor has been drained. Existing original
    data wins over a possible inverse. A bounded Bin metadata scan reads content
    only after its original folder and native file identity match the intent.
    """
    if state.get('action') != 'safe_delete' or state.get('guard_version') != 1:
        raise ValueError('A guarded recycle intent is required.')
    source = Path(state['path'])
    with identity._open(source.parent, parent=True) as handle:
        if identity._parent_identity(handle) != state['source_parent']:
            raise ValueError('Original parent identity changed.')
        if os.path.lexists(source):
            if _content(_snapshot(source, token)) != _content(state['identity']):
                raise ValueError('Original path contains newer owner data.')
            return {'effect': 'original_present', 'restored': False}
        from win32com.propsys import propsys
        candidates = []
        with _shell(token) as (shell, sink):
            bin_item = shell.SHCreateItemFromParsingName('shell:RecycleBinFolder', None, shell.IID_IShellItem)
            entries = bin_item.BindToHandler(None, shell.BHID_EnumItems, shell.IID_IEnumShellItems)
            deleted_from = propsys.PSGetPropertyKeyFromName('System.Recycle.DeletedFrom')
            for index, item in enumerate(entries):
                if token is not None:
                    token.raise_if_cancelled()
                if index >= 4096:
                    raise ValueError('Recycle Bin metadata exceeds the recovery scan bound.')
                original_parent = item.QueryInterface(shell.IID_IShellItem2).GetString(deleted_from)
                if Path(original_parent) != source.parent:
                    continue
                candidate = item.GetDisplayName(0x80058000)
                try:
                    with identity._open(candidate) as candidate_handle:
                        actual = identity._metadata(candidate_handle)
                        if any(actual[key] != state['identity'][key] for key in ('volume', 'file_id', 'kind')):
                            continue
                    observed = _snapshot(candidate, token)
                    if _content(observed) != _content(state['identity']):
                        raise ValueError('Exact recycled target has changed.')
                    receipt = dict(state, recycled_path=candidate, recycled_identity=observed)
                    _receipt_path(receipt)
                    candidates.append(receipt)
                except FileNotFoundError:
                    raise ValueError('Recovery candidate disappeared.') from None
        if len(candidates) != 1:
            raise ValueError('Exactly one unchanged recycled identity is required for recovery.')
        restore(candidates[0], token)
        return {'effect': 'recycled_identity_restored', 'restored': True}
