"""pluma.voice.stt_adapter — STT adapter interface (stub).

Spec §7.1: whisper.cpp local STT.
PLUMA_TECH_STACK.md: whisper.cpp, quantized local Whisper model.
Must NOT import whisper bindings at module level (idle runtime law).
Implemented in Phase 6.
"""


class SttAdapter:
    """Stub: whisper.cpp STT adapter. Implemented in Phase 6."""

    def transcribe(self, audio: bytes) -> str:
        raise NotImplementedError("SttAdapter not implemented until Phase 6.")
