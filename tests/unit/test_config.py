"""tests.unit.test_config — Configuration loading tests."""

from __future__ import annotations

import os
import json
import tempfile
import pytest
from pathlib import Path


class TestConfigLoading:
    def test_load_defaults_without_user_override(self) -> None:
        from pluma.config.loader import load_config
        # Ensure no user config interferes.
        env_bak = os.environ.pop("PLUMA_CONFIG", None)
        try:
            config = load_config()
            assert isinstance(config, dict)
            assert "agent" in config
        finally:
            if env_bak is not None:
                os.environ["PLUMA_CONFIG"] = env_bak

    def test_env_var_override_merges(self, tmp_path: Path) -> None:
        from pluma.config.loader import load_config, get
        override = {"agent": {"max_plan_steps": 4}}
        override_file = tmp_path / "test_settings.json"
        override_file.write_text(json.dumps(override), encoding="utf-8")
        os.environ["PLUMA_CONFIG"] = str(override_file)
        try:
            config = load_config()
            assert get(config, "agent", "max_plan_steps") == 4
            # Other keys should still be present from defaults.
            assert get(config, "voice", "required") is True
        finally:
            del os.environ["PLUMA_CONFIG"]

    def test_get_helper_returns_default_for_missing(self) -> None:
        from pluma.config.loader import get
        config = {"a": {"b": 1}}
        assert get(config, "a", "b") == 1
        assert get(config, "a", "missing", default=42) == 42
        assert get(config, "totally_absent", default="x") == "x"

    def test_stop_config_matches_spec(self) -> None:
        from pluma.config.loader import load_config, get
        config = load_config()
        assert get(config, "stop", "block_new_steps_immediately") is True
        assert get(config, "stop", "rollback_reversible_actions") is True
        assert get(config, "stop", "touch_preexisting_user_apps") is False
