"""pluma.app — Production entry point and resident process host.

Spec §20, §25:
- Windows startup launches only the resident core. LLM/STT/OCR workers are never startup services.
- On startup, mark any previously RUNNING/STOPPING task as ABORTED_BY_CRASH.
- Inspect recorded temp resources and clean only resources whose PLUMA ownership can be verified.
- Clean shutdown terminates task Job Objects and releases IPC handles.
"""

from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import time
from typing import Any, Dict, Optional, Sequence

from pluma.config.loader import get, load_config
from pluma.config.paths import PlumaPaths, set_paths
from pluma.core.orchestrator import Orchestrator
from pluma.core.ownership import OwnershipRegistry
from pluma.core.recovery import CrashRecoveryManager, CrashRecoveryResult
from pluma.core.resident import ResidentCore
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection
from pluma.policy.engine import PolicyEngine
from pluma.policy.rules import PolicyRules
from pluma.rollback.engine import RollbackEngine
from pluma.tools.registry import ToolRegistry, register_default_tools
from pluma.ui.confirmations import ConfirmationContract
from pluma.voice.pipeline import VoicePipeline

__version__ = "0.1.0"
logger = logging.getLogger("pluma")


class PlumaApplicationRuntime:
    """Encapsulates the single cohesive runtime dependency graph for PLUMA."""

    def __init__(
        self,
        paths: PlumaPaths,
        config: Optional[Dict[str, Any]] = None,
        confirmation_contract: Optional[ConfirmationContract] = None,
        db_connection: Optional[DbConnection] = None,
    ) -> None:
        self.paths = paths
        self.config = config or load_config()
        self.db = db_connection or DbConnection(str(paths.db_path))
        if not self.db.is_open:
            self.db.open()

        self.ledger = ActivityLedger(db=self.db)
        self.ownership_registry = OwnershipRegistry(db_conn=self.db)
        self.supervisor = TaskSupervisor(
            ledger=self.ledger,
            ownership_registry=self.ownership_registry,
        )
        self.policy_rules = PolicyRules()
        self.policy_engine = PolicyEngine(
            rules=self.policy_rules,
            confirmation_contract=confirmation_contract,
        )
        self.tool_registry = ToolRegistry(policy_engine=self.policy_engine)
        register_default_tools(self.tool_registry)

        self.rollback_engine = RollbackEngine(ledger=self.ledger)
        self.router = Router()

        # Model & Planner Lifecycles (Zero-ML at startup; auto-unloaded on idle)
        model_name = get(self.config, "brain", "model_name", default="qwen3-4b.gguf")
        model_path = get(self.config, "brain", "model_path", default=str(paths.models_dir / model_name))
        idle_seconds = float(get(self.config, "brain", "idle_unload_seconds", default=30.0))

        from pluma.brain.lifecycle import LlmLifecycleManager
        self.llm_lifecycle = LlmLifecycleManager(
            model_path=model_path,
            registry=self.tool_registry,
            idle_unload_seconds=idle_seconds,
        )

        self.orchestrator = Orchestrator(
            registry=self.tool_registry,
            supervisor=self.supervisor,
            ledger=self.ledger,
            router=self.router,
            llm_manager=self.llm_lifecycle,
            rollback_engine=self.rollback_engine,
        )

        stt_model_name = get(self.config, "voice", "model_name", default="base.en.pt")
        stt_model_path = get(self.config, "voice", "model_path", default=str(paths.models_dir / stt_model_name))
        stt_idle = float(get(self.config, "voice", "idle_unload_seconds", default=30.0))

        from pluma.voice.lifecycle import VoiceLifecycleManager
        self.voice_lifecycle = VoiceLifecycleManager(
            model_path=stt_model_path,
            idle_unload_seconds=stt_idle,
        )
        self.voice_pipeline = VoicePipeline(lifecycle_manager=self.voice_lifecycle)

        self.resident_core = ResidentCore(
            config=self.config,
            voice_pipeline=self.voice_pipeline,
            supervisor=self.supervisor,
            orchestrator=self.orchestrator,
            ledger=self.ledger,
            ownership_registry=self.ownership_registry,
        )

    def close(self) -> None:
        """Close resident core and database connection cleanly."""
        try:
            self.resident_core.stop()
        except Exception:
            pass
        try:
            self.llm_lifecycle.shutdown()
        except Exception:
            pass
        try:
            self.voice_lifecycle.shutdown()
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass


def setup_logging(logs_dir: Path, debug: bool = False) -> None:
    """Configure structured logging with console output and rotating file log."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / "pluma.log"

    level = logging.DEBUG if debug else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler
    console_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # Rotating file handler (5MB max per file, up to 3 backups)
    try:
        file_formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d [%(levelname)s] [%(threadName)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)
    except Exception as exc:
        print(f"Warning: Failed to initialize file logger at {log_file}: {exc}", file=sys.stderr)


def shutdown_logging() -> None:
    """Flush and close all logging handlers to release file locks."""
    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        try:
            h.flush()
            h.close()
        except Exception:
            pass
        root_logger.removeHandler(h)


def run_app(argv: Optional[Sequence[str]] = None) -> int:
    """Main execution function for the PLUMA resident host."""
    parser = argparse.ArgumentParser(
        prog="pluma",
        description="PLUMA — Local Voice & OS-Automation Resident Core",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--recover-only", action="store_true", help="Run crash recovery reconciliation and exit")
    parser.add_argument("--config", type=str, default=None, help="Path to custom user configuration file")
    parser.add_argument("--local-app-data", type=str, default=None, help="Override %LOCALAPPDATA% directory")
    parser.add_argument("--roaming-app-data", type=str, default=None, help="Override %APPDATA% directory")

    args = parser.parse_args(argv)

    # 1. Initialize paths and directory hierarchy
    paths = PlumaPaths(
        local_app_data=args.local_app_data,
        roaming_app_data=args.roaming_app_data,
    )
    set_paths(paths)
    paths.ensure_directories()

    # 2. Configure logging
    setup_logging(paths.logs_dir, debug=args.debug)
    logger.info("Starting PLUMA v%s (PID: %d)", __version__, os.getpid())
    logger.info("Storage root: %s", paths.local_root)

    # 3. Startup Crash Recovery & State Reconciliation
    recovery_mgr = CrashRecoveryManager(paths=paths)
    recovery_res: CrashRecoveryResult = recovery_mgr.reconcile_startup()

    if recovery_res.stale_tasks_recovered > 0:
        logger.warning(
            "Crash Recovery reconciled %d interrupted tasks.",
            recovery_res.stale_tasks_recovered,
        )

    if args.recover_only:
        logger.info("Recovery-only mode completed successfully. Exiting.")
        shutdown_logging()
        return 0

    # 4. Initialize and start Production Runtime Dependency Graph
    custom_cfg = load_config(args.config) if args.config else None
    runtime = PlumaApplicationRuntime(paths=paths, config=custom_cfg)
    core = runtime.resident_core

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %d. Initiating clean shutdown...", signum)
        stop_event.set()

    # Register OS termination signals
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    core.start()
    logger.info("PLUMA Resident Core active and listening (Hotkeys & Named Pipe IPC ready).")

    # 5. Main loop
    try:
        while not stop_event.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    finally:
        logger.info("Stopping Resident Core and releasing resources...")
        runtime.close()
        logger.info("PLUMA shutdown cleanly.")
        shutdown_logging()

    return 0


def main() -> None:
    """Console script entry point."""
    sys.exit(run_app())


if __name__ == "__main__":
    main()
