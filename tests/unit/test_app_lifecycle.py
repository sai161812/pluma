"""tests/unit/test_app_lifecycle.py — Unit tests for application entry point and host lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from pluma.app import run_app, setup_logging, shutdown_logging
from pluma.config.paths import PlumaPaths


def test_app_recover_only_mode() -> None:
    """Verify that running pluma with --recover-only executes recovery and exits with code 0."""
    with tempfile.TemporaryDirectory() as temp_dir:
        local_root = str(Path(temp_dir) / "LocalPluma")
        roaming_root = str(Path(temp_dir) / "RoamingPluma")

        argv = [
            "--recover-only",
            "--local-app-data", local_root,
            "--roaming-app-data", roaming_root,
        ]

        try:
            exit_code = run_app(argv)
            assert exit_code == 0

            # Verify directories were created
            paths = PlumaPaths(local_app_data=local_root, roaming_app_data=roaming_root)
            assert paths.data_dir.exists()
            assert paths.logs_dir.exists()
        finally:
            shutdown_logging()


def test_setup_logging_creates_log_file() -> None:
    """Verify that setup_logging configures file logger and creates pluma.log."""
    with tempfile.TemporaryDirectory() as temp_dir:
        logs_dir = Path(temp_dir) / "logs"
        try:
            setup_logging(logs_dir=logs_dir, debug=True)

            import logging
            test_logger = logging.getLogger("pluma.test")
            test_logger.info("Test log message for lifecycle verification.")

            log_file = logs_dir / "pluma.log"
            assert log_file.exists()
            content = log_file.read_text(encoding="utf-8")
            assert "Test log message for lifecycle verification." in content
        finally:
            shutdown_logging()
