"""pluma.voice.pipeline — Voice processing pipeline.

Spec §6, §7.1:
  Push-to-talk -> microphone capture -> VAD -> whisper.cpp STT
  -> transcript confidence / sanity checks -> normal PlumaRequest pipeline.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from pluma.core.request import InputMode, PlumaRequest
from pluma.memory.redaction import redact_command_text
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.vad import EnergyVAD

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceClarificationRequired:
    """Backend outcome for material speech that is too uncertain to execute.

    The transcript and guessed target are deliberately omitted. A later UI can
    present a clarification request without persisting or replaying sensitive
    speech.
    """

    confidence: float
    code: str = "LOW_CONFIDENCE_MATERIAL_TARGET"

# Patterns for detecting material targets (destructive verbs, files, numbers)
_DESTRUCTIVE_PATTERN = re.compile(
    r"\b(delete|remove|format|erase|drop|kill|terminate|overwrite|destroy|wipe)\b",
    re.IGNORECASE,
)
_FILE_EXT_PATTERN = re.compile(r"\b[\w.-]+\.[A-Za-z0-9][A-Za-z0-9_-]{0,15}\b")
_FILE_PATH_PATTERN = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]+\\|(?:^|\s)\.\.?[\\/])"
)
_FILE_MUTATION_PATTERN = re.compile(
    r"\b(move|copy|rename|duplicate|transfer|restore|archive|extract|save|write|create)\b",
    re.IGNORECASE,
)
_FILE_TARGET_PATTERN = re.compile(
    r"\b(file|folder|directory|document|spreadsheet|workbook|photo|image|video|"
    r"script|database|report|filename|path)\b",
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
    if (_DESTRUCTIVE_PATTERN.search(text)
            or _FILE_EXT_PATTERN.search(text)
            or _FILE_PATH_PATTERN.search(text)
            # File mutations with an extensionless target still require the
            # same conservative clarification as targets with known suffixes.
            # App launching (for example, "open notepad") is excluded here.
            or _FILE_MUTATION_PATTERN.search(text)
            or _FILE_TARGET_PATTERN.search(text)):
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
    ) -> Optional[PlumaRequest | VoiceClarificationRequired]:
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
                "Low-confidence STT detected on a material target (%0.2f); refusing to create a request.",
                stt_result.confidence,
            )
            return VoiceClarificationRequired(confidence=stt_result.confidence)

        # 6. Synthesize PlumaRequest with InputMode.VOICE and preserved original transcript
        request = PlumaRequest(
            input_mode=InputMode.VOICE,
            text=normalized_text,
            original_transcript=raw_text,
        )

        logger.info(
            "Voice utterance transcribed: '%s' (confidence: %0.2f)",
            redact_command_text(normalized_text), stt_result.confidence,
        )
        return request
