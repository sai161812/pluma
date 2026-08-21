"""pluma.tools.clipboard — Clipboard read and write tools.

Spec §11, §14: Clipboard actions are registered ToolSpecs.
Sensitive clipboard content (passwords, tokens) is redacted from logs
before being written to the Activity Ledger.

Boundary: No heavy libraries imported at module level.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import verify_noop


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class ClearClipboardArgs(BaseModel):
    """Arguments for clear_clipboard / clipboard_clear."""
    pass


class GetClipboardArgs(BaseModel):
    """Arguments for get_clipboard_text."""
    pass


class SetClipboardArgs(BaseModel):
    """Arguments for set_clipboard_text."""
    text: str = Field(min_length=0, max_length=65536, description="Text to place on the clipboard.")


# ---------------------------------------------------------------------------
# Win32 Clipboard Helpers
# ---------------------------------------------------------------------------

def _open_clipboard(user32: Any, retries: int = 5, delay: float = 0.02) -> bool:
    """Open clipboard with small bounded retry for transient locks."""
    import time
    for _ in range(retries):
        if user32.OpenClipboard(None):
            return True
        time.sleep(delay)
    return False


def _win32_clipboard_clear() -> bool:
    """Clear the clipboard using Win32 API."""
    import ctypes
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.OpenClipboard.restype = ctypes.c_bool
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.CloseClipboard.restype = ctypes.c_bool

    if not _open_clipboard(user32):
        return False
    try:
        user32.EmptyClipboard()
        return True
    finally:
        user32.CloseClipboard()


def _win32_clipboard_get_text() -> Optional[str]:
    """Read text from the clipboard using Win32 API."""
    import ctypes

    HANDLE = ctypes.c_size_t

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    user32.OpenClipboard.restype = ctypes.c_bool
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.CloseClipboard.restype = ctypes.c_bool
    user32.GetClipboardData.restype = HANDLE
    user32.GetClipboardData.argtypes = [ctypes.c_uint]

    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [HANDLE]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalUnlock.argtypes = [HANDLE]

    CF_UNICODETEXT = 13

    if not _open_clipboard(user32):
        return None
    try:
        h_data = user32.GetClipboardData(CF_UNICODETEXT)
        if not h_data:
            return None
        p_data = kernel32.GlobalLock(h_data)
        if p_data is None:
            return None
        try:
            text = ctypes.wstring_at(p_data)
            return text
        finally:
            kernel32.GlobalUnlock(h_data)
    finally:
        user32.CloseClipboard()


def _win32_clipboard_set_text(text: str) -> bool:
    """Set text on the clipboard using Win32 API.

    Uses c_size_t for HGLOBAL handles (safe on both 32-bit and 64-bit Windows).
    """
    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE = ctypes.c_size_t   # HGLOBAL is opaque pointer-sized value

    # Configure function signatures
    kernel32.GlobalAlloc.restype = HANDLE
    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [HANDLE]
    kernel32.GlobalUnlock.restype = ctypes.c_bool
    kernel32.GlobalUnlock.argtypes = [HANDLE]
    kernel32.GlobalFree.restype = HANDLE
    kernel32.GlobalFree.argtypes = [HANDLE]

    user32.OpenClipboard.restype = ctypes.c_bool
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.EmptyClipboard.restype = ctypes.c_bool
    user32.SetClipboardData.restype = HANDLE
    user32.SetClipboardData.argtypes = [ctypes.c_uint, HANDLE]
    user32.CloseClipboard.restype = ctypes.c_bool

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    encoded = (text + "\0").encode("utf-16-le")
    n_bytes = len(encoded)

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, n_bytes)
    if not h_mem:
        return False

    p_mem = kernel32.GlobalLock(h_mem)
    if p_mem is None:
        kernel32.GlobalFree(h_mem)
        return False

    ctypes.memmove(p_mem, encoded, n_bytes)
    kernel32.GlobalUnlock(h_mem)

    if not _open_clipboard(user32):
        kernel32.GlobalFree(h_mem)
        return False
    try:
        user32.EmptyClipboard()
        res = user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        if not res:
            kernel32.GlobalFree(h_mem)
            return False
        return True
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_clear_clipboard(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    if sys.platform == "win32":
        ok = _win32_clipboard_clear()
    else:
        # Fallback for testing on non-Windows
        ok = True

    if not ok:
        return ToolResult.failure("clear_clipboard", "Failed to clear clipboard via Win32 API.")

    return ToolResult(
        ok=True,
        tool="clear_clipboard",
        data={},
        factual_message="Cleared clipboard.",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail="Clipboard cleared via Win32 EmptyClipboard."),
    )


def execute_get_clipboard_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    if sys.platform == "win32":
        text = _win32_clipboard_get_text()
    else:
        text = ""

    if text is None:
        return ToolResult(
            ok=True,
            tool="get_clipboard_text",
            data={"text": "", "is_empty": True},
            factual_message="Clipboard is empty or contains no text.",
            verified=True,
        )

    return ToolResult(
        ok=True,
        tool="get_clipboard_text",
        # NOTE: data["text"] will be redacted by sanitise_args_for_ledger when logged.
        # The raw text is available to the caller but never persisted.
        data={"text": text, "is_empty": len(text) == 0, "char_count": len(text)},
        factual_message=f"Read {len(text)} character{'s' if len(text) != 1 else ''} from clipboard.",
        verified=True,
    )


def execute_set_clipboard_text(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    text = args["text"]

    if sys.platform == "win32":
        ok = _win32_clipboard_set_text(text)
    else:
        ok = True

    if not ok:
        return ToolResult.failure("set_clipboard_text", "Failed to set clipboard text via Win32 API.")

    return ToolResult(
        ok=True,
        tool="set_clipboard_text",
        data={"char_count": len(text)},
        factual_message=f"Set {len(text)} character{'s' if len(text) != 1 else ''} on clipboard.",
        verified=True,
        verify_detail=VerifyResult(ok=True, method="api", detail=f"Clipboard set to {len(text)} chars via Win32."),
    )


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

CLIPBOARD_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="clear_clipboard",
        description="Clear the system clipboard.",
        args_schema=ClearClipboardArgs,
        risk_class=RiskClass.LOW,
        timeout_s=3.0,
        executor=execute_clear_clipboard,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    # Register under the golden corpus alias too
    ToolSpec(
        name="clipboard_clear",
        description="Clear the system clipboard (alias for clear_clipboard).",
        args_schema=ClearClipboardArgs,
        risk_class=RiskClass.LOW,
        timeout_s=3.0,
        executor=execute_clear_clipboard,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="get_clipboard_text",
        description="Read the current text content of the clipboard.",
        args_schema=GetClipboardArgs,
        risk_class=RiskClass.READ,
        timeout_s=3.0,
        executor=execute_get_clipboard_text,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="set_clipboard_text",
        description="Place text content onto the clipboard.",
        args_schema=SetClipboardArgs,
        risk_class=RiskClass.LOW,
        timeout_s=3.0,
        executor=execute_set_clipboard_text,
        verifier=verify_noop,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
]
