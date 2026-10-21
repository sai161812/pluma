"""Disposable hidden native window for P11 process-exit tests; never activates."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
import time


def main():
    marker, mode = Path(sys.argv[1]), sys.argv[2]
    if mode == 'headless':
        marker.write_text(json.dumps({'pid': os.getpid(), 'hwnd': None}), encoding='utf-8')
        time.sleep(60)
        return
    user, kernel = c.WinDLL('user32', use_last_error=True), c.WinDLL('kernel32', use_last_error=True)
    procedure = c.WINFUNCTYPE(c.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
    class WindowClass(c.Structure):
        _fields_ = [('style', w.UINT), ('procedure', procedure), ('class_extra', c.c_int),
            ('window_extra', c.c_int), ('instance', w.HINSTANCE), ('icon', w.HANDLE),
            ('cursor', w.HANDLE), ('background', w.HANDLE), ('menu', w.LPCWSTR), ('name', w.LPCWSTR)]
    user.DefWindowProcW.argtypes, user.DefWindowProcW.restype = [w.HWND, w.UINT, w.WPARAM, w.LPARAM], c.c_ssize_t
    user.DestroyWindow.argtypes, user.DestroyWindow.restype = [w.HWND], w.BOOL
    user.PostQuitMessage.argtypes = [c.c_int]
    def handle(hwnd, message, wp, lp):
        if message == 0x10:
            if mode != 'refuse':
                if not user.DestroyWindow(hwnd):
                    raise c.WinError()
            return 0
        if message == 2:
            user.PostQuitMessage(0)
            return 0
        return user.DefWindowProcW(hwnd, message, wp, lp)
    callback = procedure(handle)
    kernel.GetModuleHandleW.argtypes, kernel.GetModuleHandleW.restype = [w.LPCWSTR], w.HMODULE
    module = kernel.GetModuleHandleW(None)
    name = 'PLUMAOwnedProcessFixture' + str(os.getpid())
    definition = WindowClass(0, callback, 0, 0, module, None, None, None, None, name)
    user.RegisterClassW.argtypes, user.RegisterClassW.restype = [c.POINTER(WindowClass)], w.ATOM
    if not user.RegisterClassW(c.byref(definition)):
        raise c.WinError()
    user.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, c.c_int, c.c_int,
        c.c_int, c.c_int, w.HWND, w.HANDLE, w.HINSTANCE, c.c_void_p]
    user.CreateWindowExW.restype = w.HWND
    hwnd = user.CreateWindowExW(0, name, 'PLUMA owned hidden fixture', 0x00CF0000, 0, 0, 100, 100,
        None, None, module, None)
    if not hwnd:
        raise c.WinError()
    marker.write_text(json.dumps({'pid': os.getpid(), 'hwnd': hwnd}), encoding='utf-8')
    user.GetMessageW.argtypes, user.GetMessageW.restype = [c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT], w.BOOL
    user.TranslateMessage.argtypes = [c.POINTER(w.MSG)]
    user.DispatchMessageW.argtypes, user.DispatchMessageW.restype = [c.POINTER(w.MSG)], c.c_ssize_t
    message = w.MSG()
    while True:
        status = user.GetMessageW(c.byref(message), None, 0, 0)
        if status == -1:
            raise c.WinError()
        if status == 0:
            return
        user.TranslateMessage(c.byref(message))
        user.DispatchMessageW(c.byref(message))


if __name__ == '__main__':
    main()
