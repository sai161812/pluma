"""Real whisper.cpp low-confidence material-target refusal check.

Run on Windows with a 16 kHz mono 16-bit WAV containing a known material
target. The script uses an isolated runtime and never routes the request to the
orchestrator or a tool. Reports contain confidence and booleans only; audio and
recognized text remain in memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import wave

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.voice.pipeline import (
    VoiceClarificationRequired,
    VoicePipeline,
    is_material_target,
)
from pluma.voice.vad import EnergyVAD


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read_audio(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        _assert((source.getframerate(), source.getnchannels(), source.getsampwidth())
                == (16000, 1, 2), "Fixture must be 16 kHz mono signed 16-bit PCM WAV.")
        audio = source.readframes(source.getnframes())
    _assert(320 <= len(audio) <= 16000 * 2 * 30,
            "Fixture audio must fit the bounded 30-second STT input.")
    return audio


class _ObservedLifecycle:
    """Observe only non-sensitive native STT fields for this acceptance run."""

    def __init__(self, lifecycle) -> None:
        self.lifecycle = lifecycle
        self.observation: dict = {}

    def transcribe(self, audio, sample_rate=16000, cancellation_token=None):
        result = self.lifecycle.transcribe(
            audio, sample_rate=sample_rate, cancellation_token=cancellation_token
        )
        self.observation = {
            "confidence": result.confidence,
            "low_confidence": result.is_low_confidence,
            "material_target": is_material_target(result.text),
        }
        return result


def run_acceptance(model_path: Path, sample_path: Path, report_path: Path) -> dict:
    _assert(sys.platform == "win32", "Native material-target acceptance requires Windows.")
    model_path = model_path.resolve()
    sample_path = sample_path.resolve()
    _assert(model_path.is_file() and sample_path.is_file(),
            "Configured local model or explicit test fixture is missing.")
    audio = _read_audio(sample_path)
    root = report_path.parent.resolve() / "material-target-runtime"
    root.mkdir(parents=True, exist_ok=True)
    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["voice"]["required"] = False
    config["voice"]["model_path"] = str(model_path)
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    runtime = PlumaApplicationRuntime(paths=paths, config=config)
    observed = _ObservedLifecycle(runtime.voice_lifecycle)
    pipeline = VoicePipeline(lifecycle_manager=observed, vad=EnergyVAD())
    capsule = runtime.supervisor.create_task_capsule(history_expected=False)
    with model_path.open("rb") as model_file:
        model_sha1 = hashlib.file_digest(model_file, "sha1").hexdigest()
    report = {
        "source": "tests/windows/p14_material_target_acceptance.py",
        "platform": sys.platform,
        "python": sys.version,
        "model_path": str(model_path),
        "model_sha1": model_sha1,
        "sample_path": str(sample_path),
        "sample_sha256": hashlib.sha256(audio).hexdigest(),
        "sample_bytes": len(audio),
        "sample_is_external_or_synthetic_fixture": True,
        "microphone_used": False,
        "transcript_persisted": False,
        "raw_audio_persisted": False,
    }
    try:
        request = pipeline.process_audio(
            audio, cancellation_token=capsule.cancellation_token
        )
        observation = observed.observation
        threshold = runtime.voice_lifecycle.adapter.low_confidence_threshold
        triggered = bool(
            observation.get("low_confidence")
            and observation.get("material_target")
            and isinstance(request, VoiceClarificationRequired)
            and request.code == "LOW_CONFIDENCE_MATERIAL_TARGET"
        )
        report.update({
            "threshold": threshold,
            "confidence": observation.get("confidence"),
            "low_confidence": observation.get("low_confidence", False),
            "material_target_detected": observation.get("material_target", False),
            "clarification_event_emitted": isinstance(request, VoiceClarificationRequired),
            "transcript_attached_to_clarification": False,
            "tool_execution_admitted": False,
            "native_stt_returned_cold": runtime.voice_lifecycle.state == "COLD",
            "low_confidence_material_refused": triggered,
        })
        _assert(triggered,
                "Actual whisper.cpp did not produce a low-confidence material-target refusal.")
        _assert(runtime.voice_lifecycle.state == "COLD",
                "Actual native STT did not return to COLD after the check.")
        report["status"] = "passed"
        return report
    finally:
        audio = b""
        try:
            runtime.supervisor.stop_task(capsule.task_id, grace_s=0)
            _assert(capsule.terminal_ready.wait(timeout=10),
                    "Material-target task cleanup did not finish.")
            _assert(capsule.terminal_persisted is True,
                    "Material-target cleanup was not persisted.")
            cleanup = ActivityQuery(runtime.db).cleanup_report_for_task(capsule.task_id)
            _assert(cleanup is not None, "Material-target cleanup report did not read back.")
            metadata = json.loads(cleanup["metadata_json"])
            report["cleanup_verified"] = any(
                entry.get("code") == "WORKER_ABSENCE_VERIFIED" and entry.get("verified")
                for entry in metadata.get("entries", [])
            )
            _assert(report["cleanup_verified"], "Native STT worker absence was not verified.")
            _assert(ActivityQuery(runtime.db).task_by_id(capsule.task_id) is None,
                    "Refused voice input unexpectedly created a command task row.")
            report["command_task_created"] = False
        finally:
            runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/material-target-acceptance-report.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(args.model, args.sample, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
