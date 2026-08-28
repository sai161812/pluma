"""conftest.py — Global test configuration for PLUMA.

Applies environment flags that activate test-safe backends:
  - PLUMA_EMULATE_AUDIO=1: Use mock audio state instead of pycaw hardware.
    Required for CI and any machine without audio devices or pycaw installed.
    Production code paths remain fail-closed when this variable is NOT set.

The audio emulation flag is explicitly set here so that:
1. Every test module does not need to set it individually.
2. The production code paths remain honest (fail-closed) when the flag is absent.
3. Tests that specifically probe fail-closed behavior can monkeypatch the env to unset it.
"""

import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def enable_audio_emulation_for_tests() -> None:
    """Activate mock audio backend for the entire test session.

    This ensures unit and integration tests that route through audio tools
    (mute, unmute, set_volume, get_volume_status) succeed without real
    audio hardware or pycaw installed.

    Tests that specifically verify fail-closed behavior (test_phase13_5_regression.py)
    use monkeypatch to unset PLUMA_EMULATE_AUDIO within their own scope.
    """
    os.environ["PLUMA_EMULATE_AUDIO"] = "1"
    os.environ["PLUMA_TEST_MODE"] = "1"
    yield
    # Restore: remove the flag after the test session
    os.environ.pop("PLUMA_EMULATE_AUDIO", None)
    os.environ.pop("PLUMA_TEST_MODE", None)

