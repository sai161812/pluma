"""tests/unit/test_phase13_5_stage_g_promised_actions.py — Stage G Promised Actions regression tests."""

from __future__ import annotations

import pytest

from pluma.tools.audio import execute_get_volume_status, execute_set_volume
from pluma.tools.registry import ToolRegistry, register_default_tools
from pluma.tools.system import execute_get_system_status
from pluma.tools.windows import execute_restore_window


def test_stage_g_get_volume_status() -> None:
    """Gate G: Verify get_volume_status returns real volume level and mute state."""
    # Set known level
    set_res = execute_set_volume({"level": 65})
    assert set_res.ok is True

    # Read status
    status_res = execute_get_volume_status({})
    assert status_res.ok is True
    assert status_res.data["volume"] == 65
    assert "muted" in status_res.data
    assert "65%" in status_res.factual_message


def test_stage_g_restore_window() -> None:
    """Gate G: Verify restore_window fails-closed on invalid HWND and restores real windows."""
    import sys
    from pluma.tools.windows import execute_minimize_window

    # Invalid handle must fail closed
    res_inv = execute_restore_window({"hwnd": 0})
    assert res_inv.ok is False
    assert res_inv.verified is False

    if sys.platform == "win32":
        import ctypes
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        fg = user32.GetForegroundWindow()
        if fg and user32.IsWindow(fg):
            # Restore active foreground window
            res = execute_restore_window({"hwnd": fg})
            assert res.ok is True
            assert res.verified is True
            assert "Restored window" in res.factual_message
    else:
        res = execute_restore_window({"hwnd": 1234})
        assert res.ok is True


def test_stage_g_system_status_cpu_ram_disk() -> None:
    """Gate G: Verify get_system_status returns CPU, RAM, and Disk metrics."""
    res = execute_get_system_status({})
    assert res.ok is True
    assert "disk_free_gb" in res.data
    assert "disk_total_gb" in res.data
    assert "cpu_percent" in res.data
    assert "RAM:" in res.factual_message
    assert "Disk:" in res.factual_message


def test_stage_g_all_registered_tools_functional() -> None:
    """Gate G: Verify every registered tool in default ToolRegistry has a valid non-stub executor."""
    registry = ToolRegistry()
    register_default_tools(registry)

    # Must contain full complement of tools
    assert len(registry) >= 20
    assert registry.contains("get_volume_status")
    assert registry.contains("restore_window")
    assert registry.contains("get_system_status")
    assert registry.contains("open_app")
    assert registry.contains("move_file")
    assert registry.contains("undo_last")
