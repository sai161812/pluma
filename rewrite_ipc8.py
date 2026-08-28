import os
import re

with open('pluma/core/ipc.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        advapi32.SetFileSecurityW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, ctypes.c_void_p]

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

        DACL_SECURITY_INFORMATION = 4
        if not advapi32.SetFileSecurityW(pipe_name, DACL_SECURITY_INFORMATION, sd_ptr):
            err = ctypes.get_last_error()
            raise RuntimeError(f"_restrict_pipe_to_current_user: SetFileSecurityW failed with err {err}")
        else:
            logger.debug("Named pipe DACL restricted to current user SID %s", sid_str)
    except Exception as exc:'''

code = re.sub(
    r'''        # Get current user SID.*?    except Exception as exc:''',
    replacement,
    code,
    flags=re.DOTALL
)

with open('pluma/core/ipc.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('IPC SetFileSecurityW fixed')
