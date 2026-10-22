"""P09 uses only exact test-owned files/ACLs; no production credential repair."""
from concurrent.futures import ThreadPoolExecutor
import ctypes
import hashlib
import hmac
from ctypes import wintypes as W
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from pluma.adapters.credentials import FileInformation, WindowsCredentialStore
from pluma.core import ipc

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows credential contract')


def assert_same_secret(actual, expected):
    matched = hmac.compare_digest(actual, expected)
    assert matched, 'Fixture credential did not match.'


def key(root):
    return root / 'Pluma' / 'ipc_secret.key'


def set_security(path, sddl):
    """Only called with tmp_path-owned files/directories by these fixtures."""
    store = WindowsCredentialStore()
    descriptor = ctypes.c_void_p()
    store.security.SetFileSecurityW.argtypes = [W.LPCWSTR, W.DWORD, ctypes.c_void_p]
    store.security.SetFileSecurityW.restype = W.BOOL
    assert store.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, ctypes.byref(descriptor), None)
    try:
        assert store.security.SetFileSecurityW(str(path), 0x80000004, descriptor)
    finally:
        store.kernel.LocalFree(descriptor)


def private(path):
    sid = WindowsCredentialStore().user_sid
    set_security(path, f'D:P(A;;FA;;;{sid})')


def test_fresh_key_under_broad_parent_is_private_and_reusable(tmp_path):
    sid = WindowsCredentialStore().user_sid
    set_security(tmp_path, f'D:P(A;OICI;FA;;;{sid})(A;OICI;GR;;;BU)')
    first = ipc._get_or_create_ipc_secret(str(tmp_path))
    store = WindowsCredentialStore()
    with store.opened(key(tmp_path)) as handle:
        assert store.validate(handle) == 32
        assert_same_secret(store.read(handle), first)
    assert_same_secret(ipc._get_or_create_ipc_secret(str(tmp_path)), first)
    ipc._verify_win32_file_dacl(str(key(tmp_path)))


@pytest.mark.parametrize('trustee', ['WD', 'BU', 'AU', 'AN', 'OW'])
def test_existing_broad_allow_is_refused_without_repair_or_rotation(tmp_path, trustee, caplog):
    original = ipc._get_or_create_ipc_secret(str(tmp_path))
    sid = WindowsCredentialStore().user_sid
    set_security(key(tmp_path), f'D:P(A;;FA;;;{sid})(A;;GR;;;{trustee})')
    try:
        with pytest.raises(RuntimeError, match='unavailable or insecure'):
            ipc._get_or_create_ipc_secret(str(tmp_path))
        assert_same_secret(key(tmp_path).read_bytes(), original)
        with pytest.raises(RuntimeError):
            ipc._verify_win32_file_dacl(str(key(tmp_path)))
        leaked = original.hex() in caplog.text
        assert not leaked
    finally:
        private(key(tmp_path))


@pytest.mark.parametrize('trustee', ['SY', 'BA'])
def test_existing_trusted_system_or_administrators_allow_matches_csharp(tmp_path, trustee):
    original = ipc._get_or_create_ipc_secret(str(tmp_path))
    sid = WindowsCredentialStore().user_sid
    set_security(key(tmp_path), f'D:P(A;;FA;;;{sid})(A;;GR;;;{trustee})')
    assert_same_secret(ipc._get_or_create_ipc_secret(str(tmp_path)), original)


@pytest.mark.parametrize('length', [0, 1, 31, 33, 4096])
def test_corrupt_existing_size_is_not_truncated_or_replaced(tmp_path, length):
    ipc._get_or_create_ipc_secret(str(tmp_path))
    contents = b'x' * length
    key(tmp_path).write_bytes(contents)
    with pytest.raises(RuntimeError):
        ipc._get_or_create_ipc_secret(str(tmp_path))
    assert key(tmp_path).read_bytes() == contents


def test_owner_mismatch_fails_opened_handle_validation(tmp_path):
    ipc._get_or_create_ipc_secret(str(tmp_path))
    store = WindowsCredentialStore()
    store.user_sid = 'S-1-5-18'  # injected expected identity; actual owner readback is native
    with store.opened(key(tmp_path)) as handle:
        with pytest.raises(RuntimeError):
            store.read(handle)


def test_null_dacl_is_refused_without_repair(tmp_path):
    original = ipc._get_or_create_ipc_secret(str(tmp_path))
    set_security(key(tmp_path), 'D:NO_ACCESS_CONTROL')
    try:
        with pytest.raises(RuntimeError):
            ipc._get_or_create_ipc_secret(str(tmp_path))
    finally:
        private(key(tmp_path))
    assert_same_secret(key(tmp_path).read_bytes(), original)


def test_access_denied_does_not_fall_back_to_creation(tmp_path):
    original = ipc._get_or_create_ipc_secret(str(tmp_path))
    sid = WindowsCredentialStore().user_sid
    set_security(key(tmp_path), f'D:P(D;;GR;;;{sid})(A;;FA;;;{sid})')
    try:
        with pytest.raises(RuntimeError):
            ipc._get_or_create_ipc_secret(str(tmp_path))
    finally:
        private(key(tmp_path))
    assert_same_secret(key(tmp_path).read_bytes(), original)


def test_concurrent_threads_return_one_winner_without_truncation(tmp_path):
    with ThreadPoolExecutor(12) as pool:
        values = list(pool.map(lambda _: ipc._get_or_create_ipc_secret(str(tmp_path)), range(24)))
    consistent = len(set(values)) == 1
    assert consistent
    length = len(values[0])
    assert length == 32
    assert_same_secret(key(tmp_path).read_bytes(), values[0])


def test_writer_exclusivity_refuses_partial_reader_then_reuses_winner(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    write = WindowsCredentialStore.write
    def blocked(self, handle, secret):
        entered.set()
        assert release.wait(3)
        return write(self, handle, secret)
    monkeypatch.setattr(WindowsCredentialStore, 'write', blocked)
    with ThreadPoolExecutor(1) as pool:
        creating = pool.submit(ipc._get_or_create_ipc_secret, str(tmp_path))
        assert entered.wait(2)
        try:
            start = time.monotonic()
            with pytest.raises(RuntimeError):
                ipc._get_or_create_ipc_secret(str(tmp_path))
            assert time.monotonic() - start < 1.5
        finally:
            release.set()
        winner = creating.result(2)
    assert_same_secret(ipc._get_or_create_ipc_secret(str(tmp_path)), winner)


@pytest.mark.parametrize('failure', ['write', 'flush', 'read', 'validate'])
def test_new_path_failures_never_return_unverified_secret(tmp_path, monkeypatch, failure):
    original = WindowsCredentialStore.write
    if failure in ('read', 'validate'):
        def fail(*args): raise RuntimeError('private failure')
        monkeypatch.setattr(WindowsCredentialStore, failure, fail)
    else:
        def write(self, handle, secret):
            name = 'WriteFile' if failure == 'write' else 'FlushFileBuffers'
            native = getattr(self.kernel, name)
            setattr(self.kernel, name, lambda *args: False)
            try: return original(self, handle, secret)
            finally: setattr(self.kernel, name, native)
        monkeypatch.setattr(WindowsCredentialStore, 'write', write)
    with pytest.raises(RuntimeError, match='unavailable or insecure'):
        ipc._get_or_create_ipc_secret(str(tmp_path))
    assert key(tmp_path).exists()  # exact failed private file retained; no insecure repair


def test_existing_read_handle_blocks_write_or_replacement(tmp_path):
    ipc._get_or_create_ipc_secret(str(tmp_path))
    store = WindowsCredentialStore()
    with store.opened(key(tmp_path)) as handle:
        assert store.read(handle)
        with pytest.raises(OSError):
            key(tmp_path).write_bytes(b'wrong')
        with pytest.raises(OSError):
            key(tmp_path).unlink()


def test_hard_link_is_refused_without_touching_original(tmp_path):
    original = ipc._get_or_create_ipc_secret(str(tmp_path))
    linked = tmp_path / 'owned-link.key'
    os.link(key(tmp_path), linked)
    try:
        with pytest.raises(RuntimeError):
            ipc._get_or_create_ipc_secret(str(tmp_path))
        assert_same_secret(linked.read_bytes(), original)
    finally:
        linked.unlink()


def test_file_directory_is_refused_without_repair(tmp_path):
    key(tmp_path).mkdir(parents=True)
    with pytest.raises(RuntimeError):
        ipc._get_or_create_ipc_secret(str(tmp_path))
    assert key(tmp_path).is_dir()


def test_repeated_validation_releases_native_handles(tmp_path):
    ipc._get_or_create_ipc_secret(str(tmp_path))
    store = WindowsCredentialStore()
    count = W.DWORD()
    store.kernel.GetProcessHandleCount.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
    store.kernel.GetProcessHandleCount.restype = W.BOOL
    def handles():
        assert store.kernel.GetProcessHandleCount(store.kernel.GetCurrentProcess(), ctypes.byref(count))
        return count.value
    before = handles()
    for _ in range(100):
        ipc._get_or_create_ipc_secret(str(tmp_path))
        ipc._verify_win32_file_dacl(str(key(tmp_path)))
    assert handles() <= before + 1


def test_native_subprocess_creators_share_one_stable_winner(tmp_path, record_property):
    # Pipes carry no secret: comparison fingerprints remain transient and unlogged.
    # Every exact Popen handle is owned, bounded and joined by this fixture.
    code = "from pluma.core.ipc import _get_or_create_ipc_secret; import sys,hashlib; s=_get_or_create_ipc_secret(sys.argv[1]); assert len(s)==32; print(hashlib.sha256(s).hexdigest())"
    children = []
    try:
        for _ in range(4):
            children.append(subprocess.Popen([sys.executable, '-c', code, str(tmp_path)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW))
        store = WindowsCredentialStore()
        store.kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
        store.kernel.GetProcessTimes.restype = W.BOOL
        fingerprints = []
        for child in children:
            created, exited, kernel, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
            assert store.kernel.GetProcessTimes(int(child._handle), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user))
            record_property('owned_credential_process', f'task=P09-creators;pid={child.pid};created={created.dwHighDateTime}:{created.dwLowDateTime};class=credential_fixture;ownership=PLUMA_CREATED')
            out, err = child.communicate(timeout=5)
            assert child.returncode == 0 and not err
            fingerprints.append(out.strip())
        same_winner = len(set(fingerprints)) == 1
        assert same_winner
        first = ipc._get_or_create_ipc_secret(str(tmp_path))
        matched = hmac.compare_digest(fingerprints[0], hashlib.sha256(first).hexdigest().encode())
        assert matched
        assert_same_secret(key(tmp_path).read_bytes(), first)
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()  # original PLUMA-owned Popen handle, never a PID lookup
                child.wait(timeout=3)
