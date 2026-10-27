"""tests/unit/test_app_lifecycle.py — Unit tests for application entry point and host lifecycle."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from pluma.app import PlumaApplicationRuntime, run_app, setup_logging, shutdown_logging
from pluma.config.paths import PlumaPaths
from pluma.config.loader import load_config


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


def test_runtime_wires_configured_planner_limits_and_model_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        paths = PlumaPaths(
            local_app_data=str(Path(temp_dir) / "LocalPluma"),
            roaming_app_data=str(Path(temp_dir) / "RoamingPluma"),
        )
        config = load_config()
        config["agent"]["max_plan_steps"] = 4
        config["runtime"]["model_idle_unload_seconds"] = 7
        config["brain"]["model_name"] = "planner-fixture.gguf"
        runtime = PlumaApplicationRuntime(paths=paths, config=config)
        try:
            assert runtime.policy_engine.confirmation_contract is runtime.confirmation_broker
            assert runtime.resident_core.confirmation_broker is runtime.confirmation_broker
            assert not runtime.confirmation_broker.is_available
            opened = runtime.resident_core.handle_ipc_command({
                "protocol_version": 1, "message_type": "confirmation_query",
                "request_id": "0aba89fa-dad8-420f-8bd5-37ae8daaa786",
                "client_id": "b88d7081-cf53-471f-aa6c-d84b084a927f",
            })
            assert opened["confirmations"] == [] and runtime.confirmation_broker.is_available
            assert runtime.llm_lifecycle.adapter.max_plan_steps == 4
            assert runtime.llm_lifecycle.idle_unload_seconds == 7
            assert runtime.llm_lifecycle.adapter.model_path == str(
                paths.llm_models_dir / "planner-fixture.gguf"
            )
            settings = runtime.resident_core.handle_ipc_command({
                "protocol_version": 1,
                "message_type": "settings_query",
                "request_id": "9eb00b7f-69f5-4bc1-b6ef-360de5234bc1",
            })
            assert settings["planner_model_path"] == str(paths.llm_models_dir / "planner-fixture.gguf")
            assert settings["stt_model_path"] == str(paths.whisper_models_dir / "ggml-base.en.bin")
        finally:
            runtime.close()
        assert not runtime.confirmation_broker.is_available
        assert runtime.confirmation_broker._clients == {}


def test_runtime_wires_lazy_whisper_model_and_locked_stt_unload_setting() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        paths = PlumaPaths(
            local_app_data=str(Path(temp_dir) / "LocalPluma"),
            roaming_app_data=str(Path(temp_dir) / "RoamingPluma"),
        )
        config = load_config()
        config["voice"]["model_name"] = "fixture-whisper.ggml"
        config["runtime"]["stt_idle_unload_seconds"] = 9
        runtime = PlumaApplicationRuntime(paths=paths, config=config)
        try:
            assert runtime.voice_lifecycle.model_path == str(
                paths.whisper_models_dir / "fixture-whisper.ggml"
            )
            assert runtime.voice_lifecycle.idle_unload_seconds == 9
            assert runtime.voice_lifecycle.adapter._registry is runtime.tool_registry
            assert runtime.voice_lifecycle.state == "COLD"
            assert not runtime.voice_lifecycle.adapter.is_loaded
        finally:
            runtime.close()


def test_runtime_honors_explicit_whisper_model_path() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        paths = PlumaPaths(
            local_app_data=str(Path(temp_dir) / "LocalPluma"),
            roaming_app_data=str(Path(temp_dir) / "RoamingPluma"),
        )
        model_path = str(Path(temp_dir) / "custom-whisper.ggml")
        config = load_config()
        config["voice"]["model_path"] = model_path
        runtime = PlumaApplicationRuntime(paths=paths, config=config)
        try:
            assert runtime.voice_lifecycle.model_path == model_path
            assert runtime.voice_lifecycle.state == "COLD"
            assert not runtime.voice_lifecycle.adapter.is_loaded
        finally:
            runtime.close()
