"""Opt-in physical microphone checks for P14 C-01 and C-07.

Uses the real Windows default input only during explicit push-to-talk events.
Captured PCM stays in process memory, is reduced to a byte count by an inert
pipeline, and is never written to disk or passed to a command executor.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys
import time

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _DiscardingPipeline:
    def __init__(self) -> None:
        self.observed_audio_bytes: list[int] = []

    def process_audio(self, raw_audio: bytes, cancellation_token=None):
        self.observed_audio_bytes.append(len(raw_audio))
        return None


def _cleanup(runtime: PlumaApplicationRuntime, capsule) -> dict:
    _assert(capsule.terminal_ready.wait(timeout=10), "Voice task did not reach terminal cleanup.")
    _assert(capsule.terminal_persisted is True, "Voice cleanup was not persisted.")
    row = ActivityQuery(runtime.db).cleanup_report_for_task(capsule.task_id)
    _assert(row is not None and row.get("released_at"), "Voice cleanup readback is missing.")
    return json.loads(row["metadata_json"])


def run_acceptance(model_path: Path, report_path: Path) -> dict:
    _assert(sys.platform == "win32", "Physical microphone acceptance requires Windows.")
    _assert(model_path.is_file(), "Configured local whisper.cpp model is missing.")
    _assert("sounddevice" not in sys.modules, "Audio dependency loaded before activation.")

    root = report_path.parent / "device-runtime"
    root.mkdir(parents=True, exist_ok=True)
    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["voice"]["required"] = True
    config["voice"]["model_path"] = str(model_path)
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    runtime = PlumaApplicationRuntime(paths=paths, config=config)
    probe = _DiscardingPipeline()
    core = runtime.resident_core
    core.voice_pipeline = probe
    capture = core.audio_capture
    activation = core.voice_activation
    _assert(capture is not None and activation is not None, "Push-to-talk capture is not configured.")
    _assert(capture.capture_closed, "Microphone capture was open before push-to-talk activation.")
    report = {
        "source": "tests/windows/p14_voice_device_acceptance.py",
        "python": sys.version,
        "platform": sys.platform,
        "sounddevice": importlib.metadata.version("sounddevice"),
        "physical_device_used": True,
        "audio_saved": False,
        "transcript_recorded": False,
    }
    try:
        _assert("sounddevice" not in sys.modules, "Audio dependency imported before PTT activation.")
        activation.trigger_press()
        first_capsule = core._current_voice_capsule
        first_stream = capture._stream
        _assert(first_stream is not None and capture.is_recording,
                "PTT activation did not open the physical input stream.")
        import sounddevice as sd
        report["physical_input_device"] = sd.query_devices(sd.default.device[0])["name"]
        time.sleep(0.35)
        activation.trigger_release()
        first_cleanup = _cleanup(runtime, first_capsule)
        _assert(capture.capture_closed, "PTT release left the physical input stream open.")
        _assert(first_capsule.state == TaskState.STOPPED,
                "Inert physical capture unexpectedly dispatched a command.")
        _assert(ActivityQuery(runtime.db).task_by_id(first_capsule.task_id) is None,
                "Inert microphone capture unexpectedly wrote a command task.")

        observed_bytes = sum(probe.observed_audio_bytes)
        report["push_to_talk_capture"] = {
            "capture_closed_before_activation": True,
            "stream_opened_after_activation": True,
            "stream_closed_after_release": True,
            "pcm_bytes_observed_in_memory": observed_bytes,
            "raw_audio_persisted": False,
            "cleanup_readback": first_cleanup.get("pre_execution_outcome", {}),
        }

        activation.trigger_press()
        stop_capsule = core._current_voice_capsule
        stop_stream = capture._stream
        _assert(stop_stream is not None and capture.is_recording,
                "Second PTT activation did not open capture for STOP acceptance.")
        time.sleep(0.2)
        observed_calls = len(probe.observed_audio_bytes)
        runtime.supervisor.stop_task(stop_capsule.task_id, grace_s=0)
        stop_cleanup = _cleanup(runtime, stop_capsule)
        _assert(stop_capsule.state == TaskState.STOPPED,
                "STOP during physical capture did not produce STOPPED.")
        _assert(capture.capture_closed and bool(getattr(stop_stream, "closed", False)),
                "STOP did not close and read back the physical input stream.")
        _assert(len(probe.observed_audio_bytes) == observed_calls,
                "Capture STOP passed audio to voice processing after the latch.")
        _assert(ActivityQuery(runtime.db).task_by_id(stop_capsule.task_id) is None,
                "Capture STOP unexpectedly admitted a command task.")
        worker_entries = [entry for entry in stop_cleanup.get("entries", [])
                          if entry.get("kind") == "worker"]
        _assert(any(entry.get("code") == "VOICE_OWNER_CLOSED" and entry.get("verified")
                    for entry in worker_entries),
                "STOP cleanup did not read back voice capture closure.")
        report["stop_during_capture"] = {
            "physical_stream_closed": True,
            "no_voice_processing_after_stop": True,
            "cleanup_readback": stop_cleanup.get("pre_execution_outcome", {}),
        }
        activation.trigger_release()
        report["status"] = "passed"
        return report
    finally:
        if activation.is_active:
            activation.trigger_release()
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/device-acceptance-report.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(args.model, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
