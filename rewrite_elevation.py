import os
import re

with open('pluma/policy/elevation_broker.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        try:
            import tempfile
            from pathlib import Path
            import ctypes
            from ctypes import wintypes

            class SHELLEXECUTEINFOW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("fMask", wintypes.ULONG),
                    ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR),
                    ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR),
                    ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int),
                    ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p),
                    ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY),
                    ("dwHotKey", wintypes.DWORD),
                    ("DUMMYUNIONNAME", wintypes.HANDLE),
                    ("hProcess", wintypes.HANDLE)
                ]

            SEE_MASK_NOCLOSEPROCESS = 0x00000040
            SEE_MASK_FLAG_NO_UI = 0x00000400
            SW_HIDE = 0

            shell32 = ctypes.WinDLL("shell32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            temp_fd, temp_path = tempfile.mkstemp(suffix=".ps1", prefix="pluma_elev_")
            try:
                with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                    f.write(script)

                sei = SHELLEXECUTEINFOW()
                sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
                sei.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
                sei.lpVerb = "runas"
                sei.lpFile = "powershell.exe"
                sei.lpParameters = f"-NoProfile -NonInteractive -ExecutionPolicy Bypass -File \\"{temp_path}\\""
                sei.nShow = SW_HIDE

                if not shell32.ShellExecuteExW(ctypes.byref(sei)):
                    err = ctypes.get_last_error()
                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    return ToolResult.failure(
                        tool="elevate",
                        error=f"ShellExecuteExW failed with error {err}",
                        duration_ms=duration_ms,
                        adapter_used="elevation_broker",
                    )

                hProcess = sei.hProcess
                if hProcess:
                    # Wait for process
                    timeout_ms = int(effective_timeout * 1000)
                    WAIT_TIMEOUT = 0x00000102
                    res = kernel32.WaitForSingleObject(hProcess, timeout_ms)
                    if res == WAIT_TIMEOUT:
                        kernel32.TerminateProcess(hProcess, 1)
                        kernel32.CloseHandle(hProcess)
                        duration_ms = (time.perf_counter() - t0) * 1000.0
                        return ToolResult.failure(
                            tool="elevate",
                            error=f"Elevated operation timed out after {effective_timeout:.1f}s.",
                            duration_ms=duration_ms,
                            adapter_used="elevation_broker",
                        )
                    
                    exit_code = wintypes.DWORD()
                    kernel32.GetExitCodeProcess(hProcess, ctypes.byref(exit_code))
                    kernel32.CloseHandle(hProcess)

                    duration_ms = (time.perf_counter() - t0) * 1000.0
                    if exit_code.value != 0:
                        return ToolResult.failure(
                            tool="elevate",
                            error=f"Elevated execution failed with exit code {exit_code.value}",
                            duration_ms=duration_ms,
                            adapter_used="elevation_broker",
                        )

                duration_ms = (time.perf_counter() - t0) * 1000.0
                return ToolResult(
                    ok=True,
                    tool="elevate",
                    factual_message="Single-operation elevated command executed successfully.",
                    duration_ms=duration_ms,
                    adapter_used="elevation_broker",
                )
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass'''

code = re.sub(
    r'''        try:
            import tempfile.*?except Exception:
                        pass''',
    replacement,
    code,
    flags=re.DOTALL
)

with open('pluma/policy/elevation_broker.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Elevation fix done')
