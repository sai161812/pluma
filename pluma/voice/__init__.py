"""pluma.voice — Voice capture, VAD, STT, and activation interfaces."""

from pluma.voice.activation import VoiceActivation, parse_hotkey_string
from pluma.voice.capture import AudioCapture
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.pipeline import VoicePipeline, is_material_target, normalize_transcript
from pluma.voice.stt_adapter import TranscriptResult, WhisperSttAdapter
from pluma.voice.vad import EnergyVAD

__all__ = [
    "VoiceActivation",
    "parse_hotkey_string",
    "AudioCapture",
    "EnergyVAD",
    "WhisperSttAdapter",
    "TranscriptResult",
    "VoiceLifecycleManager",
    "VoicePipeline",
    "normalize_transcript",
    "is_material_target",
]
