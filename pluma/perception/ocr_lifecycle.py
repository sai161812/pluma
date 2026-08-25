"""pluma.perception.ocr_lifecycle — On-demand OCR lifecycle manager.

Spec §4 Zero-ML-at-idle law: OCR models must not reside in memory during idle.
Spec §8.3: "On-demand local OCR worker."

State machine:
  COLD -> LOADING -> WARM -> RUNNING -> WARM (after run completes)
  WARM -> UNLOADING -> COLD (after idle timeout or shutdown)

Boundary: paddleocr/onnxruntime must never be imported at module level.
"""

from __future__ import annotations

import logging
import threading
from enum import Enum, auto
from typing import Optional

from pluma.perception.ocr_adapter import OcrAdapter, OcrBackend, OcrResult
from pluma.perception.element_refs import BoundingBox
from pluma.core.cancellation import CancellationToken, TaskCancelledError

logger = logging.getLogger(__name__)

# Default unload after 10 seconds of idle
DEFAULT_IDLE_UNLOAD_SECONDS: float = 10.0


class OcrLifecycleState(str, Enum):
    """States of the OcrLifecycleManager state machine."""
    COLD = "COLD"           # Model not loaded; zero memory footprint.
    LOADING = "LOADING"     # Model is being loaded in background.
    WARM = "WARM"           # Model loaded and ready.
    RUNNING = "RUNNING"     # OCR recognition in progress.
    UNLOADING = "UNLOADING" # Model being freed.


class OcrModelNotReadyError(RuntimeError):
    """Raised if OCR is requested while the lifecycle manager is loading."""


class OcrLifecycleManager:
    """Manages the warm/cold lifecycle of the OCR backend.

    Loads on demand, then automatically unloads after idle_unload_seconds
    of inactivity.  Thread-safe.
    """

    def __init__(
        self,
        idle_unload_seconds: float = DEFAULT_IDLE_UNLOAD_SECONDS,
        custom_backend: Optional[OcrBackend] = None,
    ) -> None:
        self._idle_unload_seconds = idle_unload_seconds
        self._adapter = OcrAdapter(custom_backend=custom_backend)
        self._state = OcrLifecycleState.COLD
        self._lock = threading.Lock()
        self._idle_timer: Optional[threading.Timer] = None

    @property
    def state(self) -> OcrLifecycleState:
        with self._lock:
            return self._state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_ocr(
        self,
        image_bytes: bytes,
        cancellation_token: Optional[CancellationToken] = None,
    ) -> OcrResult:
        """Load OCR model if needed and run recognition on *image_bytes*.

        This is the primary entry point. The image bytes are ephemeral and
        are not stored by this class.

        Raises:
            TaskCancelledError: If cancellation is requested.
        """
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

        self._ensure_warm()

        with self._lock:
            self._cancel_idle_timer()
            self._state = OcrLifecycleState.RUNNING

        try:
            result = self._adapter.run(image_bytes, cancellation_token=cancellation_token)
        finally:
            with self._lock:
                # Return to WARM only if we're still RUNNING (not shut down)
                if self._state == OcrLifecycleState.RUNNING:
                    self._state = OcrLifecycleState.WARM
                    self._schedule_idle_unload()

        return result

    def shutdown(self) -> None:
        """Immediately unload the OCR model and cancel any pending timers."""
        with self._lock:
            self._cancel_idle_timer()
            if self._state in (OcrLifecycleState.WARM, OcrLifecycleState.RUNNING):
                self._state = OcrLifecycleState.UNLOADING

        # Unload outside the lock to avoid deadlock
        try:
            self._adapter.unload()
        except Exception as exc:
            logger.debug("OCR unload error during shutdown: %s", exc)

        with self._lock:
            self._state = OcrLifecycleState.COLD
        logger.info("OcrLifecycleManager: shutdown complete (COLD).")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_warm(self) -> None:
        """Load the OCR model synchronously if currently COLD."""
        with self._lock:
            if self._state == OcrLifecycleState.WARM:
                return
            if self._state == OcrLifecycleState.RUNNING:
                return  # Another thread already running; proceed
            if self._state == OcrLifecycleState.LOADING:
                raise OcrModelNotReadyError("OCR model is still loading.")
            if self._state in (
                OcrLifecycleState.COLD,
                OcrLifecycleState.UNLOADING,
            ):
                self._state = OcrLifecycleState.LOADING

        # Load outside the lock
        logger.info("OcrLifecycleManager: loading OCR model (COLD -> WARM).")
        try:
            self._adapter.load()
        except Exception as exc:
            with self._lock:
                self._state = OcrLifecycleState.COLD
            raise RuntimeError(f"Failed to load OCR model: {exc}") from exc

        with self._lock:
            self._state = OcrLifecycleState.WARM
        logger.info("OcrLifecycleManager: OCR model warm and ready.")

    def _schedule_idle_unload(self) -> None:
        """Schedule an idle unload timer. Must be called while holding self._lock."""
        self._idle_timer = threading.Timer(
            self._idle_unload_seconds,
            self._idle_unload_callback,
        )
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        """Cancel any scheduled idle unload. Must be called while holding self._lock."""
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _idle_unload_callback(self) -> None:
        """Unload callback fired by the idle timer."""
        with self._lock:
            if self._state != OcrLifecycleState.WARM:
                return  # Already unloading or running — skip
            self._state = OcrLifecycleState.UNLOADING

        logger.info(
            "OcrLifecycleManager: idle timeout (%.1fs) — unloading OCR model.",
            self._idle_unload_seconds,
        )
        try:
            self._adapter.unload()
        except Exception as exc:
            logger.debug("OCR idle unload error: %s", exc)

        with self._lock:
            self._state = OcrLifecycleState.COLD
        logger.info("OcrLifecycleManager: OCR model unloaded (COLD).")


# ---------------------------------------------------------------------------
# Process-wide Default Instance
# ---------------------------------------------------------------------------

_default_ocr_manager: Optional[OcrLifecycleManager] = None
_default_ocr_manager_lock = threading.Lock()


def get_default_ocr_lifecycle_manager() -> OcrLifecycleManager:
    """Get or create the default process-wide OCR lifecycle manager."""
    global _default_ocr_manager
    with _default_ocr_manager_lock:
        if _default_ocr_manager is None:
            _default_ocr_manager = OcrLifecycleManager()
        return _default_ocr_manager


def set_default_ocr_lifecycle_manager(manager: Optional[OcrLifecycleManager]) -> None:
    """Override or reset the default process-wide OCR lifecycle manager."""
    global _default_ocr_manager
    with _default_ocr_manager_lock:
        if _default_ocr_manager is not None and _default_ocr_manager is not manager:
            _default_ocr_manager.shutdown()
        _default_ocr_manager = manager
