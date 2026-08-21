"""pluma.voice.vad — Voice Activity Detection interface (stub).

Spec §7.1: VAD / end-of-utterance detection.
Implemented in Phase 6.
"""


class VoiceActivityDetector:
    """Stub: VAD. Implemented in Phase 6."""

    def is_speech_ended(self, audio: bytes) -> bool:
        raise NotImplementedError("VoiceActivityDetector not implemented until Phase 6.")
