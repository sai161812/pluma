"""tests/unit/test_phase13_5_stage_i_packaging.py — Stage I Packaging regression tests."""

from __future__ import annotations

import importlib
from pathlib import Path
import pytest

from pluma.config.loader import load_config


def test_stage_i_defaults_yaml_loading() -> None:
    """Gate I: Verify defaults.yaml is bundled and loads cleanly into configuration dictionary."""
    config = load_config()
    assert isinstance(config, dict)
    assert "runtime" in config
    assert "brain" in config
    assert "voice" in config
    assert "perception" in config
    assert "policy" in config

    # Specific baseline values
    assert config["runtime"]["model_idle_unload_seconds"] == 30
    assert config["perception"]["snapshot_ttl_seconds"] == 3.0


def test_stage_i_entry_point_importability() -> None:
    """Gate I: Verify pluma.app entry point main is callable."""
    app_module = importlib.import_module("pluma.app")
    assert hasattr(app_module, "main")
    assert callable(app_module.main)
    assert hasattr(app_module, "PlumaApplicationRuntime")
