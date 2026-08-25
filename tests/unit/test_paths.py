"""tests/unit/test_paths.py — Unit tests for PlumaPaths and directory hierarchy."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from pluma.config.paths import PlumaPaths, get_paths, set_paths


def test_default_paths_resolution() -> None:
    """Verify default paths resolution for local and roaming data."""
    paths = PlumaPaths()
    assert paths.local_root is not None
    assert paths.roaming_root is not None
    assert paths.db_path.name == "pluma.db"
    assert paths.user_settings_path.name == "user_settings.json"
    assert paths.llm_models_dir.name == "llm"
    assert paths.whisper_models_dir.name == "whisper"
    assert paths.ocr_models_dir.name == "ocr"


def test_custom_paths_and_directory_creation() -> None:
    """Verify that PlumaPaths creates all directory structures under a custom root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        local_root = Path(temp_dir) / "LocalPluma"
        roaming_root = Path(temp_dir) / "RoamingPluma"

        paths = PlumaPaths(local_app_data=local_root, roaming_app_data=roaming_root)
        paths.ensure_directories()

        assert paths.data_dir.exists()
        assert paths.models_dir.exists()
        assert paths.llm_models_dir.exists()
        assert paths.whisper_models_dir.exists()
        assert paths.ocr_models_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.cache_dir.exists()
        assert paths.temp_dir.exists()
        assert paths.roaming_root.exists()


def test_task_temp_dir_naming() -> None:
    """Verify task-isolated scratch space directory naming and safety."""
    paths = PlumaPaths(local_app_data=tempfile.gettempdir())
    t_dir = paths.task_temp_dir("test-task-123")
    assert "task_test-task-123" in str(t_dir)


def test_environment_variable_overrides() -> None:
    """Verify that environment variables override default paths."""
    with tempfile.TemporaryDirectory() as custom_data:
        os.environ["PLUMA_DATA_DIR"] = custom_data
        try:
            paths = PlumaPaths()
            assert paths.data_dir == Path(custom_data)
            assert paths.db_path == Path(custom_data) / "pluma.db"
        finally:
            del os.environ["PLUMA_DATA_DIR"]
