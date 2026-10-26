"""Speech-to-text adapter for task-owned local whisper.cpp inference.

Spec §7.1: whisper.cpp local STT. Heavy bindings stay out of the resident
process; each inference runs in the matching task's owned worker.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pluma.voice.capture import MAX_RECORDING_SECONDS

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
MAX_AUDIO_BYTES = SAMPLE_RATE * 2 * int(MAX_RECORDING_SECONDS)
DEFAULT_STT_TIMEOUT_S = 60.0


@dataclass
class TranscriptResult:
    """Outcome of transcribing an audio buffer."""

    text: str
    confidence: float = 0.0
    language: str = "en"
    is_low_confidence: bool = False
    segments: List[Dict[str, Any]] = field(default_factory=list)


class WhisperSttAdapter:
    """On-demand whisper.cpp adapter using the request's owned worker process."""

    def __init__(
        self,
        low_confidence_threshold: float = 0.65,
        *,
        registry: Optional[Any] = None,
        inference_timeout_s: float = DEFAULT_STT_TIMEOUT_S,
    ) -> None:
        if not math.isfinite(inference_timeout_s) or inference_timeout_s <= 0:
            raise ValueError("STT inference timeout must be a positive finite value.")
        self.low_confidence_threshold = low_confidence_threshold
        self.inference_timeout_s = inference_timeout_s
        self._registry = registry
        self._model: Any = None
        self._model_path: Optional[str] = None
        self._lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        """Report only an in-process model reference; production STT is worker-local."""
        with self._lock:
            return self._model is not None

    def load(self, model_path: str, cancellation_token: Optional[Any] = None) -> None:
        """Validate and remember the explicit local GGML model path.

        The native weights are loaded only inside the task worker when inference
        starts. This keeps application startup and the resident adapter cold.
        """
        if cancellation_token is not None and cancellation_token.is_cancelled:
            return
        if not model_path or not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"Whisper model file not found at '{model_path}' (expected GGML). "
                "Set voice.model_path to an installed whisper.cpp GGML model."
            )
        with self._lock:
            self._model_path = model_path

    def unload(self) -> None:
        """Drop any local fixture reference and clear the configured path."""
        with self._lock:
            self._model = None
            self._model_path = None

    def transcribe(
        self,
        audio: bytes,
        sample_rate: int = SAMPLE_RATE,
        cancellation_token: Optional[Any] = None,
    ) -> TranscriptResult:
        """Transcribe bounded int16 mono PCM through the matching task worker."""
        if cancellation_token is not None and cancellation_token.is_cancelled:
            return TranscriptResult(text="", confidence=0.0, is_low_confidence=True)
        if not audio or len(audio) < 320:
            return TranscriptResult(text="", confidence=0.0, is_low_confidence=True)
        if sample_rate != SAMPLE_RATE:
            raise ValueError("Local STT accepts only 16 kHz PCM audio.")
        if len(audio) % 2 or len(audio) > MAX_AUDIO_BYTES:
            raise ValueError("Audio must be an even-byte 16-bit buffer no longer than 30 seconds.")

        with self._lock:
            model_path = self._model_path
            registry = self._registry
        if not model_path:
            raise RuntimeError("Whisper model path is not configured.")
        if registry is None:
            raise RuntimeError("Native STT requires the task-owned worker registry.")
        if cancellation_token is None:
            raise RuntimeError("Native STT requires its owning task cancellation token.")

        cancellation_token.raise_if_cancelled("STT was stopped before worker admission.")
        task_id = getattr(cancellation_token, "task_id", None)
        capsule_ref = getattr(cancellation_token, "_capsule", None)
        capsule = capsule_ref() if callable(capsule_ref) else None
        if capsule is None or not task_id or capsule.task_id != task_id:
            raise RuntimeError("Native STT requires the matching task capsule.")

        from pluma.tools.registry import WorkerRequest, WorkerResponse

        controller = registry.get_worker(task_id)
        capsule.worker_controller = controller
        capsule.tool_registry = registry
        request = WorkerRequest(
            task_id=task_id,
            tool_name="voice_stt",
            validated_args={
                "model_path": model_path,
                "audio": audio,
                "sample_rate": sample_rate,
                "language": "en",
            },
            timeout_s=self.inference_timeout_s,
            supervisor_pid=os.getpid(),
        )
        status, payload = controller.execute_call(
            _native_stt_executor,
            request.validated_args,
            request,
            timeout_s=self.inference_timeout_s,
            job_object=getattr(capsule, "job_object", None),
            cancellation_token=cancellation_token,
        )

        if status in ("cancelled", "timeout"):
            if controller.verify_cleanup() is not True:
                raise RuntimeError("Stopped STT worker cleanup could not be verified.")
            if status == "timeout":
                raise TimeoutError("Local speech transcription exceeded its deadline.")
            from pluma.core.cancellation import TaskCancelledError
            raise TaskCancelledError("Speech transcription was stopped.")
        if cancellation_token.is_cancelled:
            from pluma.core.cancellation import TaskCancelledError
            raise TaskCancelledError("Speech transcription was stopped.")
        if status != "ok" or not isinstance(payload, WorkerResponse):
            raise RuntimeError("Owned local STT worker failed before returning a result.")

        result = payload.result
        data = result.data
        if (not result.ok or data.get("runtime_unloaded") is not True
                or not isinstance(data.get("text"), str)
                or not isinstance(data.get("segments"), list)):
            raise RuntimeError("Local STT inference or model cleanup was not verified.")
        confidence = data.get("confidence")
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
            confidence = 0.0
        confidence = min(1.0, max(0.0, float(confidence)))
        return TranscriptResult(
            text=data["text"],
            confidence=confidence,
            language=str(data.get("language") or "en"),
            is_low_confidence=(confidence < self.low_confidence_threshold),
            segments=data["segments"],
        )


def _native_stt_executor(arguments: Dict[str, Any], task_context: Any):
    """Load, transcribe and release one GGML model inside the task worker."""
    import gc
    import weakref

    from pluma.core.cancellation import TaskCancelledError
    from pluma.tools.base import ToolResult

    cancellation_token = getattr(task_context, "cancellation_token", None)
    if cancellation_token is None:
        return ToolResult.failure("voice_stt", "Task cancellation state is unavailable.",
                                  error_code="STT_OWNERSHIP_UNAVAILABLE")
    cancellation_token.raise_if_cancelled()

    model = None
    model_ref = None
    model_error = False
    text = ""
    segments_out: List[Dict[str, Any]] = []
    probabilities: List[float] = []
    try:
        import numpy as np
        from pywhispercpp.model import Model

        audio = arguments["audio"]
        if (arguments.get("sample_rate") != SAMPLE_RATE or not isinstance(audio, bytes)
                or not audio or len(audio) % 2 or len(audio) > MAX_AUDIO_BYTES):
            return ToolResult.failure("voice_stt", "Audio input failed validation.",
                                      error_code="STT_AUDIO_INVALID")

        model = Model(
            arguments["model_path"],
            n_threads=min(4, max(1, (os.cpu_count() or 4) // 2)),
            redirect_whispercpp_logs_to=None,
            print_progress=False,
            print_realtime=False,
            print_timestamps=False,
        )
        model_ref = weakref.ref(model)
        cancellation_token.raise_if_cancelled()
        samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
        whisper_segments = model.transcribe(
            samples,
            language=arguments["language"],
            abort_callback=lambda: cancellation_token.is_cancelled,
            extract_probability=True,
            print_progress=False,
            print_realtime=False,
            print_timestamps=False,
        )
        cancellation_token.raise_if_cancelled()

        transcript_parts: List[str] = []
        for segment in whisper_segments:
            segment_text = getattr(segment, "text", "")
            if not isinstance(segment_text, str):
                segment_text = ""
            transcript_parts.append(segment_text)
            try:
                probability = float(getattr(segment, "probability"))
            except (AttributeError, TypeError, ValueError):
                probability = 0.0
            if not math.isfinite(probability):
                probability = 0.0
            probability = min(1.0, max(0.0, probability))
            if segment_text.strip():
                probabilities.append(probability)
            segments_out.append({
                "text": segment_text,
                "t0": getattr(segment, "t0", 0),
                "t1": getattr(segment, "t1", 0),
                "probability": probability,
            })
        text = " ".join(part.strip() for part in transcript_parts if part.strip())
    except TaskCancelledError:
        raise
    except Exception:
        # Never write raw audio, transcript text, or local model details to logs.
        logger.warning("Native whisper.cpp transcription failed.")
        model_error = True
    finally:
        model = None
        gc.collect()

    runtime_unloaded = model_ref is None or model_ref() is None
    if not runtime_unloaded:
        return ToolResult.failure("voice_stt", "Whisper model release could not be verified.",
                                  error_code="STT_MODEL_UNLOAD_UNVERIFIED")
    if model_error:
        return ToolResult.failure("voice_stt", "Local speech transcription failed.",
                                  error_code="STT_NATIVE_FAILED")

    # A weak segment can contain the target that determines what the command
    # will act on. The mean can hide that risk behind unrelated strong speech,
    # so expose the weakest nonempty segment as the conservative request score.
    confidence = min(probabilities) if probabilities else 0.0
    return ToolResult.success(
        "voice_stt",
        data={
            "text": text,
            "confidence": confidence,
            "language": arguments["language"],
            "segments": segments_out,
            "runtime_unloaded": runtime_unloaded,
        },
        factual_message="Local transcription completed and the Whisper model reference was released.",
        verified=False,
    )
