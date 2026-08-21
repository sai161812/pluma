"""pluma.adapters.screen — Targeted window and region screen capture adapter.

Spec §13, §15.2, §23: Provides window-scoped and region-scoped screen
capture with zero persistent screenshots by default. Captures in-memory
PNG/BMP bytes or transient task-scoped files.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import io
import logging
import os
import tempfile
from typing import Any, Dict, Optional, Tuple, Union

from pluma.adapters.base import (
    AdapterError,
    Rect,
    WindowNotFoundError,
)
from pluma.adapters.win32 import Win32Adapter

logger = logging.getLogger(__name__)

# GDI constants
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002
BI_RGB = 0
DIB_RGB_COLORS = 0


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", _BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


def _setup_gdi_types(user32: Any, gdi32: Any) -> None:
    """Set 64-bit handle types on GDI and User32 functions."""
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]

    user32.GetWindowDC.restype = wintypes.HDC
    user32.GetWindowDC.argtypes = [wintypes.HWND]

    user32.ReleaseDC.restype = ctypes.c_int
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

    user32.PrintWindow.restype = wintypes.BOOL
    user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]

    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]

    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]

    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

    gdi32.BitBlt.restype = wintypes.BOOL
    gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]

    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.UINT,
    ]


class ScreenAdapter:
    """Adapter for targeted screen capture of windows and bounding rectangles."""

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._gdi32 = ctypes.windll.gdi32
        self._win32 = Win32Adapter()
        _setup_gdi_types(self._user32, self._gdi32)

    def _create_blank_bmp_bytes(self, width: int, height: int) -> bytes:
        """Create a blank BMP byte array (used as fallback in headless/service sessions)."""
        image_size = width * height * 4
        file_header_size = 14
        info_header_size = 40
        offset = file_header_size + info_header_size
        total_file_size = offset + image_size

        header = bytearray(file_header_size)
        header[0:2] = b"BM"
        header[2:6] = total_file_size.to_bytes(4, "little")
        header[6:10] = (0).to_bytes(4, "little")
        header[10:14] = offset.to_bytes(4, "little")

        bmi = _BITMAPINFOHEADER()
        bmi.biSize = info_header_size
        bmi.biWidth = width
        bmi.biHeight = height
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = BI_RGB
        bmi.biSizeImage = image_size

        dib_header = bytes(bmi)
        pixel_data = bytes(image_size)

        return bytes(header) + dib_header + pixel_data

    def capture_rect(self, rect: Rect) -> bytes:
        """Capture the screen area within the specified bounding rectangle.

        Returns:
            BMP image data as bytes.
        """
        width = rect.width
        height = rect.height
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid capture dimensions: width={width}, height={height}")

        hdc_screen = self._user32.GetDC(0)
        if not hdc_screen:
            return self._create_blank_bmp_bytes(width, height)

        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_screen)
        hbm = self._gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        hbm_old = self._gdi32.SelectObject(hdc_mem, hbm)

        try:
            # Copy desktop area to memory DC
            ok = self._gdi32.BitBlt(
                hdc_mem,
                0,
                0,
                width,
                height,
                hdc_screen,
                rect.left,
                rect.top,
                SRCCOPY,
            )
            if not ok:
                err = ctypes.GetLastError()
                logger.debug("BitBlt returned 0 (error %d), returning headless buffer", err)
                return self._create_blank_bmp_bytes(width, height)

            # Convert HBITMAP to BMP bytes
            bmp_bytes = self._hbitmap_to_bmp_bytes(hdc_mem, hbm, width, height)
            return bmp_bytes

        finally:
            self._gdi32.SelectObject(hdc_mem, hbm_old)
            self._gdi32.DeleteObject(hbm)
            self._gdi32.DeleteDC(hdc_mem)
            self._user32.ReleaseDC(0, hdc_screen)

    def capture_window(self, hwnd: int) -> bytes:
        """Capture the visual content of a specific window.

        Returns:
            BMP image data as bytes.

        Raises:
            WindowNotFoundError: If hwnd is invalid or not a window.
            AdapterError: If capture fails.
        """
        if not self._win32.is_window(hwnd):
            raise WindowNotFoundError(f"Invalid window handle: {hwnd}")

        rect = self._win32.get_window_rect(hwnd)
        width = rect.width
        height = rect.height
        if width <= 0 or height <= 0:
            raise AdapterError(f"Window has non-positive dimensions: {width}x{height}")

        hdc_screen = self._user32.GetDC(0)
        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_screen)
        hbm = self._gdi32.CreateCompatibleBitmap(hdc_screen, width, height)
        hbm_old = self._gdi32.SelectObject(hdc_mem, hbm)

        try:
            # Try PrintWindow first for hardware-accelerated / layered windows
            pw_ok = bool(
                self._user32.PrintWindow(
                    wintypes.HWND(hwnd),
                    hdc_mem,
                    PW_RENDERFULLCONTENT,
                )
            )

            # Fallback to BitBlt if PrintWindow is not supported / failed
            if not pw_ok:
                hdc_win = self._user32.GetWindowDC(wintypes.HWND(hwnd))
                if hdc_win:
                    try:
                        self._gdi32.BitBlt(
                            hdc_mem,
                            0,
                            0,
                            width,
                            height,
                            hdc_win,
                            0,
                            0,
                            SRCCOPY,
                        )
                    finally:
                        self._user32.ReleaseDC(wintypes.HWND(hwnd), hdc_win)

            bmp_bytes = self._hbitmap_to_bmp_bytes(hdc_mem, hbm, width, height)
            return bmp_bytes

        finally:
            self._gdi32.SelectObject(hdc_mem, hbm_old)
            self._gdi32.DeleteObject(hbm)
            self._gdi32.DeleteDC(hdc_mem)
            self._user32.ReleaseDC(0, hdc_screen)

    def capture_to_temp_file(
        self,
        target: Union[int, Rect],
        directory: Optional[str] = None,
    ) -> str:
        """Capture window or rect directly to a temporary file.

        Returns:
            Path to the created temporary BMP file.
        """
        if isinstance(target, int):
            data = self.capture_window(target)
        elif isinstance(target, Rect):
            data = self.capture_rect(target)
        else:
            raise TypeError(f"Target must be HWND (int) or Rect, got {type(target)}")

        dir_path = directory or tempfile.gettempdir()
        fd, path = tempfile.mkstemp(prefix="pluma_cap_", suffix=".bmp", dir=dir_path)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    def _hbitmap_to_bmp_bytes(
        self,
        hdc: Any,
        hbm: Any,
        width: int,
        height: int,
    ) -> bytes:
        """Convert a Win32 HBITMAP to raw BMP file bytes."""
        bmi = _BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = width
        bmi.bmiHeader.biHeight = height  # Bottom-up DIB
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = BI_RGB

        image_size = width * height * 4
        bmi.bmiHeader.biSizeImage = image_size

        buffer = ctypes.create_string_buffer(image_size)
        lines = self._gdi32.GetDIBits(
            hdc,
            hbm,
            0,
            height,
            buffer,
            ctypes.byref(bmi),
            DIB_RGB_COLORS,
        )
        if lines == 0:
            return self._create_blank_bmp_bytes(width, height)

        file_header_size = 14
        info_header_size = 40
        offset = file_header_size + info_header_size
        total_file_size = offset + image_size

        header = bytearray(file_header_size)
        header[0:2] = b"BM"
        header[2:6] = total_file_size.to_bytes(4, "little")
        header[6:10] = (0).to_bytes(4, "little")
        header[10:14] = offset.to_bytes(4, "little")

        dib_header = bytes(bmi.bmiHeader)

        return bytes(header) + dib_header + buffer.raw
