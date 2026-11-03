"""Volatile, bounded recognition evidence; never a request or ledger event."""
from dataclasses import dataclass
import threading
from uuid import uuid4
from typing import Literal

from pluma.memory.redaction import redact_command_text

MAX_SEGMENTS = 128
MAX_SEGMENT_BYTES = 4096
MAX_TRANSCRIPT_BYTES = 16384


def validate_segment(sequence, text):
    if (type(sequence) is not int or not 1 <= sequence <= MAX_SEGMENTS
            or type(text) is not str or not text.strip()
            or len(text.encode("utf-8")) > MAX_SEGMENT_BYTES):
        raise ValueError("Invalid recognition segment.")


@dataclass(frozen=True)
class RecognitionSnapshot:
    recognition_id: str
    task_id: str
    state: Literal["DECODING", "RECOGNIZED", "EMPTY", "FAILED", "CANCELLED", "TIMED_OUT", "UNAVAILABLE"]
    sequence: int
    text: str


class RecognitionProgress:
    """One inference generation. A final recognition is not execution admission.

    Raw incremental text is private in-memory data needed to redact the entire
    prefix. Only redacted copy leaves snapshot(); no observer threads or logs.
    Cancellation is read before publication and snapshot, without waiting on a
    UI subscriber. Terminal failure/STOP clears text rather than replaying it.
    """
    def __init__(self, task_id, token):
        self.recognition_id = str(uuid4())
        self.task_id = task_id
        self._token = token
        self._lock = threading.Lock()
        self._state = "DECODING"
        self._sequence = 0
        self._raw = ""
        self._text = ""

    def _cancel_state(self):
        reason = getattr(getattr(self._token, "reason", None), "value", None)
        return "TIMED_OUT" if reason == "task_timeout" else "FAILED" if reason in {"internal_error", "policy_deny"} else "CANCELLED"

    def accept(self, sequence, text):
        validate_segment(sequence, text)
        with self._lock:
            if self._token.is_cancelled or self._state != "DECODING":
                return
            if sequence != self._sequence + 1:
                raise ValueError("Recognition sequence is not contiguous.")
            candidate = (self._raw + " " + text.strip()).strip()
            self._sequence = sequence
            if len(candidate.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
                self._state, self._raw, self._text = "UNAVAILABLE", "", ""
                return
            self._raw = candidate
            self._text = redact_command_text(candidate)

    def finish(self, state, text=""):
        if state not in {"RECOGNIZED", "FAILED", "CANCELLED", "TIMED_OUT"}:
            raise ValueError("Invalid recognition outcome.")
        with self._lock:
            if self._state in {"FAILED", "CANCELLED", "TIMED_OUT"}:
                return
            self._raw = ""
            self._text = ""
            if self._token.is_cancelled:
                state = self._cancel_state()
            if state == "RECOGNIZED":
                if not text.strip():
                    state = "EMPTY"
                elif len(text.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
                    state = "UNAVAILABLE"
                else:
                    self._text = redact_command_text(text)
            self._state = state

    def snapshot(self):
        if not self._lock.acquire(timeout=.02):
            raise TimeoutError("Recognition observation is busy.")
        try:
            if self._token.is_cancelled:
                self._raw = self._text = ""
                self._state = self._cancel_state()
            return RecognitionSnapshot(self.recognition_id, self.task_id, self._state, self._sequence, self._text)
        finally:
            self._lock.release()
