"""tests.unit.test_adapters_powershell — Unit tests for PowerShellAdapter."""

import pytest

from pluma.adapters.base import (
    AccessDeniedError,
    AdapterError,
    AdapterTimeoutError,
)
from pluma.adapters.powershell import PowerShellAdapter, PowerShellResult
from pluma.core.cancellation import CancellationToken


def test_powershell_simple_execution() -> None:
    """Verify basic echo command execution and output capture."""
    adapter = PowerShellAdapter()
    res = adapter.run("Write-Output 'PLUMA_TEST_OK'")
    assert isinstance(res, PowerShellResult)
    assert res.exit_code == 0
    assert "PLUMA_TEST_OK" in res.stdout
    assert res.duration_ms > 0
    assert not res.timed_out


def test_powershell_exit_code() -> None:
    """Verify non-zero exit codes are captured."""
    adapter = PowerShellAdapter()
    res = adapter.run("exit 42")
    assert res.exit_code == 42


def test_powershell_timeout() -> None:
    """Verify hard timeout triggers AdapterTimeoutError."""
    adapter = PowerShellAdapter()
    with pytest.raises(AdapterTimeoutError) as exc_info:
        adapter.run("Start-Sleep -Seconds 5", timeout_s=0.5)
    assert "timed out" in exc_info.value.message.lower()


def test_powershell_cancelled_token() -> None:
    """Verify pre-cancelled token aborts execution immediately."""
    adapter = PowerShellAdapter()
    token = CancellationToken()
    token.cancel()
    with pytest.raises(AdapterError) as exc_info:
        adapter.run("Write-Output 'should not run'", token=token)
    assert "cancellation" in exc_info.value.message.lower()


def test_powershell_access_denied_mapping() -> None:
    """Verify permission denial strings map to AccessDeniedError."""
    adapter = PowerShellAdapter()
    # Simulate an access denied error via stderr output and exit code
    with pytest.raises(AccessDeniedError):
        adapter.run("[Console]::Error.WriteLine('Access is denied.'); exit 1")
