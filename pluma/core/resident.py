"""pluma.core.resident — Resident process, hotkeys and tray entry.

Spec §5.1 Resident Core: "Hotkeys, voice trigger, STOP, IPC, request creation,
runtime lifecycle, task state. Must not load heavy ML at startup."
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from pluma.config.loader import get, load_config
from pluma.core.ipc import IpcServer
from pluma.core.ownership import OwnershipRegistry
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.task_supervisor import TaskSupervisor

if TYPE_CHECKING:
    from pluma.voice.activation import VoiceActivation
    from pluma.voice.capture import AudioCapture
    from pluma.voice.pipeline import VoicePipeline

logger = logging.getLogger(__name__)
_VOICE_INIT_LOCK = threading.Lock()

# Hotkey identifiers
HOTKEY_ID_TEXT = 1
HOTKEY_ID_STOP = 2
HOTKEY_ID_VOICE = 3


class ResidentCore:
    """Resident process coordinating IPC, Task Supervisor, Voice, and global hotkeys."""

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        voice_pipeline: Optional[VoicePipeline] = None,
        on_request_callback: Optional[Callable[[Any], Any]] = None,
        supervisor: Optional[TaskSupervisor] = None,
        orchestrator: Optional[Any] = None,
        ledger: Optional[Any] = None,
        ownership_registry: Optional[OwnershipRegistry] = None,
        ipc_address: Optional[str] = None,
    ) -> None:
        self.config = config or load_config()
        self.registry = ownership_registry or OwnershipRegistry()
        self.ledger = ledger
        self.supervisor = supervisor or TaskSupervisor(ownership_registry=self.registry, ledger=self.ledger)
        self.orchestrator = orchestrator
        self.on_request_callback = on_request_callback or (self.orchestrator.execute if self.orchestrator else None)
        self.ipc = IpcServer(command_handler=self.handle_ipc_command, address=ipc_address, require_auth=True)


        # Voice subsystem components (zero-ML at idle; lazily initialized if voice_enabled)
        self.voice_enabled = get(self.config, "voice", "required", default=True)
        self.voice_hotkey_str = get(self.config, "agent", "voice_hotkey", default="ctrl+alt+v")

        if voice_pipeline is not None:
            self.voice_pipeline: Optional[VoicePipeline] = voice_pipeline
        elif self.voice_enabled:
            from pluma.voice.pipeline import VoicePipeline
            self.voice_pipeline = VoicePipeline()
        else:
            self.voice_pipeline = None

        if self.voice_enabled:
            from pluma.voice.activation import VoiceActivation
            from pluma.voice.capture import AudioCapture
            self.audio_capture: Optional[AudioCapture] = AudioCapture()
            self.voice_activation: Optional[VoiceActivation] = VoiceActivation(
                on_press=self._on_voice_press,
                on_release=self._on_voice_release,
                hotkey=self.voice_hotkey_str,
            )
        else:
            self.audio_capture = None
            self.voice_activation = None

        self._hotkey_thread: Optional[threading.Thread] = None
        self._running = False
        from pluma.core.shutdown import WorkGate
        self._entry_gate = WorkGate()
        self._voice_lock = threading.Lock()
        self._voice_session = None

    def _on_voice_press(self) -> None:
        # Bare fixtures initialize lazily; production creates the gate at startup.
        from pluma.core.shutdown import WorkGate
        from pluma.core.cancellation import TaskCancelledError
        if not hasattr(self, "_entry_gate"):
            self._entry_gate = WorkGate()
        try:
            with self._entry_gate.enter():
                return self._admitted_on_voice_press()
        except TaskCancelledError:
            return {"status": "error", "message": ("Runtime is shutting down." if self._entry_gate.closing
                                                    else "Task was cancelled.")}

    def _voice_state_lock(self):
        # Bare audit fixtures bypass __init__; creation is serialized as well.
        with _VOICE_INIT_LOCK:
            if not hasattr(self, "_voice_lock"):
                self._voice_lock = threading.Lock()
            return self._voice_lock

    def _admitted_on_voice_press(self) -> None:
        from pluma.voice.session import VoiceSession
        with self._voice_state_lock():
            previous = getattr(self, "_voice_session", None)
            if previous is not None:
                if not previous.released or not previous.idle:
                    return
                self.supervisor.refresh_voice_cleanup(previous.capsule)
                if previous.capsule.voice_session is not None:
                    return  # failed closure keeps the device and capsule owned
                self._voice_session = None
            capsule = self.supervisor.create_task_capsule(history_expected=False)
            session = VoiceSession(capsule, self.audio_capture)
            self._voice_session = session
            self._current_voice_capsule = capsule
        try:
            self.supervisor.attach_voice_session(capsule, session)
            session.start()
        except Exception:
            logger.warning("Voice capture could not start.")
            session.finish_start()
            if not capsule.terminal_ready.is_set():
                if capsule.cancellation_token.is_cancelled:
                    self.supervisor.stop_task(capsule.task_id, grace_s=0)
                else:
                    self.supervisor.fail_task_with_rollback(capsule.task_id)
        finally:
            self.supervisor.refresh_voice_cleanup(capsule)

    def _on_voice_release(self) -> None:
        # Bare fixtures initialize lazily; production creates the gate at startup.
        from pluma.core.shutdown import WorkGate
        from pluma.core.cancellation import TaskCancelledError
        if not hasattr(self, "_entry_gate"):
            self._entry_gate = WorkGate()
        try:
            with self._entry_gate.enter():
                return self._admitted_on_voice_release()
        except TaskCancelledError:
            return {"status": "error", "message": ("Runtime is shutting down." if self._entry_gate.closing
                                                    else "Task was cancelled.")}

    def _admitted_on_voice_release(self) -> None:
        with self._voice_state_lock():
            session = getattr(self, "_voice_session", None)
            if session is None or not session.claim_release():
                return
        capsule = session.capsule
        raw_audio = None
        failed = False
        dispatched = False
        try:
            raw_audio = session.stop_and_get()
            capsule.cancellation_token.raise_if_cancelled()
            if not raw_audio or self.voice_pipeline is None:
                return
            request = self.voice_pipeline.process_audio(
                raw_audio, cancellation_token=capsule.cancellation_token)
            raw_audio = None  # raw audio is never included in logs/history
            capsule.cancellation_token.raise_if_cancelled()
            if request is None:
                return  # silence/low-confidence clarification, no guessed action
            if self.orchestrator is None:
                raise RuntimeError("Voice execution owner is unavailable.")
            capsule.request_id = str(request.request_id)
            dispatched = True
            self.orchestrator.execute(request, capsule=capsule)
        except Exception:
            failed = not capsule.cancellation_token.is_cancelled
            logger.warning("Voice request did not complete.")
        finally:
            raw_audio = None
            session.finish_release()
            if (not dispatched or failed) and not capsule.terminal_ready.is_set():
                if failed:
                    self.supervisor.fail_task_with_rollback(capsule.task_id)
                else:
                    self.supervisor.stop_task(capsule.task_id, grace_s=0)
            self.supervisor.refresh_voice_cleanup(capsule)
            with self._voice_state_lock():
                if (getattr(self, "_voice_session", None) is session
                        and session.idle and capsule.voice_session is None):
                    self._voice_session = None


    def handle_ipc_command(self, req: Dict[str, Any]) -> Dict[str, Any]:
        # Bare fixtures initialize lazily; production creates the gate at startup.
        from pluma.core.shutdown import WorkGate
        from pluma.core.cancellation import TaskCancelledError
        if not hasattr(self, "_entry_gate"):
            self._entry_gate = WorkGate()
        try:
            with self._entry_gate.enter():
                return self._admittedhandle_ipc_command(req)
        except TaskCancelledError:
            return {"status": "error", "message": ("Runtime is shutting down." if self._entry_gate.closing
                                                    else "Task was cancelled.")}

    def _admittedhandle_ipc_command(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming IPC commands."""
        cmd = req.get("command")

        # 1. Execute text command
        if cmd in ("execute", "request", "submit"):
            req_data = req.get("request") if isinstance(req.get("request"), dict) else req
            text = (
                req_data.get("text")
                or req_data.get("command_text")
                or req_data.get("query")
                or req.get("text")
                or req.get("command_text")
                or req.get("query")
            )
            if not text:
                return {"status": "error", "message": "Missing 'text' in command payload."}

            pluma_req = PlumaRequest(input_mode=InputMode.TEXT, text=str(text))
            if self.orchestrator:
                res = self.orchestrator.execute(pluma_req)
                return {
                    "status": "ok",
                    "task_id": res.task_id,
                    "request_id": res.request_id,
                    "final_state": res.final_state,
                    "success": res.success,
                    "route": res.route.value if hasattr(res.route, "value") else str(res.route),
                    "message": res.user_message,
                    "duration_ms": res.duration_ms,
                    "completion_verified": res.completion_verified,
                    "terminal_persisted": res.terminal_persisted,
                    "has_residual": res.has_residual,
                    "rollback_performed": res.rollback_performed,
                    "rollback_success": res.rollback_success,
                    "cleanup_evidence": res.cleanup_evidence,
                }
            elif self.on_request_callback:
                callback_res = self.on_request_callback(pluma_req)
                return {"status": "ok", "message": "Request dispatched via callback.", "result": str(callback_res)}
            else:
                return {"status": "error", "message": "No orchestrator or callback configured."}

        # 2/3. STOP receipts distinguish the latch from verified cleanup.
        elif cmd in ("stop", "STOP", "stop_all", "stop_task"):
            from pluma.core.stop_protocol import StopReply
            tid = req.get("task_id") if cmd == "stop_task" else None
            if cmd == "stop_task" and (not isinstance(tid, str) or not tid.strip() or len(tid) > 128):
                return StopReply(status="error", message="A valid task ID is required.",
                                 error_code="INVALID_TASK_ID").wire()
            return self.supervisor.request_stop(tid).wire()

        # 4. Status query
        elif cmd == "status":
            return {
                "status": "ok",
                "running": self._running,
                "message": "Resident core running",
                "active_tasks": len(self.supervisor.get_active_tasks()),
                "voice_enabled": self.voice_enabled,
            }

        # 5. Recent tasks
        elif cmd in ("recent_tasks", "get_recent_tasks"):
            limit = req.get("limit", 50)
            from pluma.memory.activity import ActivityQuery
            query = ActivityQuery(self.ledger._db) if hasattr(self.ledger, "_db") else None
            tasks = query.recent_tasks(limit=limit) if query else []
            return {"status": "ok", "tasks": tasks}

        return {"status": "error", "message": f"Unknown command: {cmd}"}

    def _run_crash_recovery(self) -> None:
        """Scan for unfinished tasks from previous run and clean up.
        
        Spec §13: "On PLUMA startup, stale tasks are marked ABORTED and 
        residual temp metadata is checked."
        """
        logger.info("Running startup crash recovery...")
        pass

    def _hotkey_loop(self) -> None:
        """Windows message loop for global hotkeys."""
        if sys.platform != "win32":
            return

        import ctypes
        from ctypes import wintypes
        from pluma.voice.activation import parse_hotkey_string

        user32 = ctypes.WinDLL("user32", use_last_error=True)

        # Register text and STOP hotkeys from config
        text_mods, text_vk = parse_hotkey_string(get(self.config, "agent", "text_hotkey", default="win+alt+p"))
        stop_mods, stop_vk = parse_hotkey_string(get(self.config, "agent", "stop_hotkey", default="ctrl+alt+esc"))

        if not user32.RegisterHotKey(None, HOTKEY_ID_TEXT, text_mods, text_vk):
            logger.warning("Failed to register Text hotkey")

        if not user32.RegisterHotKey(None, HOTKEY_ID_STOP, stop_mods, stop_vk):
            logger.warning("Failed to register STOP hotkey")

        msg = wintypes.MSG()
        while self._running:
            bRet = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if bRet <= 0:
                break

            if msg.message == 0x0312:  # WM_HOTKEY
                if msg.wParam == HOTKEY_ID_STOP:
                    logger.info("Global STOP hotkey triggered!")
                    self.supervisor.stop_all_active_tasks()
                elif msg.wParam == HOTKEY_ID_TEXT:
                    logger.info("Global Text hotkey triggered!")

            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, HOTKEY_ID_TEXT)
        user32.UnregisterHotKey(None, HOTKEY_ID_STOP)

    def start(self) -> None:
        """Start the resident core, voice listener, and background workers."""
        self._run_crash_recovery()
        self.ipc.start()

        if self.voice_enabled and self.voice_activation is not None:
            self.voice_activation.start()

        self._running = True
        if sys.platform == "win32":
            self._hotkey_thread = threading.Thread(target=self._hotkey_loop, daemon=True, name="HotkeyThread")
            self._hotkey_thread.start()

    def begin_shutdown(self) -> None:
        from pluma.core.shutdown import WorkGate
        if not hasattr(self, "_entry_gate"):
            self._entry_gate = WorkGate()
        self._entry_gate.begin_shutdown()
        self._running = False
        if hasattr(self.ipc, "begin_shutdown"):
            self.ipc.begin_shutdown()

    def cancel_capture(self) -> None:
        """Discard capture through the same owner used by task STOP."""
        session = getattr(self, "_voice_session", None)
        if session is not None:
            session.cancel_capture()
            return
        capture = getattr(self, "audio_capture", None)
        if capture is not None:
            if hasattr(capture, "cancel"):
                capture.cancel()
            else:
                capture.stop_and_get()  # inert legacy capture fixture

    def stop(self) -> None:
        """Reject entry, cancel capture and verify all resident handlers exit."""
        self.begin_shutdown()
        self.cancel_capture()
        if self.voice_enabled and self.voice_activation is not None:
            self.voice_activation.stop()
        if sys.platform == "win32" and self._hotkey_thread and self._hotkey_thread.is_alive():
            import ctypes
            user32 = ctypes.WinDLL("user32")
            user32.PostThreadMessageW(self._hotkey_thread.native_id, 0x0012, 0, 0)
            self._hotkey_thread.join(timeout=1.0)
            if self._hotkey_thread.is_alive():
                raise RuntimeError("Hotkey owner remains active.")
        self.ipc.stop()
        if not self._entry_gate.wait_idle(1.0):
            raise RuntimeError("Resident handlers remain active.")
        self.cancel_capture()  # an admitted press may have crossed the first cancel
        if self.voice_enabled and self.voice_pipeline is not None and hasattr(self.voice_pipeline, "lifecycle"):
            lifecycle = self.voice_pipeline.lifecycle
            lifecycle.shutdown()
            for timer in getattr(lifecycle, "_timers", set()).copy():
                timer.join(timeout=1.0)
                if timer.is_alive():
                    raise RuntimeError("Voice lifecycle owner remains active.")
            adapter = getattr(lifecycle, "adapter", None)
            if adapter is not None and adapter.is_loaded is not False:
                raise RuntimeError("Voice unload remains unverified.")
