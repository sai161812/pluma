import os
import re

with open('pluma/core/ipc.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''def _verify_win32_file_dacl(filepath: str) -> None:
    """Verify that the file DACL grants access only to the current user."""
    import ctypes
    from ctypes import wintypes
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
    advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

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
    
    if "WD" in str_sd.value or "BU" in str_sd.value or "AN" in str_sd.value:
         raise RuntimeError(f"Insecure DACL detected: {str_sd.value}")
'''

code = re.sub(
    r'def _verify_win32_file_dacl\(filepath: str\) -> None:.*?raise RuntimeError\(f"Insecure DACL detected: \{str_sd\.value\}"\)\n',
    replacement,
    code,
    flags=re.DOTALL
)

replacement2 = '''def _restrict_pipe_to_current_user(pipe_name: str) -> None:
    """Restrict the named pipe DACL to the current user SID (Windows only).
    Raises RuntimeError if it fails.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi32.GetTokenInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]

        # Get current user SID
        TOKEN_QUERY = 0x0008
        h_token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(h_token)):
            raise RuntimeError("_restrict_pipe_to_current_user: OpenProcessToken failed")

        TOKEN_USER = 1
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(h_token, TOKEN_USER, None, 0, ctypes.byref(needed))
        buf = ctypes.create_string_buffer(needed.value)
        ok = advapi32.GetTokenInformation(h_token, TOKEN_USER, buf, needed, ctypes.byref(needed))
        kernel32.CloseHandle(h_token)
        if not ok:
            raise RuntimeError("_restrict_pipe_to_current_user: GetTokenInformation failed")

        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
            raise RuntimeError("_restrict_pipe_to_current_user: ConvertSidToStringSidW failed")

        sid_str = sid_str_ptr.value
        sddl = f"D:(A;;GA;;;{sid_str})"
        sd_ptr = ctypes.c_void_p()
        sd_size = wintypes.ULONG()
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd_ptr), ctypes.byref(sd_size)
        ):
            raise RuntimeError("_restrict_pipe_to_current_user: ConvertStringSecurityDescriptorToSecurityDescriptorW failed")

        # Get a handle to the pipe for SetSecurityInfo
        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        h_pipe = kernel32.CreateFileW(
            pipe_name,
            FILE_WRITE_ATTRIBUTES,
            0, None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        if not h_pipe or h_pipe == INVALID_HANDLE_VALUE:
            raise RuntimeError(f"_restrict_pipe_to_current_user: CreateFileW failed err {ctypes.get_last_error()}")

        try:
            # SE_KERNEL_OBJECT=6, DACL_SECURITY_INFORMATION=4
            DACL_SECURITY_INFORMATION = 4
            SE_KERNEL_OBJECT = 6
            ret = advapi32.SetSecurityInfo(
                h_pipe, SE_KERNEL_OBJECT, DACL_SECURITY_INFORMATION,
                None, None, sd_ptr, None
            )
            if ret != 0:  # ERROR_SUCCESS = 0
                raise RuntimeError(f"_restrict_pipe_to_current_user: SetSecurityInfo returned {ret}")
            else:
                logger.debug("Named pipe DACL restricted to current user SID %s", sid_str)
        finally:
            kernel32.CloseHandle(h_pipe)
    except Exception as exc:
        raise RuntimeError(f"_restrict_pipe_to_current_user failed: {exc}")'''

code = re.sub(
    r'def _restrict_pipe_to_current_user\(pipe_name: str\) -> None:.*?raise RuntimeError\(f"_restrict_pipe_to_current_user failed: \{exc\}"\)',
    replacement2,
    code,
    flags=re.DOTALL
)

with open('pluma/core/ipc.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('IPC update 3 done')
