"""pluma.voice.capture — Microphone capture interface (stub).

Spec §7.1: push-to-talk → microphone capture → VAD.
Implemented in Phase 6. Uses sounddevice per PLUMA_TECH_STACK.md.
Must not import sounddevice at module level (idle runtime law).
"""


class AudioCapture:
    """Stub: microphone capture. Implemented in Phase 6."""

    def start(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        raise NotImplementedError("AudioCapture not implemented until Phase 6.")

    def stop(self) -> bytes:
        raise NotImplementedError("AudioCapture not implemented until Phase 6.")
