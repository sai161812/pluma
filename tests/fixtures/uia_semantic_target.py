"""Owned Win32 window used by P12 semantic UIA acceptance tests."""

from __future__ import annotations

import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path
import sys
import os


BUTTON_ID = 4101
SECOND_BUTTON_ID = 4103
STATUS_ID = 4102
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
BN_CLICKED = 0
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_EX_NOACTIVATE = 0x08000000
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_TABSTOP = 0x00010000
BS_PUSHBUTTON = 0
SS_LEFT = 0


def main() -> None:
    ready_path = Path(sys.argv[1])
    user = c.WinDLL("user32", use_last_error=True)
    kernel = c.WinDLL("kernel32", use_last_error=True)
    lresult = c.c_ssize_t
    wndproc_type = c.WINFUNCTYPE(lresult, w.HWND, w.UINT, w.WPARAM, w.LPARAM)

    user.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user.DefWindowProcW.restype = lresult
    user.CreateWindowExW.argtypes = [
        w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int, c.c_int,
        c.c_int, w.HWND, w.HMENU, w.HINSTANCE, c.c_void_p,
    ]
    user.CreateWindowExW.restype = w.HWND
    user.DestroyWindow.argtypes = [w.HWND]
    user.DestroyWindow.restype = w.BOOL
    user.EnableWindow.argtypes = [w.HWND, w.BOOL]
    user.EnableWindow.restype = w.BOOL
    user.GetDlgItem.argtypes = [w.HWND, c.c_int]
    user.GetDlgItem.restype = w.HWND
    user.GetMessageW.argtypes = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
    user.GetMessageW.restype = c.c_int
    user.TranslateMessage.argtypes = [c.POINTER(w.MSG)]
    user.DispatchMessageW.argtypes = [c.POINTER(w.MSG)]
    user.DispatchMessageW.restype = lresult
    user.PostQuitMessage.argtypes = [c.c_int]
    user.SetWindowTextW.argtypes = [w.HWND, w.LPCWSTR]
    user.SetWindowTextW.restype = w.BOOL
    user.ShowWindow.argtypes = [w.HWND, c.c_int]
    user.UpdateWindow.argtypes = [w.HWND]
    kernel.GetModuleHandleW.argtypes = [w.LPCWSTR]
    kernel.GetModuleHandleW.restype = w.HINSTANCE

    open_windows = 0
    duplicate_labels = False
    textless_window = False

    def handle(hwnd: int, message: int, wp: int, lp: int) -> int:
        nonlocal open_windows
        if message == 0x0001:  # WM_CREATE
            open_windows += 1
            if textless_window:
                return 0
            button = user.CreateWindowExW(
                0, "BUTTON", "Submit", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                24, 28, 150, 36, hwnd, w.HMENU(BUTTON_ID), instance, None,
            )
            second_button = None
            if duplicate_labels:
                second_button = user.CreateWindowExW(
                    0, "BUTTON", "Submit", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                    24, 76, 150, 36, hwnd, w.HMENU(SECOND_BUTTON_ID), instance, None,
                )
            status = user.CreateWindowExW(
                0, "STATIC", "Ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
                24, 132 if duplicate_labels else 82, 220, 28, hwnd, w.HMENU(STATUS_ID), instance, None,
            )
            if not button or (duplicate_labels and not second_button) or not status:
                return -1
            return 0
        if message == WM_COMMAND and (wp & 0xFFFF) in {BUTTON_ID, SECOND_BUTTON_ID} and ((wp >> 16) & 0xFFFF) == BN_CLICKED:
            button = user.GetDlgItem(hwnd, wp & 0xFFFF)
            status = user.GetDlgItem(hwnd, STATUS_ID)
            if button:
                user.EnableWindow(button, False)
            if status:
                user.SetWindowTextW(status, "Submitted")
            return 0
        if message == WM_CLOSE:
            user.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            open_windows -= 1
            if open_windows == 0:
                user.PostQuitMessage(0)
            return 0
        return int(user.DefWindowProcW(hwnd, message, wp, lp))

    procedure = wndproc_type(handle)

    class_name = f"PLUMA_P12_UIA_{os.getpid()}"

    class WndClass(c.Structure):
        _fields_ = [
            ("style", w.UINT),
            ("procedure", wndproc_type),
            ("class_extra", c.c_int),
            ("window_extra", c.c_int),
            ("instance", w.HINSTANCE),
            ("icon", w.HANDLE),
            ("cursor", w.HANDLE),
            ("background", w.HANDLE),
            ("menu", w.LPCWSTR),
            ("name", w.LPCWSTR),
        ]

    instance = kernel.GetModuleHandleW(None)
    definition = WndClass(0, procedure, 0, 0, instance, None, None, None, None, class_name)
    user.RegisterClassW.argtypes = [c.POINTER(WndClass)]
    user.RegisterClassW.restype = w.ATOM
    if not user.RegisterClassW(c.byref(definition)):
        raise c.WinError()

    def create_window(
        title: str,
        x: int,
        include_duplicate_labels: bool,
        include_textless_canvas: bool = False,
    ) -> int:
        nonlocal duplicate_labels, textless_window
        duplicate_labels = include_duplicate_labels
        textless_window = include_textless_canvas
        hwnd = user.CreateWindowExW(
            WS_EX_NOACTIVATE, class_name, title, WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            x, 160, 420, 240, None, None, instance, None,
        )
        if not hwnd:
            raise c.WinError()
        user.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
        user.UpdateWindow(hwnd)
        return int(hwnd)

    hwnd = create_window("PLUMA P12 UIA fixture", 180, False)
    duplicate_hwnd = create_window("PLUMA P12 duplicate-label fixture", 620, True)
    textless_hwnd = create_window("PLUMA P12 textless fixture", 1060, False, True)

    temporary = ready_path.with_suffix(".partial")
    temporary.write_text(
        json.dumps({
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "hwnd": int(hwnd),
            "duplicate_hwnd": duplicate_hwnd,
            "textless_hwnd": textless_hwnd,
        }),
        encoding="utf-8",
    )
    temporary.replace(ready_path)

    message = w.MSG()
    while True:
        result = user.GetMessageW(c.byref(message), None, 0, 0)
        if result == -1:
            raise c.WinError()
        if result == 0:
            return
        user.TranslateMessage(c.byref(message))
        user.DispatchMessageW(c.byref(message))


if __name__ == "__main__":
    main()
