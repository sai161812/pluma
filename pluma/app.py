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

_CLOSE_INIT_LOCK = threading.Lock()

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
        settings_path: Optional[str] = None,
    ) -> None:
        self.paths = paths
        self.settings_path = str(Path(settings_path or os.environ.get("PLUMA_CONFIG") or paths.user_settings_path).absolute())
        self.config = config or load_config(self.settings_path)
        self.db = db_connection or DbConnection(str(paths.db_path))
        if not self.db.is_open:
            self.db.open()

        self.ledger = ActivityLedger(db=self.db)
        self.ownership_registry = OwnershipRegistry(db_conn=self.db)
        self.rollback_engine = RollbackEngine(ledger=self.ledger)
        self.supervisor = TaskSupervisor(
            ledger=self.ledger,
            ownership_registry=self.ownership_registry,
            rollback_engine=self.rollback_engine,
        )
        self.rollback_engine.task_resolver = self.supervisor.get_task
        self.policy_rules = PolicyRules()
        self.policy_rules.confirm_low_risk = get(self.config,"policy","confirm_low_risk",default=False)
        from pluma.ui.ipc_confirmations import IpcConfirmationBroker
        self.confirmation_broker = (IpcConfirmationBroker(self.supervisor.get_task)
                                    if confirmation_contract is None else
                                    confirmation_contract if isinstance(confirmation_contract, IpcConfirmationBroker) else None)
        self.policy_engine = PolicyEngine(
            rules=self.policy_rules,
            confirmation_contract=confirmation_contract if confirmation_contract is not None else self.confirmation_broker,
            command_catalog_path=str(paths.roaming_root / 'commands.json'),
        )
        self.tool_registry = ToolRegistry(policy_engine=self.policy_engine, stop_service=self.supervisor.request_stop,
                                          settings_path=self.settings_path)
        register_default_tools(self.tool_registry)
        self.rollback_engine.clipboard_inverse = self.tool_registry.restore_clipboard
        self.rollback_engine.screen_text_inverse = self.tool_registry.restore_screen_control_text
        self.tool_registry.clipboard_task_resolver = self.supervisor.get_task

        self.router = Router()

        # Model & Planner Lifecycles (Zero-ML at startup; auto-unloaded on idle)
        model_name = get(self.config, "brain", "model_name", default="qwen3-4b.gguf")
        model_path = get(self.config, "brain", "model_path", default=str(paths.llm_models_dir / model_name))
        idle_seconds = float(get(self.config, "runtime", "model_idle_unload_seconds", default=30.0))
        if not get(self.config, "runtime", "allow_short_warm_grace", default=True):
            idle_seconds = 0
        max_plan_steps = get(self.config, "agent", "max_plan_steps", default=8)

        from pluma.brain.lifecycle import LlmLifecycleManager
        self.llm_lifecycle = LlmLifecycleManager(
            model_path=model_path,
            registry=self.tool_registry,
            idle_unload_seconds=idle_seconds,
            max_plan_steps=max_plan_steps,
        )

        self.orchestrator = Orchestrator(
            registry=self.tool_registry,
            supervisor=self.supervisor,
            ledger=self.ledger,
            router=self.router,
            llm_manager=self.llm_lifecycle,
            rollback_engine=self.rollback_engine,
        )

        stt_model_name = get(self.config, "voice", "model_name", default="ggml-base.en.bin")
        stt_model_path = get(
            self.config,
            "voice",
            "model_path",
            default=str(paths.whisper_models_dir / stt_model_name),
        )
        stt_idle = float(get(self.config, "runtime", "stt_idle_unload_seconds", default=20.0))

        if not get(self.config, "runtime", "allow_short_warm_grace", default=True):
            stt_idle = 0

        from pluma.voice.lifecycle import VoiceLifecycleManager
        from pluma.voice.stt_adapter import WhisperSttAdapter
        self.voice_lifecycle = VoiceLifecycleManager(
            adapter=WhisperSttAdapter(registry=self.tool_registry),
            model_path=stt_model_path,
            idle_unload_seconds=stt_idle,
        )
        self.orchestrator.include_command_previews = get(self.config,"logging","include_command_previews",default=True)
        self.voice_pipeline = VoicePipeline(lifecycle_manager=self.voice_lifecycle,
            include_command_previews=get(self.config,"logging","include_command_previews",default=True))

        self.resident_core = ResidentCore(
            config=self.config,
            voice_pipeline=self.voice_pipeline,
            supervisor=self.supervisor,
            orchestrator=self.orchestrator,
            ledger=self.ledger,
            ownership_registry=self.ownership_registry,
            effective_model_path=model_path,
            effective_stt_model_path=stt_model_path,
            confirmation_broker=self.confirmation_broker,
            settings_path=self.settings_path,
        )
        self.resident_core.default_model_path = str(paths.llm_models_dir / model_name)
        self.resident_core.default_stt_model_path = str(paths.whisper_models_dir / stt_model_name)

    def close(self, timeout_s: float = 5.0):
        """Bounded, resumable shutdown. Unknown drain keeps storage owned/open."""
        from pluma.core.shutdown import ShutdownSession
        with _CLOSE_INIT_LOCK:
            if not hasattr(self, "_shutdown_session"):
                self._shutdown_session = ShutdownSession()
        # Latch every task before any external shutdown operation/wait.
        self.supervisor.begin_shutdown()
        self.resident_core.begin_shutdown()
        self.tool_registry.begin_shutdown()
        for lifecycle in (self.llm_lifecycle, self.voice_lifecycle):
            if hasattr(lifecycle, "begin_shutdown"):
                lifecycle.begin_shutdown()
        stages = [
            ("capture", self.resident_core.cancel_capture),
            ("tasks", self.supervisor.drain_shutdown_tasks),
            ("handlers", self._drain_handlers),
            ("registry", self.tool_registry.close),
            ("outcomes", self.supervisor.finalize_shutdown),
            ("planner", lambda: self._close_model(self.llm_lifecycle)),
            ("voice", lambda: self._close_model(self.voice_lifecycle)),
            ("storage", self._close_storage),
        ]
        self.shutdown_result = self._shutdown_session.run(stages, timeout_s)
        return self.shutdown_result

    def _drain_handlers(self):
        self.resident_core.stop()
        if not self.supervisor.execution_gate.wait_idle(1.0):
            raise RuntimeError("Execution handlers remain active.")

    def _close_model(self, lifecycle):
        if not hasattr(self, "_shutdown_timers"):
            self._shutdown_timers = set()
        for name in ("_idle_timer", "_unload_timer"):
            timer = getattr(lifecycle, name, None)
            if isinstance(timer, threading.Thread):
                self._shutdown_timers.add(timer)
        timers = getattr(lifecycle, "_timers", set())
        if isinstance(timers, set):
            self._shutdown_timers.update(timers.copy())
        for timer in self._shutdown_timers.copy():
            timer.cancel()
        lifecycle.shutdown()
        for timer in list(self._shutdown_timers):
            if isinstance(timer, threading.Thread):
                timer.join(timeout=1.0)
                if timer.is_alive():
                    raise RuntimeError("Model lifecycle timer remains active.")
                self._shutdown_timers.remove(timer)
        adapter = getattr(lifecycle, "adapter", None)
        if adapter is not None and adapter.is_loaded is not False:
            raise RuntimeError("Model unload remains unverified.")

    def _close_storage(self):
        self.db.close()
        if self.db.is_open is not False:
            raise RuntimeError("Storage closure remains unverified.")


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
    parser.add_argument("--restore-previous-settings", action="store_true", help="Explicit confirmed settings recovery without starting resident hotkeys/devices")
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

    if args.recover_only and args.restore_previous_settings:
        parser.error("Choose one explicit recovery operation.")
    if not args.recover_only and not args.restore_previous_settings:
        from pluma.core.host import CoreHost
        host=CoreHost(paths,config_path=args.config,debug=args.debug)
        stopped=threading.Event()
        signal.signal(signal.SIGINT,lambda *_:stopped.set())
        signal.signal(signal.SIGTERM,lambda *_:stopped.set())
        try:
            host.start()
            while not stopped.wait(.05):host.advance()
        except KeyboardInterrupt:
            stopped.set()
        finally:
            while not host.close():time.sleep(.1)
            shutdown_logging()
        return 0
    from pluma.config.settings import _exclusive
    with _exclusive(paths.local_root/"core.host.lock"):
        return _run_explicit_recovery(args,paths)


def _run_explicit_recovery(args,paths):
    # 2. Configure logging
    logging_config = {} if args.restore_previous_settings else load_config(args.config)
    setup_logging(paths.logs_dir, debug=args.debug or get(logging_config,"logging","debug",default=False))
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

    if args.restore_previous_settings:
        from pluma.config.settings import SettingsStore
        from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
        from pluma.core.request import PlumaRequest, InputMode
        from pluma.brain.schemas import Plan, ToolCall, RouteMode
        source = Path(args.config or os.environ.get("PLUMA_CONFIG") or paths.user_settings_path).absolute()
        revision, previous = SettingsStore(source).recovery_state()
        from pluma.config.loader import _load_yaml, _DEFAULTS_FILE
        recovery_runtime = PlumaApplicationRuntime(paths, config=_load_yaml(_DEFAULTS_FILE), settings_path=str(source),
            confirmation_contract=CallbackConfirmationContract(lambda request: ConfirmationResponse(
                approved=input(request.prompt_message + " Type RESTORE to approve: ") == "RESTORE")))
        try:
            request=PlumaRequest(input_mode=InputMode.TEXT,text="Restore previous valid PLUMA settings.")
            capsule=recovery_runtime.supervisor.create_task_capsule(request_id=request.request_id)
            result=recovery_runtime.orchestrator.execute_typed_plan(request,capsule,
                Plan(task_id=capsule.task_id,route=RouteMode.FAST,steps=[ToolCall(tool="recover_settings",
                    arguments={"expected_revision":revision,"previous_revision":previous.revision},purpose="Restore selected valid settings.")]))
            return 0 if result.success else 1
        finally:
            if not recovery_runtime.close(5).complete:
                raise RuntimeError("Settings recovery cleanup remains unverified.")
            shutdown_logging()



def main() -> None:
    """Console script entry point."""
    sys.exit(run_app())


if __name__ == "__main__":
    main()
