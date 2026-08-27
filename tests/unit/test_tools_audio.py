"""tests.unit.test_tools_audio — Unit and verification tests for Audio tools."""

import os

import pytest

from pluma.tools.audio import (
    execute_mute,
    execute_set_volume,
    execute_unmute,
    undo_builder_mute,
    undo_builder_set_volume,
)
from pluma.tools.registry import ToolRegistry, register_default_tools


@pytest.fixture(autouse=True)
def enable_audio_emulation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Activate mock audio backend for all tests in this module via explicit env flag."""
    monkeypatch.setenv("PLUMA_EMULATE_AUDIO", "1")


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_set_volume_and_undo() -> None:
    undo_data = undo_builder_set_volume({"level": 40})
    assert undo_data is not None
    assert "previous_volume" in undo_data

    res = execute_set_volume({"level": 40})
    assert res.ok is True
    assert res.verified is True
    assert res.data["target_level"] == 40


def test_mute_and_unmute() -> None:
    undo_data = undo_builder_mute({})
    assert undo_data is not None

    res_mute = execute_mute({})
    assert res_mute.ok is True
    assert res_mute.verified is True
    assert res_mute.data["muted"] is True

    res_unmute = execute_unmute({})
    assert res_unmute.ok is True
    assert res_unmute.verified is True
    assert res_unmute.data["muted"] is False
