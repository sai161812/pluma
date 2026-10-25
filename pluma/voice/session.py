"""One transient capture owner attached before microphone admission.

Device operations serialize separately from the STOP latch. A slow native
close is retained as one bounded shutdown-stage worker, never abandoned.
"""
import threading

from pluma.core.cleanup import CleanupEvidence
from pluma.core.shutdown import ShutdownSession


class VoiceSession:
    def __init__(self, capsule, capture):
        self.capsule = capsule
        self.capture = capture
        self._operation = threading.Lock()
        self._state = threading.Condition()
        self._starting = True
        self._processing = False
        self._released = False
        self._cancel = ShutdownSession()

    @property
    def released(self):
        with self._state:
            return self._released

    @property
    def idle(self):
        with self._state:
            return not self._starting and not self._processing

    def finish_start(self):
        with self._state:
            self._starting = False
            self._state.notify_all()

    def start(self):
        try:
            with self._operation:
                self.capsule.cancellation_token.admit_executor()
                if self.capture is None:
                    raise RuntimeError("Capture is unavailable.")
                self.capture.start()
                if self.capsule.cancellation_token.is_cancelled:
                    self._discard()
        finally:
            self.finish_start()

    def claim_release(self):
        with self._state:
            if self._released:
                return False
            self._released = True
            self._processing = True
            return True

    def finish_release(self):
        with self._state:
            self._processing = False
            self._state.notify_all()

    def stop_and_get(self):
        with self._state:
            if not self._state.wait_for(lambda: not self._starting, 1.0):
                raise RuntimeError("Capture startup remains pending.")
        with self._operation:
            if self.capsule.cancellation_token.is_cancelled:
                self._discard()
                return b""
            audio = self.capture.stop_and_get() if self.capture is not None else b""
            if not self._closed():
                raise RuntimeError("Capture release remains unverified.")
            return audio

    def _closed(self):
        if self.capture is None:
            return True
        # Production adapters expose positive stream/buffer readback. Legacy
        # inert audit fixtures expose recording; unknown state fails closed.
        if hasattr(self.capture, "capture_closed"):
            return self.capture.capture_closed is True
        return getattr(self.capture, "recording", None) is False

    def _discard(self):
        if self.capture is not None:
            if hasattr(self.capture, "cancel"):
                self.capture.cancel()
            else:
                self.capture.stop_and_get()
        if not self._closed():
            raise RuntimeError("Capture closure remains unverified.")

    def cancel_capture(self):
        with self._operation:
            self._discard()

    def cleanup(self, *, stopping):
        try:
            cancelled = self.capsule.cancellation_token.is_cancelled
            if stopping or cancelled:
                result = self._cancel.run([("capture", self.cancel_capture)], timeout_s=0.1)
                verified = result.complete and self.idle and self._closed()
            else:
                verified = self._closed()
        except Exception:
            verified = False
        return CleanupEvidence(resource_id="voice:" + self.capsule.task_id,
            kind="worker", verified=verified,
            code="VOICE_OWNER_CLOSED" if verified else "VOICE_OWNER_PENDING",
            identity={"task_id": self.capsule.task_id, "command_class": "voice"})
