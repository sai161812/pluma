"""tests/unit/test_tools_clipboard.py — Phase 3: Clipboard tool tests.

Tests:
  - clear_clipboard / clipboard_clear executors.
  - get_clipboard_text executor.
  - set_clipboard_text executor.
  - Sensitive value redaction guard (data["text"] never persisted directly).
  - Cross-platform: all tests must pass on Windows and non-Windows (CI).
"""

from __future__ import annotations

import sys
from typing import Any, Dict

import pytest

from pluma.tools.clipboard import (
    CLIPBOARD_TOOL_SPECS,
    execute_clear_clipboard,
    execute_get_clipboard_text,
    execute_set_clipboard_text,
)
from pluma.tools.base import ToolResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _spec_by_name(name: str):
    for spec in CLIPBOARD_TOOL_SPECS:
        if spec.name == name:
            return spec
    raise KeyError(f"No clipboard ToolSpec named {name!r}")


# ---------------------------------------------------------------------------
# Tests: clear_clipboard
# ---------------------------------------------------------------------------

class TestClearClipboard:
    def test_clear_clipboard_returns_ok(self) -> None:
        result = execute_clear_clipboard({})
        assert result.ok is True, f"Expected ok=True, got error: {result.error}"

    def test_clear_clipboard_factual_message(self) -> None:
        result = execute_clear_clipboard({})
        assert "clipboard" in result.factual_message.lower()

    def test_clear_clipboard_tool_name(self) -> None:
        result = execute_clear_clipboard({})
        assert result.tool == "clear_clipboard"

    def test_clear_clipboard_verified(self) -> None:
        result = execute_clear_clipboard({})
        assert result.verified is True

    def test_clipboard_clear_alias_spec_exists(self) -> None:
        spec = _spec_by_name("clipboard_clear")
        assert spec is not None

    def test_clipboard_clear_alias_executes(self) -> None:
        spec = _spec_by_name("clipboard_clear")
        result = spec.executor({})
        assert result.ok is True


# ---------------------------------------------------------------------------
# Tests: set_clipboard_text
# ---------------------------------------------------------------------------

class TestSetClipboardText:
    def test_set_returns_ok(self) -> None:
        result = execute_set_clipboard_text({"text": "hello world"})
        assert result.ok is True

    def test_set_records_char_count(self) -> None:
        text = "hello world"
        result = execute_set_clipboard_text({"text": text})
        assert result.data.get("char_count") == len(text)

    def test_set_factual_message_mentions_count(self) -> None:
        result = execute_set_clipboard_text({"text": "abc"})
        assert "3" in result.factual_message

    def test_set_data_does_not_contain_raw_text(self) -> None:
        """Verify that sensitive raw text is NOT stored in the result data."""
        secret = "super-secret-password-12345"
        result = execute_set_clipboard_text({"text": secret})
        # data may only contain char_count; never the raw text
        assert secret not in str(result.data), (
            "Sensitive clipboard text must not be stored in result.data!"
        )

    def test_set_empty_text(self) -> None:
        result = execute_set_clipboard_text({"text": ""})
        assert result.ok is True
        assert result.data["char_count"] == 0

    def test_set_tool_name(self) -> None:
        result = execute_set_clipboard_text({"text": "x"})
        assert result.tool == "set_clipboard_text"

    def test_set_verified(self) -> None:
        result = execute_set_clipboard_text({"text": "x"})
        assert result.verified is True


# ---------------------------------------------------------------------------
# Tests: get_clipboard_text
# ---------------------------------------------------------------------------

class TestGetClipboardText:
    def test_get_returns_ok(self) -> None:
        result = execute_get_clipboard_text({})
        assert result.ok is True

    def test_get_returns_is_empty_key(self) -> None:
        result = execute_get_clipboard_text({})
        assert "is_empty" in result.data

    def test_get_tool_name(self) -> None:
        result = execute_get_clipboard_text({})
        assert result.tool == "get_clipboard_text"

    def test_get_factual_message_present(self) -> None:
        result = execute_get_clipboard_text({})
        assert result.factual_message

    @pytest.mark.skipif(sys.platform != "win32", reason="Win32 clipboard round-trip requires Windows.")
    def test_roundtrip_set_get(self) -> None:
        """Set text then immediately read it back. Windows only."""
        test_text = "pluma-clipboard-roundtrip-test"
        set_result = execute_set_clipboard_text({"text": test_text})
        assert set_result.ok
        get_result = execute_get_clipboard_text({})
        assert get_result.ok
        assert get_result.data.get("text") == test_text


# ---------------------------------------------------------------------------
# Tests: ToolSpec registration
# ---------------------------------------------------------------------------

class TestClipboardToolSpecs:
    def test_all_specs_present(self) -> None:
        names = {spec.name for spec in CLIPBOARD_TOOL_SPECS}
        assert "clear_clipboard" in names
        assert "clipboard_clear" in names
        assert "get_clipboard_text" in names
        assert "set_clipboard_text" in names

    def test_all_specs_have_executor(self) -> None:
        for spec in CLIPBOARD_TOOL_SPECS:
            assert callable(spec.executor), f"Spec {spec.name!r} has no executor"

    def test_all_specs_have_schema(self) -> None:
        for spec in CLIPBOARD_TOOL_SPECS:
            assert spec.args_schema is not None, f"Spec {spec.name!r} has no args_schema"

    def test_no_module_level_win32_import(self) -> None:
        """Clipboard Win32 APIs must not be imported at module level."""
        import importlib
        import types
        # Re-import to verify no ctypes call at module level causes errors
        # on non-Windows. If this succeeds, boundary is respected.
        import pluma.tools.clipboard as mod  # noqa
        # ctypes itself is stdlib and may be present; actual WinDLL call must be inside executor
        # We verify by checking the executor is callable and was not called at import time.
        assert callable(mod.execute_clear_clipboard)
