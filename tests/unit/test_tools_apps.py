"""tests.unit.test_tools_apps — Unit and verification tests for App tools."""

import sys
import time
import pytest

from pluma.tools.apps import (
    execute_app_status,
    execute_close_app,
    execute_list_apps,
    execute_open_app,
)
from pluma.tools.registry import ToolRegistry, register_default_tools


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_list_apps_and_app_status() -> None:
    res = execute_list_apps({})
    assert res.ok is True
    assert res.verified is True
    assert "count" in res.data
    assert res.data["count"] > 0

    # Query status of python executable
    res_stat = execute_app_status({"app_name": "python"})
    assert res_stat.ok is True
    assert res_stat.verified is True


def test_open_and_close_fixture_app() -> None:
    # 1. Verify forbidden executables (python, cmd, powershell) are rejected per risk policy
    forbidden_res = execute_open_app({
        "app_name": sys.executable,
        "arguments": ["tests/fixtures/fixture_app.py", "spin"],
    })
    assert forbidden_res.ok is False
    assert "forbidden" in forbidden_res.error.lower()

    # 2. Open standard app (e.g. notepad.exe on Windows)
    if sys.platform == "win32":
        open_res = execute_open_app({
            "app_name": "notepad.exe",
            "arguments": [],
        })
        assert open_res.ok is True
        assert open_res.verified is True
        assert "pid" in open_res.data
        pid = open_res.data["pid"]

        try:
            # Check app status
            stat_res = execute_app_status({"app_name": "notepad"})
            assert stat_res.ok is True
            assert stat_res.data["running"] is True

            # Close the app
            close_res = execute_close_app({"app_name": "notepad", "force": True})
            assert close_res.ok is True
            assert close_res.verified is True

            # Verify it's not running
            time.sleep(0.3)
            stat_after = execute_app_status({"app_name": "notepad"})
            assert stat_after.data["running"] is False
        finally:
            import subprocess
            try:
                subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
            except Exception:
                pass
