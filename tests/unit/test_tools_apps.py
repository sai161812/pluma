"""tests.unit.test_tools_apps — Unit and verification tests for App tools."""

import sys
import time
import os
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
    from pluma.core.ownership import get_process_creation_time
    res_stat = execute_app_status({'pid': os.getpid(), 'creation_time': get_process_creation_time(os.getpid())})
    assert res_stat.ok is True
    assert res_stat.verified is True


@pytest.mark.parametrize('name', ['cmd', 'powershell', sys.executable, 'unknown.exe'])
def test_unregistered_launch_rejected_before_execution(registry, name):
    from pluma.tools.registry import ToolArgumentError
    with pytest.raises(ToolArgumentError): registry.validate_call('open_app', {'app_name': name})


def test_direct_launch_without_owned_journal_refuses():
    result = execute_open_app({'app_name': 'notepad', 'arguments': []})
    assert not result.ok and not result.verified and result.error_code == 'APP_LAUNCH_UNVERIFIED'


# Positive native open, status/ownership and close/undo assertions now live in
# test_app_launch_native.py and test_app_close_native.py on owned private-desktop
# fixtures. No direct Notepad launch or raw-PID taskkill against user apps.
