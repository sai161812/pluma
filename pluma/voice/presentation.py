"""One volatile voice generation, read on demand without subscribers or storage."""
import threading
import time
from uuid import uuid4

from pluma.core.ipc_contracts import VoiceViewV1
from pluma.memory.redaction import redact_command_text

TERMINAL_RETENTION_S = 30.0
_ACTIVE = {"STARTING", "LISTENING", "DECODING"}


class VoicePresentation:
    def __init__(self, task_id, token, *, clock=time.monotonic):
        self.voice_id = str(uuid4())
        self.task_id = task_id
        self._token = token
        self._clock = clock
        self._lock = threading.Lock()
        self._phase = "STARTING"
        self._code = None
        self._request_id = None
        self._text = ""
        self._finished_at = None

    def _cancel_locked(self):
        if self._phase in _ACTIVE and self._token.is_cancelled:
            reason = getattr(getattr(self._token, "reason", None), "value", None)
            phase = "TIMED_OUT" if reason == "task_timeout" else "ERROR" if reason in {"internal_error", "policy_deny"} else "CANCELLED"
            self._set_locked(phase, "VOICE_FAILED" if phase == "ERROR" else None)

    def _set_locked(self, phase, code=None):
        self._phase, self._code = phase, code
        if phase not in _ACTIVE:
            self._finished_at = self._clock()
        if phase != "COMMITTED":
            self._text = ""

    def listening(self):
        with self._lock:
            self._cancel_locked()
            if self._phase == "STARTING":
                self._set_locked("LISTENING")

    def decoding(self):
        with self._lock:
            self._cancel_locked()
            if self._phase == "LISTENING":
                self._set_locked("DECODING")

    def finish(self, phase, code=None):
        if (phase, code) not in {("EMPTY", None), ("CLARIFICATION", "LOW_CONFIDENCE_MATERIAL_TARGET"),
                                ("ERROR", "CAPTURE_DENIED"), ("ERROR", "CAPTURE_UNAVAILABLE"),
                                ("ERROR", "VOICE_FAILED")}:
            raise ValueError("Invalid voice outcome.")
        with self._lock:
            self._cancel_locked()
            if self._phase in _ACTIVE:
                self._set_locked(phase, code)

    def committed(self, request, *, capsule):
        # Called only after the orchestrator has entered its execution gate and
        # successfully started this same capsule. Recognition alone never calls it.
        if (capsule.task_id != self.task_id or capsule.cancellation_token is not self._token
                or str(request.request_id) != str(capsule.request_id)):
            raise ValueError("Voice commitment owner mismatch.")
        with self._lock:
            self._cancel_locked()
            if self._phase == "DECODING":
                self._request_id = str(request.request_id)
                text = redact_command_text(request.text)
                self._text = text if len(text.encode("utf-8")) <= 16384 else ""
                self._set_locked("COMMITTED")

    def snapshot(self, capsule, capture):
        if capsule.task_id != self.task_id or capsule.cancellation_token is not self._token:
            raise ValueError("Voice observation owner mismatch.")
        if not self._lock.acquire(timeout=.02):
            raise TimeoutError("Voice observation is busy.")
        try:
            self._cancel_locked()
            if self._finished_at is not None and self._clock() - self._finished_at >= TERMINAL_RETENTION_S:
                self._text = ""
                return None
            active = boundary = None
            if self._phase == "LISTENING":
                observe = getattr(capture, "observation", None)
                if callable(observe):
                    active, boundary = observe()
            recognition_id, sequence, text = None, 0, self._text
            progress = capsule.recognition_progress
            if self._phase == "DECODING" and progress is not None:
                result = progress.snapshot()
                if result.task_id != self.task_id:
                    raise ValueError("Recognition owner mismatch.")
                recognition_id, sequence = result.recognition_id, result.sequence
                text = result.text if result.state in {"DECODING", "RECOGNIZED"} else ""
            # Latch may race observation, but cannot publish an already observed
            # cancellation as listening/decoding or leak its recognition text.
            self._cancel_locked()
            if self._phase not in {"DECODING", "COMMITTED"}:
                text = ""
            if self._phase != "LISTENING":
                active = boundary = None
            return VoiceViewV1(voice_id=self.voice_id, task_id=self.task_id,
                task_request_id=self._request_id, phase=self._phase, code=self._code,
                capture_active=active, boundary_complete=boundary,
                recognition_id=recognition_id, recognition_sequence=sequence, text=text)
        finally:
            self._lock.release()
