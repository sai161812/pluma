import os
import re

with open('pluma/core/ipc.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        # Use SetNamedSecurityInfoW to set DACL without needing to open a client handle
        SE_FILE_OBJECT = 1
        DACL_SECURITY_INFORMATION = 4
        
        ret = advapi32.SetNamedSecurityInfoW(
            pipe_name, SE_FILE_OBJECT, DACL_SECURITY_INFORMATION,
            None, None, sd_ptr, None
        )
        if ret != 0:
            raise RuntimeError(f"_restrict_pipe_to_current_user: SetNamedSecurityInfoW returned {ret}")
        else:
            logger.debug("Named pipe DACL restricted to current user SID %s", sid_str)'''

code = re.sub(
    r'''        # Get a handle to the pipe for SetSecurityInfo.*?logger\.debug\("Named pipe DACL restricted to current user SID %s", sid_str\)\n        finally:\n            kernel32\.CloseHandle\(h_pipe\)''',
    replacement,
    code,
    flags=re.DOTALL
)

with open('pluma/core/ipc.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('IPC SetNamedSecurityInfoW fixed')
