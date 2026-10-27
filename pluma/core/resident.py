"""pluma.core.resident — Resident process, hotkeys and tray entry.

Spec §5.1 Resident Core: "Hotkeys, voice trigger, STOP, IPC, request creation,
runtime lifecycle, task state. Must not load heavy ML at startup."
"""

from __future__ import annotations

import logging
import hashlib
import json
import sys
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

from pluma.config.loader import get, load_config
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.ipc import MAX_IPC_MESSAGE_SIZE, IpcServer
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
        on_voice_clarification_callback: Optional[Callable[[Any], Any]] = None,
        supervisor: Optional[TaskSupervisor] = None,
        orchestrator: Optional[Any] = None,
        ledger: Optional[Any] = None,
        ownership_registry: Optional[OwnershipRegistry] = None,
        ipc_address: Optional[str] = None,
        effective_model_path: Optional[str] = None,
        effective_stt_model_path: Optional[str] = None,
        confirmation_broker: Optional[Any] = None,
    ) -> None:
        self.config = config or load_config()
        self.effective_model_path = effective_model_path
        self.effective_stt_model_path = effective_stt_model_path
        self.confirmation_broker = confirmation_broker
        self.registry = ownership_registry or OwnershipRegistry()
        self.ledger = ledger
        self.supervisor = supervisor or TaskSupervisor(ownership_registry=self.registry, ledger=self.ledger)
        self.orchestrator = orchestrator
        self.on_request_callback = on_request_callback or (self.orchestrator.execute if self.orchestrator else None)
        self.on_voice_clarification_callback = on_voice_clarification_callback
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
            vad = getattr(self.voice_pipeline, "vad", None)
            self.audio_capture: Optional[AudioCapture] = AudioCapture(vad=vad)
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
        self._submission_lock = threading.RLock()
        self._submission_records = OrderedDict()
        self._submission_threads = {}
        self._submission_fence_lock = threading.RLock()
        self._stopped_submission_ids = set()
        self._submission_admission_paused = False

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
            from pluma.voice.pipeline import VoiceClarificationRequired
            if isinstance(request, VoiceClarificationRequired):
                callback = self.on_voice_clarification_callback
                if callback is not None:
                    callback(request)
                else:
                    logger.info("Voice clarification is required; no request was admitted.")
                return
            if request is None:
                return  # silence or invalid speech; no guessed action
            if self.orchestrator is None:
                raise RuntimeError("Voice execution owner is unavailable.")
            capsule.request_id = str(request.request_id)
            dispatched = True
            self.orchestrator.execute(request, capsule=capsule)
        except TaskCancelledError:
            failed = capsule.cancellation_token.reason == StopReason.TASK_TIMEOUT
            if failed:
                logger.warning("Voice request exceeded its deadline.")
        except Exception:
            # The task worker records its deadline by latching TASK_TIMEOUT;
            # retain that factual failure through voice-capsule finalization.
            failed = (not capsule.cancellation_token.is_cancelled
                     or capsule.cancellation_token.reason == StopReason.TASK_TIMEOUT)
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
        if "protocol_version" in req or "message_type" in req:
            return self._handle_versioned_ipc(req)
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

    def _handle_versioned_ipc(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from pluma.core.ipc_contracts import (
            ProtocolErrorV1, SubmissionAckV1,
            ConfirmationQueryV1, ConfirmationDecisionV1, ConfirmationDisconnectV1, EventsQueryV1,
            ActivityQueryV1, HistoryQueryV1, SettingsQueryV1, StopRequestV1, SubmitTextV1,
            TerminalReadbackRequestV1, parse_versioned_request,
        )
        try:
            request = parse_versioned_request(payload)
        except ValueError as exc:
            code = str(exc) if str(exc) in {
                "UNSUPPORTED_PROTOCOL_VERSION", "INVALID_REQUEST", "UNKNOWN_MESSAGE_TYPE"
            } else "INVALID_REQUEST"
            return ProtocolErrorV1(
                error_code=code,
                message={
                    "UNSUPPORTED_PROTOCOL_VERSION": "This protocol version is not supported.",
                    "INVALID_REQUEST": "The request is invalid.",
                    "UNKNOWN_MESSAGE_TYPE": "The message type is not supported.",
                }[code],
            ).model_dump(mode="json")
        if isinstance(request, SubmitTextV1):
            return self._submit_text_v1(request, SubmissionAckV1)
        if isinstance(request, TerminalReadbackRequestV1):
            return self._terminal_readback_v1(request)
        if isinstance(request, StopRequestV1):
            return self._stop_v1(request)
        if isinstance(request, SettingsQueryV1):
            return self._settings_query_v1(request)
        if isinstance(request, HistoryQueryV1):
            return self._history_query_v1(request)
        if isinstance(request, ActivityQueryV1):
            return self._activity_query_v1(request)
        if isinstance(request, (ConfirmationQueryV1, ConfirmationDecisionV1, ConfirmationDisconnectV1, EventsQueryV1)):
            return self._remaining_contract_v1(request)
        return ProtocolErrorV1(error_code="UNKNOWN_MESSAGE_TYPE",
            message="The message type is not supported.").model_dump(mode="json")

    def _submission_state(self):
        # Direct fixtures construct ResidentCore without __init__; initialize
        # the same bounded, owned state lazily and atomically for them.
        with _VOICE_INIT_LOCK:
            if not hasattr(self, "_submission_lock"):
                self._submission_lock = threading.RLock()
                self._submission_records = OrderedDict()
                self._submission_threads = {}
            if not hasattr(self, "_submission_fence_lock"):
                self._submission_fence_lock = threading.RLock()
                self._stopped_submission_ids = set()
                self._submission_admission_paused = False
        return self._submission_lock

    def _submission_is_stopped(self, request_id):
        with self._submission_fence_lock:
            return self._submission_admission_paused or request_id in self._stopped_submission_ids

    def _submit_text_v1(self, request, ack_type):
        from pluma.memory.activity import ActivityQuery, TaskRecord

        ack = lambda **values: ack_type(
            request_id=request.request_id, **values
        ).model_dump(mode="json")
        if self.orchestrator is None or self.ledger is None:
            return ack(accepted=False, error_code="CORE_UNAVAILABLE",
                       message="The request could not be accepted by the core.")
        digest = hashlib.sha256(request.text.encode("utf-8")).hexdigest()
        lock = self._submission_state()
        with lock:
            # Once a stopped request has durable terminal history, the existing
            # replay check is its fence. Reclaim those in-memory IDs on ordinary
            # admission, never by doing database I/O in the priority STOP path.
            with self._submission_fence_lock:
                for stopped_id in list(self._stopped_submission_ids):
                    record = self._submission_records.get(stopped_id)
                    cap = record.get("capsule") if record is not None else None
                    if cap is not None and cap.terminal_ready.is_set() and cap.terminal_persisted is True:
                        self._stopped_submission_ids.discard(stopped_id)
            if self._submission_is_stopped(request.request_id):
                return ack(accepted=False, error_code="SUBMISSION_STOPPED",
                           message="This submission was stopped or admission is paused.")
            previous = self._submission_records.get(request.request_id)
            if previous is not None:
                if previous["digest"] != digest:
                    return ack(accepted=False, error_code="REQUEST_ID_REUSED",
                               message="The request ID is already bound to different text.")
                return ack(accepted=True, task_id=previous["task_id"],
                           message="The request was already accepted.")
            prior_row = ActivityQuery(self.ledger._db).task_by_request_id(request.request_id)
            if prior_row is not None:
                return ack(accepted=False, error_code="REQUEST_ID_REPLAY",
                           message="This request ID was used before; inspect its task before retrying.")
            if len(self._submission_records) >= 256:
                for key, record in list(self._submission_records.items()):
                    if record.get("terminal") is not None:
                        self._submission_records.pop(key)
                        self._submission_threads.pop(record["task_id"], None)
                        if len(self._submission_records) < 256:
                            break
                if len(self._submission_records) >= 256:
                    return ack(accepted=False, error_code="BUSY",
                               message="The core has no submission capacity.")
            for task_id, thread in list(self._submission_threads.items()):
                if not thread.is_alive():
                    self._submission_threads.pop(task_id, None)
            running = sum(thread.is_alive() for thread in self._submission_threads.values())
            if running >= 4:
                return ack(accepted=False, error_code="BUSY",
                           message="The core has no submission capacity.")
            try:
                capsule = self.supervisor.create_task_capsule(request_id=request.request_id)
                from pluma.core.request import InputMode, PlumaRequest
                task_request = PlumaRequest(
                    request_id=request.request_id, input_mode=InputMode.TEXT,
                    text=request.text,
                )
                self.ledger.insert_task(TaskRecord(
                    task_id=capsule.task_id, request_id=request.request_id,
                    input_mode="text", command_text=request.text,
                    created_at=task_request.created_at.isoformat(),
                ))
            except Exception:
                if "capsule" in locals():
                    try:
                        self.supervisor.fail_task_with_rollback(capsule.task_id)
                        from pluma.core.task_supervisor import TaskState
                        self.supervisor.finalize_task(capsule.task_id, TaskState.FAILED)
                    except Exception:
                        logger.error("Rejected IPC task cleanup remains unverified.")
                return ack(accepted=False, error_code="ADMISSION_FAILED",
                           message="The core could not safely admit the request.")
            record = {"digest": digest, "task_id": capsule.task_id,
                      "request_id": request.request_id, "capsule": capsule,
                      "terminal": None, "route": None, "duration_ms": None,
                      "message": "Execution is in progress."}
            self._submission_records[request.request_id] = record
            thread = threading.Thread(
                target=self._run_text_submission_v1,
                args=(task_request, capsule, request.request_id),
                name="PlumaSubmittedTask-" + capsule.task_id[:8], daemon=True,
            )
            self._submission_threads[capsule.task_id] = thread
            try:
                # STOP never waits for the ordinary submission/history lock.
                # Its short fence orders against the actual thread start.
                with self._submission_fence_lock:
                    fenced = self._submission_is_stopped(request.request_id)
                    if not fenced:
                        thread.start()
                if fenced:
                    self._submission_records.pop(request.request_id, None)
                    self._submission_threads.pop(capsule.task_id, None)
                    self.supervisor.stop_task(capsule.task_id)
                    if capsule.terminal_ready.is_set():
                        # A STOP may have finalized before insert_task returned.
                        # Reassert its authoritative state after that insertion.
                        self.ledger.finalize_task(capsule.task_id, final_state=capsule.state.value,
                            completed_at=capsule.completed_at.isoformat(),
                            stop_reason=capsule.cancellation_token.reason.value,
                            error_code=None, entries=[item.model_dump() for item in capsule.cleanup_evidence])
                    return ack(accepted=False, error_code="SUBMISSION_STOPPED", message="This submission was stopped before execution.")
            except Exception:
                self._submission_records.pop(request.request_id, None)
                self._submission_threads.pop(capsule.task_id, None)
                try:
                    self.supervisor.fail_task_with_rollback(capsule.task_id)
                    from pluma.core.task_supervisor import TaskState
                    self.supervisor.finalize_task(capsule.task_id, TaskState.FAILED)
                except Exception:
                    logger.error("Rejected IPC task cleanup remains unverified.")
                return ack(accepted=False, error_code="ADMISSION_FAILED",
                           message="The core could not safely start the accepted request.")
        return ack(accepted=True, task_id=capsule.task_id,
                   message="The request was accepted for execution.")

    def _run_text_submission_v1(self, request, capsule, request_id: str) -> None:
        try:
            result = self.orchestrator.execute(request, capsule=capsule)
            projection = {
                "terminal": bool(capsule.terminal_ready.is_set()),
                "final_state": str(result.final_state),
                "completion_verified": bool(result.completion_verified),
                "terminal_persisted": result.terminal_persisted,
                "has_residual": bool(result.has_residual),
                "route": result.route.value if hasattr(result.route, "value") else str(result.route),
                "message": str(result.user_message or "Task result is available."),
                "duration_ms": float(result.duration_ms),
            }
        except Exception:
            logger.warning("Versioned IPC task did not return a result.")
            projection = None
            try:
                self.supervisor.fail_task_with_rollback(capsule.task_id)
                from pluma.core.task_supervisor import TaskState
                capsule = self.supervisor.finalize_task(capsule.task_id, TaskState.FAILED)
            except Exception:
                logger.error("Versioned IPC task cleanup remains unverified.")
        lock = self._submission_state()
        with lock:
            record = self._submission_records.get(request_id)
            if record is None:
                return
            record["terminal"] = projection
            record["capsule"] = capsule
            if projection is None:
                record["message"] = capsule.terminal_summary()
            if projection is not None:
                record["route"] = projection["route"]
                record["duration_ms"] = projection["duration_ms"]
                record["message"] = projection["message"]

    def _terminal_readback_v1(self, request):
        from pluma.core.ipc_contracts import TerminalReadbackV1
        from pluma.memory.activity import ActivityQuery
        lock = self._submission_state()
        with lock:
            record = self._submission_records.get(request.request_id)
            if record is None:
                row = ActivityQuery(self.ledger._db).task_by_request_id(request.request_id)
                if row is None or row["task_id"] != request.task_id:
                    return {"protocol_version": 1, "message_type": "protocol_error",
                            "error_code": "TASK_NOT_FOUND",
                            "message": "No task matches this request and task ID."}
                state = row.get("final_state") or "CREATED"
                terminal = state in {"SUCCEEDED", "FAILED", "STOPPED", "STOPPED_WITH_RESIDUAL", "ABORTED_BY_CRASH"}
                residual = state == "STOPPED_WITH_RESIDUAL"
                message = ("Task outcome was read from saved history; detailed verification is unavailable in this session."
                           if terminal else "Execution status was read from saved history.")
                return TerminalReadbackV1(
                    request_id=request.request_id, task_id=request.task_id,
                    terminal=terminal, final_state=state, completion_verified=False,
                    terminal_persisted=True if terminal else None,
                    has_residual=residual, route=row.get("route"), message=message,
                    duration_ms=None,
                ).model_dump(mode="json")
            if record["task_id"] != request.task_id:
                return {"protocol_version": 1, "message_type": "protocol_error",
                        "error_code": "TASK_NOT_FOUND",
                        "message": "No task matches this request and task ID."}
            capsule = record.get("capsule")
            result = record.get("terminal")
            if capsule is not None:
                ready = bool(capsule.terminal_ready.is_set())
                details = capsule.outcome_details()
                terminal = ready
                final_state = capsule.state.value
                verified = bool(result["completion_verified"]) if result is not None else False
                persisted = details["terminal_persisted"]
                residual = bool(details["has_residual"])
                message = capsule.terminal_summary() if ready else "Execution is in progress."
                route = record.get("route")
                duration = record.get("duration_ms")
            elif result is not None:
                terminal = bool(result["terminal"])
                final_state = result["final_state"]
                verified = bool(result["completion_verified"])
                persisted = result["terminal_persisted"]
                residual = bool(result["has_residual"])
                message = result["message"]
                route = result["route"]
                duration = result["duration_ms"]
            else:
                terminal, final_state, verified, persisted, residual = False, "CREATED", False, None, False
                message, route, duration = "Execution is in progress.", None, None
            return TerminalReadbackV1(
                request_id=request.request_id, task_id=request.task_id,
                terminal=terminal, final_state=final_state,
                completion_verified=verified, terminal_persisted=persisted,
                has_residual=residual, route=route, message=message,
                duration_ms=duration,
            ).model_dump(mode="json")

    def _stop_v1(self, request):
        if request.submission_request_id is not None:
            self._submission_state()
            with self._submission_fence_lock:
                if len(self._stopped_submission_ids) < 256:
                    self._stopped_submission_ids.add(request.submission_request_id)
                elif request.submission_request_id not in self._stopped_submission_ids:
                    # Never evict a cancelled identity and accidentally admit it.
                    # Capacity exhaustion pauses new admissions until restart.
                    self._submission_admission_paused = True
        receipt = self.supervisor.request_stop(request.task_id).wire()
        if getattr(self, "_submission_admission_paused", False):
            receipt["message"] = "STOP acknowledged. Submission fence capacity is exhausted; new requests require a core restart."
        return {
            "protocol_version": 1,
            "message_type": "stop_ack",
            "request_id": request.request_id,
            **receipt,
        }

    def _remaining_contract_v1(self, request):
        from pluma.core.ipc_contracts import (
            ConfirmationQueryV1, ConfirmationDecisionV1, EventsQueryV1,
            ConfirmationListV1, ConfirmationAckV1, ConfirmationDisconnectedV1, EventBatchV1,
        )
        try:
            if isinstance(request, EventsQueryV1):
                from pluma.memory.activity import ActivityQuery
                batch = ActivityQuery(self.ledger._db).event_batch(
                    request.stream_id, request.after_sequence, request.limit)
                return EventBatchV1(request_id=request.request_id, **batch).model_dump(mode="json")
            broker = getattr(self, "confirmation_broker", None)
            if broker is None:
                raise ValueError("Confirmation contract is unavailable.")
            if isinstance(request, ConfirmationQueryV1):
                return ConfirmationListV1(request_id=request.request_id, client_id=request.client_id,
                    confirmations=broker.pending(request.client_id)).model_dump(mode="json")
            if isinstance(request, ConfirmationDecisionV1):
                accepted, error = broker.decide(request)
                return ConfirmationAckV1(request_id=request.request_id,
                    confirmation_id=request.confirmation_id, accepted=accepted,
                    approved=request.approved if accepted else None, error_code=error).model_dump(mode="json")
            return ConfirmationDisconnectedV1(request_id=request.request_id, client_id=request.client_id,
                denied_count=broker.disconnect(request.client_id)).model_dump(mode="json")
        except Exception:
            return {"protocol_version": 1, "message_type": "protocol_error",
                    "error_code": "CONTRACT_UNAVAILABLE", "message": "The requested contract is unavailable."}

    def _settings_query_v1(self, request):
        from pluma.core.ipc_contracts import SettingsSnapshotV1
        config = getattr(self, "config", None)
        if not isinstance(config, dict):
            return {"protocol_version": 1, "message_type": "protocol_error",
                    "error_code": "SETTINGS_UNAVAILABLE",
                    "message": "Current settings are unavailable."}
        values = {
            "request_id": request.request_id,
            "submission_stop_fence": True,
            "text_hotkey": get(config, "agent", "text_hotkey"),
            "stop_hotkey": get(config, "agent", "stop_hotkey"),
            "voice_hotkey": get(config, "agent", "voice_hotkey", default="ctrl+alt+v"),
            "max_plan_steps": get(config, "agent", "max_plan_steps"),
            "default_tool_timeout_seconds": get(config, "agent", "default_tool_timeout_seconds"),
            "model_idle_unload_seconds": get(config, "runtime", "model_idle_unload_seconds"),
            "stt_idle_unload_seconds": get(config, "runtime", "stt_idle_unload_seconds"),
            "ocr_idle_unload_seconds": get(config, "runtime", "ocr_idle_unload_seconds"),
            "allow_short_warm_grace": get(config, "runtime", "allow_short_warm_grace"),
            "voice_required": get(config, "voice", "required"),
            "activation_default": get(config, "voice", "activation_default"),
            "wake_phrase_enabled": get(config, "voice", "wake_phrase_enabled"),
            "save_audio": get(config, "voice", "save_audio"),
            "persist_screenshots": get(config, "perception", "persist_screenshots"),
            "ocr_enabled": get(config, "perception", "ocr_enabled"),
            "uia_first": get(config, "perception", "uia_first"),
            "model_runtime": get(config, "brain", "runtime"),
            "model_profile": get(config, "brain", "model_profile"),
            "planner_model_path": (getattr(self, "effective_model_path", None) or
                                   get(config, "brain", "model_path")),
            "stt_model_path": (getattr(self, "effective_stt_model_path", None) or
                               get(config, "voice", "model_path")),
            "confirm_high_risk": get(config, "policy", "confirm_high_risk"),
            "redact_sensitive_logs": get(config, "policy", "redact_sensitive_logs"),
            "activity_view_enabled": get(config, "memory", "activity_view_enabled"),
        }
        try:
            return SettingsSnapshotV1(**values).model_dump(mode="json")
        except Exception:
            return {"protocol_version": 1, "message_type": "protocol_error",
                    "error_code": "SETTINGS_UNAVAILABLE",
                    "message": "Current settings do not match the supported settings view."}

    def _history_query_v1(self, request):
        from pluma.core.ipc_contracts import ActionHistoryV1, HistoryReplyV1, TaskSummaryV1
        from pluma.memory.activity import ActivityQuery
        from pluma.memory.redaction import redact_command_text, redact_sensitive_data

        if self.ledger is None or not hasattr(self.ledger, "_db"):
            return {"protocol_version": 1, "message_type": "protocol_error",
                    "error_code": "HISTORY_UNAVAILABLE",
                    "message": "Activity history is unavailable."}
        query = ActivityQuery(self.ledger._db)

        def task_summary(row):
            return TaskSummaryV1(
                task_id=row["task_id"], request_id=row["request_id"],
                input_mode=row["input_mode"],
                command_text=redact_command_text(row.get("command_text") or ""),
                created_at=row["created_at"], started_at=row.get("started_at"),
                completed_at=row.get("completed_at"), final_state=row.get("final_state"),
                route=row.get("route"), stop_reason=row.get("stop_reason"),
                error_code=row.get("error_code"),
            )

        def decoded_object(value):
            if value is None:
                return None
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("History JSON is not an object.")
            return redact_sensitive_data(parsed)

        try:
            if request.task_id is None:
                tasks = [task_summary(row) for row in query.recent_tasks(limit=request.limit)]
                actions = []
            else:
                row = query.task_by_id(request.task_id)
                if row is None:
                    return {"protocol_version": 1, "message_type": "protocol_error",
                            "error_code": "TASK_NOT_FOUND",
                            "message": "No saved task matches this task ID."}
                action_rows = query.actions_for_task(request.task_id)
                if len(action_rows) > request.limit:
                    return {"protocol_version": 1, "message_type": "protocol_error",
                            "error_code": "HISTORY_TOO_LARGE",
                            "message": "Task history exceeds the requested safe result limit."}
                tasks = [task_summary(row)]
                actions = []
                for action in action_rows:
                    undo = query.undo_status_for_action(int(action["id"]))
                    actions.append(ActionHistoryV1(
                        action_id=int(action["id"]), step_index=int(action["step_index"]),
                        tool=action["tool"], adapter=action.get("adapter"),
                        risk=action["risk"], approval_state=action.get("approval_state"),
                        started_at=action["started_at"], ended_at=action.get("ended_at"),
                        duration_ms=action.get("duration_ms"),
                        arguments=decoded_object(action.get("args_json_sanitized")) or {},
                        result=decoded_object(action.get("result_json")),
                        verified=bool(action["verified"]),
                        verification=decoded_object(action.get("verification_json")),
                        error=decoded_object(action.get("error_json")),
                        undo_available=bool(undo and undo["available"]),
                        rollback_attempted=bool(undo and undo["rollback_attempted"]),
                        rollback_ok=(bool(undo["rollback_ok"]) if undo and undo["rollback_ok"] is not None else None),
                        rollback_result=decoded_object(undo.get("rollback_result_json")) if undo else None,
                    ))
            reply = HistoryReplyV1(
                request_id=request.request_id, task_id=request.task_id,
                tasks=tasks, actions=actions,
            ).model_dump(mode="json")
            if len(json.dumps(reply, separators=(",", ":")).encode("utf-8")) > MAX_IPC_MESSAGE_SIZE:
                return {"protocol_version": 1, "message_type": "protocol_error",
                        "error_code": "HISTORY_TOO_LARGE",
                        "message": "Activity history exceeds the safe message size."}
            return reply
        except Exception:
            logger.warning("Activity history query could not be read safely.")
            return {"protocol_version": 1, "message_type": "protocol_error",
                    "error_code": "HISTORY_UNAVAILABLE",
                    "message": "Activity history could not be read safely."}

    def _activity_query_v1(self, request):
        from pluma.core.ipc_contracts import ActivityActionV1, ActivityCleanupV1, ActivityPageV1
        from pluma.core.cleanup import CleanupEvidence, latest_unresolved
        from pluma.memory.activity import ActivityQuery

        def failure(code):
            return {"protocol_version": 1, "message_type": "protocol_error", "error_code": code,
                    "message": "Activity evidence is unavailable."}

        try:
            rows = ActivityQuery(self.ledger._db).activity_page(request.task_id, request.after_action_id, request.limit)
            if not rows:
                return failure("TASK_NOT_FOUND")
            metadata = rows[0]
            cleanup = None
            encoded = metadata["cleanup_json"]
            if encoded is not None:
                if len(encoded) > 65536:
                    raise ValueError("Cleanup evidence exceeds its bound")
                value = json.loads(encoded)
                if (not isinstance(value, dict) or type(value.get("version")) is not int or value["version"] != 1
                        or type(value.get("complete")) is not bool or not isinstance(value.get("entries"), list)
                        or len(value["entries"]) > 512):
                    raise ValueError("Invalid cleanup evidence")
                checks = [CleanupEvidence.model_validate(item, strict=True) for item in value["entries"]]
                count = len(latest_unresolved(checks))
                if value["complete"] != (count == 0):
                    raise ValueError("Cleanup summary contradicts evidence")
                cleanup = ActivityCleanupV1(complete=count == 0, unresolved_count=count)
            action_rows = [row for row in rows if row["action_id"] is not None]
            actions = []
            for row in action_rows[:request.limit]:
                def flag(name):
                    if type(row[name]) is not int or row[name] not in (0, 1):
                        raise ValueError("Invalid action evidence flag")
                    return bool(row[name])
                actions.append(ActivityActionV1(action_id=row["action_id"], step_index=row["step_index"],
                    tool=row["tool"], risk=row["risk"], verified=flag("verified"),
                    error_recorded=flag("error_recorded"), policy_denied=flag("policy_denied"),
                    undo_available=flag("undo_available"), rollback_attempted=flag("rollback_attempted"),
                    rollback_ok=None if row["rollback_ok"] is None else flag("rollback_ok")))
            return ActivityPageV1(request_id=request.request_id, task_id=metadata["task_id"],
                task_request_id=metadata["task_request_id"], saved_state=metadata["saved_state"], route=metadata["route"],
                actions=actions, next_action_id=actions[-1].action_id if actions else request.after_action_id,
                has_more=len(action_rows) > request.limit, cleanup=cleanup).model_dump(mode="json")
        except Exception:
            logger.warning("Activity evidence could not be read safely.")
            return failure("ACTIVITY_UNAVAILABLE")

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
        broker = getattr(self, "confirmation_broker", None)
        if broker is not None:
            broker.close()
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
        # Latch task cancellation before draining IPC or resident-owned workers.
        self.supervisor.stop_all_active_tasks()
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
        with self._submission_state():
            submission_threads = list(self._submission_threads.values())
        for thread in submission_threads:
            thread.join(timeout=1.0)
            if thread.is_alive():
                raise RuntimeError("Submitted task owner remains active.")
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
