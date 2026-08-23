"""pluma.voice.pipeline — Voice processing pipeline.

Spec §6, §7.1:
  Push-to-talk -> microphone capture -> VAD -> whisper.cpp STT
  -> transcript confidence / sanity checks -> normal PlumaRequest pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from pluma.core.request import InputMode, PlumaRequest
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.vad import EnergyVAD

logger = logging.getLogger(__name__)

# Patterns for detecting material targets (destructive verbs, files, numbers)
_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(delete|remove|format|erase|drop|kill|terminate|overwrite|destroy|wipe)\b",
    re.IGNORECASE,
)
_FILE_EXT_PATTERN = re.compile(
    r"\.(txt|pdf|docx?|xlsx?|pptx?|exe|py|cpp|c|h|json|yaml|yml|csv|log|zip|tar|gz|png|jpg|jpeg)\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(
    r"\b(\d+|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|percent)\b",
    re.IGNORECASE,
)


def is_material_target(text: str) -> bool:
    """Check if command contains material targets (filenames, numbers, destructive actions)."""
    if _DESTRUCTIVE_PATTERN.search(text):
        return True
    if _FILE_EXT_PATTERN.search(text):
        return True
    if _NUMBER_PATTERN.search(text):
        return True
    return False


def normalize_transcript(text: str) -> str:
    """Normalize raw STT transcript minimally for downstream router processing."""
    # Collapse multiple spaces
    normalized = re.sub(r"\s+", " ", text.strip())
    # Strip trailing sentence punctuation if it's a short command (e.g. "open notepad." -> "open notepad")
    if normalized.endswith((".", "!", "?")) and len(normalized.split()) <= 10:
        normalized = normalized[:-1].strip()
    return normalized


class VoicePipeline:
    """Coordinates silence trimming, STT transcription, and PlumaRequest synthesis."""

    def __init__(
        self,
        lifecycle_manager: Optional[VoiceLifecycleManager] = None,
        vad: Optional[EnergyVAD] = None,
    ) -> None:
        self.lifecycle = lifecycle_manager or VoiceLifecycleManager()
        self.vad = vad or EnergyVAD()

    def process_audio(
        self,
        raw_audio: bytes,
        sample_rate: int = 16000,
        cancellation_token: Optional[Any] = None,
    ) -> Optional[PlumaRequest]:
        """Process raw PCM audio bytes and return a PlumaRequest if valid."""
        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            logger.debug("Voice processing aborted: cancellation token set.")
            return None

        if not raw_audio:
            logger.debug("Empty audio buffer received in voice pipeline.")
            return None

        # 1. Trim leading and trailing silence via VAD
        trimmed_audio = self.vad.trim_silence(raw_audio)
        if not trimmed_audio or len(trimmed_audio) < 1600:  # < 50ms of audio
            logger.debug("No speech detected in audio after VAD trimming.")
            return None

        # 2. Check cancellation
        if cancellation_token and hasattr(cancellation_token, "is_cancelled") and cancellation_token.is_cancelled:
            return None

        # 3. Transcribe via on-demand STT lifecycle manager
        stt_result = self.lifecycle.transcribe(
            trimmed_audio,
            sample_rate=sample_rate,
            cancellation_token=cancellation_token,
        )

        raw_text = stt_result.text.strip()
        if not raw_text:
            logger.debug("STT returned empty transcript.")
            return None

        # 4. Normalize transcript
        normalized_text = normalize_transcript(raw_text)
        if not normalized_text:
            return None

        # 5. Low-confidence safety check for material targets
        if stt_result.is_low_confidence and is_material_target(normalized_text):
            logger.warning(
                "Low-confidence STT transcript (%0.2f) detected on material target: '%s'. "
                "Rejecting guess and requiring user clarification.",
                stt_result.confidence,
                normalized_text,
            )
            return None

        # 6. Synthesize PlumaRequest with InputMode.VOICE and preserved original transcript
        request = PlumaRequest(
            input_mode=InputMode.VOICE,
            text=normalized_text,
            original_transcript=raw_text,
        )

        logger.info("Voice utterance transcribed: '%s' (confidence: %0.2f)", normalized_text, stt_result.confidence)
        return request
