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
from typing import Any, Optional, Sequence

from pluma.config.paths import PlumaPaths, set_paths
from pluma.core.recovery import CrashRecoveryManager, CrashRecoveryResult
from pluma.core.resident import ResidentCore

__version__ = "0.1.0"
logger = logging.getLogger("pluma")


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

    # 4. Initialize and start Resident Core
    core = ResidentCore()
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
        core.stop()
        logger.info("PLUMA shutdown cleanly.")
        shutdown_logging()

    return 0


def main() -> None:
    """Console script entry point."""
    sys.exit(run_app())


if __name__ == "__main__":
    main()
