"""pluma.voice.vad — Energy-based Voice Activity Detection.

Spec §7.1: VAD / end-of-utterance detection.
Implements a lightweight, zero-ML energy-threshold VAD for 16-bit 16kHz PCM audio.
"""

from __future__ import annotations

import math
import struct
from typing import List


class EnergyVAD:
    """Lightweight energy-threshold voice activity detector for 16-bit PCM audio."""

    def __init__(
        self,
        energy_threshold: float = 350.0,
        sample_rate: int = 16000,
        frame_duration_ms: int = 30,
    ) -> None:
        self.energy_threshold = energy_threshold
        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        # Bytes per frame: sample_rate * (duration / 1000) * 2 bytes (16-bit)
        self.bytes_per_frame = int(self.sample_rate * (self.frame_duration_ms / 1000.0) * 2)

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """Calculate Root Mean Square (RMS) amplitude for 16-bit signed PCM audio."""
        if not pcm_bytes:
            return 0.0
        sample_count = len(pcm_bytes) // 2
        if sample_count == 0:
            return 0.0
        
        # Unpack signed 16-bit little-endian samples
        format_str = f"<{sample_count}h"
        samples = struct.unpack(format_str, pcm_bytes[: sample_count * 2])
        sum_sq = sum(s * s for s in samples)
        return math.sqrt(sum_sq / sample_count)

    def is_speech_present(self, audio_chunk: bytes) -> bool:
        """Check if speech is present in an audio chunk based on energy threshold."""
        return self.calculate_rms(audio_chunk) >= self.energy_threshold

    def split_frames(self, audio: bytes) -> List[bytes]:
        """Split audio buffer into fixed-duration frames."""
        frames: List[bytes] = []
        step = self.bytes_per_frame
        if step <= 0:
            return frames
        for i in range(0, len(audio), step):
            frame = audio[i : i + step]
            if len(frame) == step:
                frames.append(frame)
        return frames

    def trim_silence(self, audio: bytes, padding_ms: int = 150) -> bytes:
        """Trim leading and trailing silence from audio, keeping padding around speech."""
        frames = self.split_frames(audio)
        if not frames:
            return b""

        speech_indices = [
            idx for idx, frame in enumerate(frames)
            if self.is_speech_present(frame)
        ]

        if not speech_indices:
            return b""

        first_speech = speech_indices[0]
        last_speech = speech_indices[-1]

        padding_frames = int(padding_ms / self.frame_duration_ms)
        start_frame = max(0, first_speech - padding_frames)
        end_frame = min(len(frames), last_speech + padding_frames + 1)

        start_byte = start_frame * self.bytes_per_frame
        end_byte = min(len(audio), end_frame * self.bytes_per_frame)
        return audio[start_byte:end_byte]

    def is_utterance_complete(
        self,
        audio: bytes,
        min_speech_duration_ms: int = 300,
        trailing_silence_ms: int = 600,
    ) -> bool:
        """Determine if an utterance is complete by checking for trailing silence after speech."""
        frames = self.split_frames(audio)
        if not frames:
            return False

        trailing_silence_frames = max(1, int(trailing_silence_ms / self.frame_duration_ms))
        min_speech_frames = max(1, int(min_speech_duration_ms / self.frame_duration_ms))

        # Check total frames
        if len(frames) < (min_speech_frames + trailing_silence_frames):
            return False

        # Look for speech in non-trailing frames
        speech_frames_found = 0
        search_limit = len(frames) - trailing_silence_frames
        for frame in frames[:search_limit]:
            if self.is_speech_present(frame):
                speech_frames_found += 1

        if speech_frames_found < min_speech_frames:
            return False

        # Check that all trailing frames are silence
        trailing_frames = frames[search_limit:]
        return all(not self.is_speech_present(f) for f in trailing_frames)
