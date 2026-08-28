import os
import re

with open('pluma/core/ipc.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        # Get a handle to the pipe for SetSecurityInfo
        WRITE_DAC = 0x00040000
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        h_pipe = kernel32.CreateFileW(
            pipe_name,
            WRITE_DAC,
            0, None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )'''

code = code.replace(
    '''        # Get a handle to the pipe for SetSecurityInfo
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
        )''',
    replacement
)


with open('pluma/core/ipc.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('IPC WRITE_DAC fixed')
