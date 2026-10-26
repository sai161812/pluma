"""Opt-in physical microphone/VAD boundary acceptance for P14 C-02.

Plays an explicitly supplied speech fixture through an explicitly selected
physical output and captures the default physical input. Audio and transcript
remain in memory; the report contains only device names, byte counts and
boundary/cleanup facts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import wave

import numpy as np
import sounddevice as sd

from pluma.voice.capture import AudioCapture
from pluma.voice.vad import EnergyVAD


def _read_fixture(path: Path, gain: float) -> tuple[np.ndarray, int, str]:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        frames = source.readframes(source.getnframes())
    if rate != 16000 or channels != 1 or width != 2:
        raise ValueError("Speech fixture must be 16 kHz mono signed 16-bit PCM WAV.")
    if not 0 < len(frames) <= 16000 * 2 * 30:
        raise ValueError("Speech fixture must be between 1 byte and 30 seconds.")
    pcm = np.frombuffer(frames, dtype="<i2")
    samples = pcm.astype(np.float32) * (gain / 32768.0)
    return samples, rate, hashlib.sha256(frames).hexdigest()


def _output_device(name_part: str, host_api: int) -> tuple[int, str]:
    matches = [
        (index, device)
        for index, device in enumerate(sd.query_devices())
        if name_part.casefold() in device["name"].casefold()
        and device["max_output_channels"] >= 1
        and device["hostapi"] == host_api
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one output device containing {name_part!r}; found {len(matches)}."
        )
    index, device = matches[0]
    return index, device["name"]


def run_acceptance(
    sample_path: Path,
    output_device_part: str,
    repetitions: int = 3,
    gain: float = 0.20,
    silence_wait_s: float = 2.0,
) -> dict:
    if sys.platform != "win32":
        raise RuntimeError("Physical microphone acceptance requires Windows.")
    if repetitions < 3:
        raise ValueError("C-02 physical acceptance requires at least three repetitions.")
    if not 0 < gain <= 1:
        raise ValueError("Playback gain must be in the range (0, 1].")
    sample_path = sample_path.resolve(strict=True)
    samples, sample_rate, sample_sha256 = _read_fixture(sample_path, gain)
    input_index = sd.default.device[0]
    if input_index is None or input_index < 0:
        raise RuntimeError("Windows has no default physical microphone input.")
    input_info = sd.query_devices(input_index)
    input_name = input_info["name"]
    host_apis = sd.query_hostapis()
    input_host_api_name = host_apis[input_info["hostapi"]]["name"]
    output_index, output_name = _output_device(
        output_device_part, input_info["hostapi"]
    )

    report = {
        "source": "tests/windows/p14_voice_boundary_acceptance.py",
        "platform": sys.platform,
        "python": sys.version,
        "sample_path": str(sample_path),
        "sample_pcm_bytes": len(samples) * 2,
        "sample_pcm_sha256": sample_sha256,
        "sample_is_explicit_fixture": True,
        "playback_gain": gain,
        "input_device": input_name,
        "host_api": input_host_api_name,
        "output_device": output_name,
        "repetitions": repetitions,
        "configured_vad_silence_ms": 600,
        "silence_wait_s": silence_wait_s,
        "raw_audio_saved": False,
        "transcript_saved": False,
        "trials": [],
    }
    for trial in range(1, repetitions + 1):
        capture = AudioCapture(vad=EnergyVAD())
        result = {"trial": trial}
        try:
            capture.start()
            time.sleep(0.2)
            sd.play(samples, samplerate=sample_rate, device=output_index, blocking=True)
            time.sleep(silence_wait_s)
            stream = capture._stream
            boundary = capture.utterance_complete
            stream_inactive = stream is not None and stream.active is False
            with capture._lock:
                bytes_at_boundary = len(capture._buffer)
            time.sleep(0.4)
            with capture._lock:
                buffer_stable = bytes_at_boundary == len(capture._buffer)
            audio = capture.stop_and_get()
            result.update({
                "boundary_observed": boundary,
                "physical_stream_inactive_at_boundary": stream_inactive,
                "buffer_stable_after_boundary": buffer_stable,
                "captured_bytes": len(audio),
                "stream_closed_after_release": capture.capture_closed,
            })
            result["passed"] = all((
                boundary,
                stream_inactive,
                buffer_stable,
                capture.capture_closed,
                len(audio) > 0,
            ))
        finally:
            if not capture.capture_closed:
                capture.cancel()
        report["trials"].append(result)

    report["status"] = (
        "passed" if all(trial.get("passed", False) for trial in report["trials"])
        else "failed"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument("--output-device", required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--gain", type=float, default=0.20)
    parser.add_argument("--silence-wait", type=float, default=2.0)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/voice-boundary-acceptance-report.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(
        args.sample, args.output_device, args.repetitions, args.gain, args.silence_wait
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
