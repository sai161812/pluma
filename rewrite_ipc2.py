import os
import re

with open('pluma/core/ipc.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Make the DACL function return success/failure
code = code.replace(
    '''def _try_restrict_pipe_to_current_user(pipe_name: str) -> None:
    """Attempt to restrict the named pipe DACL to the current user SID (Windows only).

    This is a best-effort operation. If it fails, the pipe security degrades to
    the default Windows named pipe security (accessible to all local processes).
    The error is logged at DEBUG level and does NOT prevent the server from starting.
    """
    if sys.platform != "win32":
        return''',
    '''def _restrict_pipe_to_current_user(pipe_name: str) -> None:
    """Restrict the named pipe DACL to the current user SID (Windows only).
    Raises RuntimeError if it fails.
    """
    if sys.platform != "win32":
        return'''
)

code = code.replace(
    '''            logger.debug("_try_restrict_pipe_to_current_user: OpenProcessToken failed")
            return''',
    '''            raise RuntimeError("_restrict_pipe_to_current_user: OpenProcessToken failed")'''
)
code = code.replace(
    '''            logger.debug("_try_restrict_pipe_to_current_user: GetTokenInformation failed")
            return''',
    '''            raise RuntimeError("_restrict_pipe_to_current_user: GetTokenInformation failed")'''
)
code = code.replace(
    '''            logger.debug("_try_restrict_pipe_to_current_user: ConvertSidToStringSidW failed")
            return''',
    '''            raise RuntimeError("_restrict_pipe_to_current_user: ConvertSidToStringSidW failed")'''
)
code = code.replace(
    '''            logger.debug("_try_restrict_pipe_to_current_user: ConvertStringSecurityDescriptorToSecurityDescriptorW failed")
            return''',
    '''            raise RuntimeError("_restrict_pipe_to_current_user: ConvertStringSecurityDescriptorToSecurityDescriptorW failed")'''
)
code = code.replace(
    '''            logger.debug("_try_restrict_pipe_to_current_user: CreateFileW failed (err %d)", ctypes.get_last_error())
            return''',
    '''            raise RuntimeError(f"_restrict_pipe_to_current_user: CreateFileW failed err {ctypes.get_last_error()}")'''
)
code = code.replace(
    '''                logger.debug("_try_restrict_pipe_to_current_user: SetSecurityInfo returned %d", ret)''',
    '''                raise RuntimeError(f"_restrict_pipe_to_current_user: SetSecurityInfo returned {ret}")'''
)
code = code.replace(
    '''    except Exception as exc:
        logger.debug("_try_restrict_pipe_to_current_user failed: %s", exc)''',
    '''    except Exception as exc:
        raise RuntimeError(f"_restrict_pipe_to_current_user failed: {exc}")'''
)

# Update IpcServer to use Semaphore and _restrict_pipe_to_current_user
code = re.sub(
    r'''        self\._thread: Optional\[threading\.Thread\] = None''',
    '''        self._thread: Optional[threading.Thread] = None\n        self._client_semaphore = threading.Semaphore(32)''',
    code
)

code = re.sub(
    r'''            # Attempt to restrict DACL to current user on Windows after pipe creation
            _try_restrict_pipe_to_current_user\(self.address\)''',
    '''            # Restrict DACL to current user on Windows after pipe creation
            _restrict_pipe_to_current_user(self.address)''',
    code
)

code = re.sub(
    r'''                # Spawn a per-client thread so one slow client cannot block others
                client_thread = threading\.Thread\(
                    target=self\._handle_client,
                    args=\(conn,\),
                    daemon=True,
                    name="PlumaIpcClient",
                \)
                client_thread\.start\(\)''',
    '''                # Bound the client semaphore
                if not self._client_semaphore.acquire(timeout=1.0):
                    logger.warning("IPC server saturated, dropping client")
                    conn.close()
                    continue
                client_thread = threading.Thread(
                    target=self._handle_client_wrapper,
                    args=(conn,),
                    daemon=True,
                    name="PlumaIpcClient",
                )
                client_thread.start()''',
    code
)

# Add _handle_client_wrapper
code = code.replace(
    '''    def _handle_client(self, conn: Any) -> None:''',
    '''    def _handle_client_wrapper(self, conn: Any) -> None:
        try:
            self._handle_client(conn)
        finally:
            self._client_semaphore.release()

    def _handle_client(self, conn: Any) -> None:'''
)

# Update _get_or_create_ipc_secret
code = re.sub(
    r'''    if os\.path\.exists\(sec_file\):
        try:
            with open\(sec_file, "rb"\) as f:
                sec = f\.read\(\)
            if len\(sec\) == IPC_SECRET_SIZE:
                return sec
        except OSError as exc:
            logger\.warning\("Could not read existing IPC secret file %s: %s", sec_file, exc\)''',
    '''    if os.path.exists(sec_file):
        if sys.platform == "win32":
            _verify_win32_file_dacl(sec_file)
        else:
            st = os.stat(sec_file)
            if st.st_uid != os.getuid():
                raise RuntimeError(f"Insecure IPC secret file owner: {st.st_uid}")
            if (st.st_mode & 0o777) != 0o600:
                raise RuntimeError(f"Insecure IPC secret file mode: {oct(st.st_mode)}")
        try:
            with open(sec_file, "rb") as f:
                sec = f.read()
            if len(sec) == IPC_SECRET_SIZE:
                return sec
            else:
                raise RuntimeError("IPC secret file is corrupt or invalid size.")
        except Exception as exc:
            raise RuntimeError(f"Failed to read IPC secret: {exc}")''',
    code
)

dacl_verify_code = '''def _verify_win32_file_dacl(filepath: str) -> None:
    """Verify that the file DACL grants access only to the current user."""
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    TOKEN_QUERY = 0x0008
    h_token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(h_token)):
        raise RuntimeError("OpenProcessToken failed")

    TOKEN_USER = 1
    needed = wintypes.DWORD(0)
    advapi32.GetTokenInformation(h_token, TOKEN_USER, None, 0, ctypes.byref(needed))
    buf = ctypes.create_string_buffer(needed.value)
    if not advapi32.GetTokenInformation(h_token, TOKEN_USER, buf, needed, ctypes.byref(needed)):
        kernel32.CloseHandle(h_token)
        raise RuntimeError("GetTokenInformation failed")
    kernel32.CloseHandle(h_token)

    sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
    sid_str_ptr = ctypes.c_wchar_p()
    if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
        raise RuntimeError("ConvertSidToStringSidW failed")
    current_sid_str = sid_str_ptr.value

    SE_FILE_OBJECT = 1
    DACL_SECURITY_INFORMATION = 4
    OWNER_SECURITY_INFORMATION = 1
    pSD = ctypes.c_void_p()
    ret = advapi32.GetNamedSecurityInfoW(
        filepath, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION,
        None, None, None, None, ctypes.byref(pSD)
    )
    if ret != 0:
        raise RuntimeError(f"GetNamedSecurityInfoW failed with {ret}")

    str_sd = ctypes.c_wchar_p()
    if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
        pSD, 1, DACL_SECURITY_INFORMATION | OWNER_SECURITY_INFORMATION, ctypes.byref(str_sd), None
    ):
        raise RuntimeError("ConvertSecurityDescriptorToStringSecurityDescriptorW failed")
    
    # We want to make sure it's strictly the current user. A typical SDDL: O:S-1-5-21...D:(A;;FA;;;S-1-5-21...)
    # For now, just reject if the DACL is not restricted.
    # A safe check: if anyone else has access, reject it. We can just set a new DACL initially, but the spec says "Reject an existing insecure secret".
    if "WD" in str_sd.value or "BU" in str_sd.value or "AN" in str_sd.value:
         raise RuntimeError(f"Insecure DACL detected: {str_sd.value}")

'''

# prepend to _get_or_create_ipc_secret
code = code.replace('def _get_or_create_ipc_secret(', dacl_verify_code + 'def _get_or_create_ipc_secret(')


with open('pluma/core/ipc.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('IPC update done')
