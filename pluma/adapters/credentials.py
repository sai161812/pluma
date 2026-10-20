"""Windows credential files: exclusive creation and opened-handle readback.

No credential repair, rotation, global ACL changes or secret logging. Native
dependencies are loaded only when the Windows IPC credential is requested.
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes as W
import hmac
import secrets
import time


class SecurityAttributes(ctypes.Structure):
    _fields_ = [("length", W.DWORD), ("descriptor", ctypes.c_void_p), ("inherit", W.BOOL)]


class FileInformation(ctypes.Structure):
    _fields_ = [("attributes", W.DWORD), ("created", W.FILETIME),
        ("accessed", W.FILETIME), ("written", W.FILETIME), ("volume", W.DWORD),
        ("size_high", W.DWORD), ("size_low", W.DWORD), ("links", W.DWORD),
        ("index_high", W.DWORD), ("index_low", W.DWORD)]


class Acl(ctypes.Structure):
    _fields_ = [("revision", W.BYTE), ("reserved", W.BYTE), ("size", W.WORD),
               ("count", W.WORD), ("reserved2", W.WORD)]


class WindowsCredentialStore:
    """Same trust boundary as CoreIpcClient: user owner; user/SYSTEM/admin allow.

    CREATE_NEW installs the explicit protected descriptor at creation. A zero
    share mask keeps incomplete bytes unreadable until validated/flush/close.
    Reuse allows readers only, preventing data writes/delete/rename through the
    opened file while its security and bytes are inspected. Contention retries
    are bounded; an existing invalid file is never truncated or repaired.
    """
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.security = ctypes.WinDLL("advapi32", use_last_error=True)
        P = ctypes.c_void_p
        def bind(dll, name, args, result):
            function = getattr(dll, name)
            function.argtypes, function.restype = args, result
        bind(self.kernel, "GetCurrentProcess", [], W.HANDLE)
        bind(self.kernel, "CloseHandle", [W.HANDLE], W.BOOL)
        bind(self.kernel, "LocalFree", [P], P)
        bind(self.kernel, "CreateFileW", [W.LPCWSTR, W.DWORD, W.DWORD, P, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE)
        bind(self.kernel, "GetFileType", [W.HANDLE], W.DWORD)
        bind(self.kernel, "GetFileInformationByHandle", [W.HANDLE, ctypes.POINTER(FileInformation)], W.BOOL)
        bind(self.kernel, "SetFilePointerEx", [W.HANDLE, ctypes.c_longlong, P, W.DWORD], W.BOOL)
        bind(self.kernel, "ReadFile", [W.HANDLE, P, W.DWORD, ctypes.POINTER(W.DWORD), P], W.BOOL)
        bind(self.kernel, "WriteFile", [W.HANDLE, P, W.DWORD, ctypes.POINTER(W.DWORD), P], W.BOOL)
        bind(self.kernel, "FlushFileBuffers", [W.HANDLE], W.BOOL)
        bind(self.security, "OpenProcessToken", [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)], W.BOOL)
        bind(self.security, "GetTokenInformation", [W.HANDLE, W.DWORD, P, W.DWORD, ctypes.POINTER(W.DWORD)], W.BOOL)
        bind(self.security, "ConvertSidToStringSidW", [P, ctypes.POINTER(W.LPWSTR)], W.BOOL)
        bind(self.security, "ConvertStringSecurityDescriptorToSecurityDescriptorW", [W.LPCWSTR, W.DWORD, ctypes.POINTER(P), P], W.BOOL)
        bind(self.security, "GetSecurityInfo", [W.HANDLE, W.DWORD, W.DWORD, ctypes.POINTER(P), P, ctypes.POINTER(P), P, ctypes.POINTER(P)], W.DWORD)
        bind(self.security, "IsValidAcl", [P], W.BOOL)
        bind(self.security, "IsValidSid", [P], W.BOOL)
        bind(self.security, "GetLengthSid", [P], W.DWORD)
        bind(self.security, "GetAce", [P, W.DWORD, ctypes.POINTER(P)], W.BOOL)
        self.user_sid = self._current_user_sid()

    @staticmethod
    def _require(ok):
        if not ok:
            raise RuntimeError("IPC credential verification failed.")

    def _sid(self, pointer):
        self._require(pointer and self.security.IsValidSid(pointer))
        value = W.LPWSTR()
        self._require(self.security.ConvertSidToStringSidW(pointer, ctypes.byref(value)))
        try:
            return value.value
        finally:
            self.kernel.LocalFree(ctypes.cast(value, ctypes.c_void_p))

    def _current_user_sid(self):
        token = W.HANDLE()
        self._require(self.security.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)))
        try:
            needed = W.DWORD()
            self.security.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
            self._require(0 < needed.value < 65536)
            buffer = ctypes.create_string_buffer(needed.value)
            self._require(self.security.GetTokenInformation(token, 1, buffer, needed, ctypes.byref(needed)))
            return self._sid(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
        finally:
            self._require(self.kernel.CloseHandle(token))

    @contextmanager
    def descriptor(self):
        descriptor = ctypes.c_void_p()
        # Explicit owner even for elevated hosts whose default owner is admins.
        sddl = f"O:{self.user_sid}D:P(A;;FA;;;{self.user_sid})"
        self._require(self.security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None))
        try:
            yield SecurityAttributes(ctypes.sizeof(SecurityAttributes), descriptor, False)
        finally:
            self.kernel.LocalFree(descriptor)

    @contextmanager
    def opened(self, path, *, create=False):
        with self.descriptor() if create else _no_descriptor() as attributes:
            handle = self.kernel.CreateFileW(str(path), 0xC0000000 if create else 0x80000000,
                0 if create else 1, ctypes.byref(attributes) if create else None,
                1 if create else 3, 0x00200080, None)  # CREATE_NEW / OPEN_EXISTING; OPEN_REPARSE_POINT
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield handle
        finally:
            self._require(self.kernel.CloseHandle(handle))

    def validate(self, handle):
        information = FileInformation()
        self._require(self.kernel.GetFileType(handle) == 1)
        self._require(self.kernel.GetFileInformationByHandle(handle, ctypes.byref(information)))
        self._require(not information.attributes & (0x10 | 0x400) and information.links == 1)
        owner, dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
        result = self.security.GetSecurityInfo(handle, 1, 5, ctypes.byref(owner), None,
                                              ctypes.byref(dacl), None, ctypes.byref(descriptor))
        self._require(result == 0)
        try:
            self._require(self._sid(owner) == self.user_sid)
            self._require(dacl and self.security.IsValidAcl(dacl))  # null DACL grants everyone access
            acl = ctypes.cast(dacl, ctypes.POINTER(Acl)).contents
            for index in range(acl.count):
                ace = ctypes.c_void_p()
                self._require(self.security.GetAce(dacl, index, ctypes.byref(ace)))
                ace_type = ctypes.c_ubyte.from_address(ace.value).value
                size = ctypes.c_ushort.from_address(ace.value + 2).value
                self._require(size >= 4 and ace_type in (0, 1))  # unsupported ACE forms fail closed
                if ace_type == 0:
                    self._require(size >= 16)
                    sid = ace.value + 8
                    self._require(self.security.IsValidSid(sid) and self.security.GetLengthSid(sid) <= size - 8)
                    self._require(self._sid(sid) in (self.user_sid, "S-1-5-18", "S-1-5-32-544"))
        finally:
            self.kernel.LocalFree(descriptor)
        return (information.size_high << 32) | information.size_low

    def read(self, handle):
        self._require(self.validate(handle) == 32)
        self._require(self.kernel.SetFilePointerEx(handle, 0, None, 0))
        data, count = ctypes.create_string_buffer(33), W.DWORD()
        self._require(self.kernel.ReadFile(handle, data, 33, ctypes.byref(count), None))
        self._require(count.value == 32 and self.validate(handle) == 32)
        return data.raw[:32]

    def write(self, handle, secret):
        self._require(self.validate(handle) == 0)
        count = W.DWORD()
        self._require(self.kernel.WriteFile(handle, secret, len(secret), ctypes.byref(count), None))
        self._require(count.value == 32 and self.kernel.FlushFileBuffers(handle))
        result = self.read(handle)
        self._require(hmac.compare_digest(result, secret))
        return result

    def load(self, path, timeout_s=0.5):
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                with self.opened(path) as handle:
                    return self.read(handle)
            except OSError as error:
                if error.winerror == 2:
                    try:
                        with self.opened(path, create=True) as handle:
                            return self.write(handle, secrets.token_bytes(32))
                    except OSError as competing:
                        if competing.winerror not in (32, 33, 80, 183):
                            raise
                elif error.winerror not in (32, 33):
                    raise
            if time.monotonic() >= deadline:
                raise RuntimeError("IPC credential is busy or unavailable.")
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))


@contextmanager
def _no_descriptor():
    yield None


def load_windows_credential(path):
    try:
        return WindowsCredentialStore().load(path)
    except Exception:
        raise RuntimeError("IPC credential is unavailable or insecure.") from None


def verify_windows_credential(path):
    try:
        store = WindowsCredentialStore()
        with store.opened(path) as handle:
            store.validate(handle)
    except Exception:
        raise RuntimeError("IPC credential is unavailable or insecure.") from None
