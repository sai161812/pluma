"""Opt-in P14 acceptance for real task-owned whisper.cpp STT on Windows.

Run from the repository root with the isolated STT environment and explicit
local model/sample paths. The native model and recorded sample stay under the
ignored output directory; this harness never opens a microphone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import threading
import time
import wave

import psutil

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.cancellation import StopReason, TaskCancelledError
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.voice.stt_adapter import MAX_AUDIO_BYTES


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _runtime(model_path: Path, root: Path) -> PlumaApplicationRuntime:
    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["voice"]["required"] = False
    config["voice"]["model_path"] = str(model_path)
    config["runtime"]["stt_idle_unload_seconds"] = 20
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    return PlumaApplicationRuntime(paths=paths, config=config)


def _sample_audio(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        _assert(
            (source.getframerate(), source.getnchannels(), source.getsampwidth())
            == (16000, 1, 2),
            "Recorded fixture must be 16 kHz mono 16-bit PCM.",
        )
        return source.readframes(source.getnframes())


def _cleanup_readback(runtime, capsule, reason: str) -> dict:
    capsule.terminal_ready.wait(timeout=10)
    _assert(capsule.terminal_ready.is_set(), "Task terminal cleanup did not finish.")
    _assert(capsule.terminal_persisted is True, "Task cleanup terminal was not persisted.")
    row = ActivityQuery(runtime.db).cleanup_report_for_task(capsule.task_id)
    _assert(row is not None and row.get("released_at"), "SQLite cleanup release was not read back.")
    metadata = json.loads(row["metadata_json"])
    outcome = metadata.get("pre_execution_outcome", {})
    _assert(outcome.get("final_state") == TaskState.STOPPED.value,
            "Pre-execution fixture task did not record STOPPED.")
    _assert(outcome.get("stop_reason") == reason, "Pre-execution STOP reason was not read back.")
    worker = [entry for entry in metadata["entries"] if entry.get("kind") == "worker"]
    _assert(any(entry.get("code") == "WORKER_ABSENCE_VERIFIED"
                and entry.get("verified") is True for entry in worker),
            "Owned STT worker absence was not recorded as verified.")
    stored = json.dumps(metadata, sort_keys=True).lower()
    _assert("fellow americans" not in stored, "Recorded transcript leaked into cleanup history.")
    return metadata


def _assert_original_process_absent(identity: dict) -> None:
    pid = int(identity["pid"])
    creation_time = float(identity["creation_time"])
    try:
        process = psutil.Process(pid)
        same_process = math.isclose(process.create_time(), creation_time, abs_tol=0.01)
    except psutil.NoSuchProcess:
        same_process = False
    _assert(not same_process, "The task-owned STT process remained alive after STOP.")


def _wait_for_native_worker_cpu(capsule, future_thread: threading.Thread) -> tuple[dict, float]:
    deadline = time.monotonic() + 30.0
    previous = None
    observed = 0.0
    while time.monotonic() < deadline and future_thread.is_alive():
        controller = capsule.worker_controller
        identity = getattr(controller, "worker_identity", None) if controller else None
        if identity and identity.get("pid") and identity.get("creation_time") is not None:
            try:
                process = psutil.Process(int(identity["pid"]))
                current = process.cpu_times()
                total = current.user + current.system
                if previous is not None:
                    observed += max(0.0, total - previous)
                previous = total
                if observed >= 0.15:
                    return dict(identity), observed
            except psutil.NoSuchProcess:
                break
        time.sleep(0.1)
    raise AssertionError(
        "Could not observe active CPU work in the native STT worker before it returned."
    )


def run_acceptance(model_path: Path, sample_path: Path, report_path: Path) -> dict:
    _assert(sys.platform == "win32", "P14 native worker acceptance requires Windows.")
    _assert(model_path.is_file(), f"Local GGML model does not exist: {model_path}")
    _assert(sample_path.is_file(), f"Recorded audio fixture does not exist: {sample_path}")
    audio = _sample_audio(sample_path)
    _assert(0 < len(audio) <= MAX_AUDIO_BYTES, "Recorded fixture exceeds the bounded STT input size.")

    root = report_path.parent / "runtime"
    root.mkdir(parents=True, exist_ok=True)
    runtime = _runtime(model_path, root)
    with model_path.open("rb") as model_file:
        model_sha1 = hashlib.file_digest(model_file, "sha1").hexdigest()
    report = {
        "source": "tests/windows/p14_native_stt_acceptance.py",
        "python": sys.version,
        "platform": sys.platform,
        "pywhispercpp": __import__("importlib.metadata", fromlist=["version"]).version("pywhispercpp"),
        "model_path": str(model_path.resolve()),
        "model_size_bytes": model_path.stat().st_size,
        "model_sha1": model_sha1,
        "recorded_fixture_path": str(sample_path.resolve()),
        "recorded_fixture_sha256": hashlib.sha256(audio).hexdigest(),
        "recorded_fixture_bytes": len(audio),
        "physical_microphone_used": False,
        "tasks": {},
    }
    try:
        _assert(runtime.voice_lifecycle.state == "COLD", "Resident STT lifecycle did not start cold.")
        _assert(not runtime.voice_lifecycle.adapter.is_loaded,
                "Resident process retained native STT weights at startup.")
        _assert("pywhispercpp" not in sys.modules,
                "Resident process imported pywhispercpp before voice inference.")
        _assert(runtime.voice_lifecycle.idle_unload_seconds == 20,
                "Locked runtime STT unload setting was not applied.")

        success_capsule = runtime.supervisor.create_task_capsule(history_expected=False)
        transcript = runtime.voice_lifecycle.transcribe(
            audio, cancellation_token=success_capsule.cancellation_token
        )
        _assert("ask not what your country can do for you" in _normalized(transcript.text),
                "Native whisper.cpp did not recognize the recorded fixture phrase.")
        _assert(transcript.confidence > 0.0 and not transcript.is_low_confidence,
                "Native whisper.cpp confidence was absent, invalid, or below the threshold.")
        _assert(runtime.voice_lifecycle.state == "COLD",
                "STT lifecycle did not return to COLD after inference.")
        _assert(not runtime.voice_lifecycle.adapter.is_loaded,
                "Resident adapter retained native model state after inference.")
        _assert("pywhispercpp" not in sys.modules,
                "Native STT bindings loaded into the resident process.")
        success_controller = success_capsule.worker_controller
        _assert(success_controller is not None and success_controller.worker_identity,
                "Successful STT did not register a native worker identity.")
        success_identity = dict(success_controller.worker_identity)
        runtime.supervisor.stop_task(success_capsule.task_id, grace_s=0)
        success_metadata = _cleanup_readback(
            runtime, success_capsule, StopReason.USER_STOP.value
        )
        _assert(success_controller.verify_cleanup() is True,
                "Successful fixture task worker cleanup did not verify.")
        _assert_original_process_absent(success_identity)
        report["tasks"]["recorded_sample"] = {
            "expected_fixture_phrase_recognized": True,
            "transcript_word_count": len(transcript.text.split()),
            "confidence": transcript.confidence,
            "low_confidence": transcript.is_low_confidence,
            "native_model_reference_released": True,
            "worker_identity": success_identity,
            "cleanup_ledger_verified": True,
            "teardown_stop_reason": success_metadata["pre_execution_outcome"]["stop_reason"],
        }

        stop_capsule = runtime.supervisor.create_task_capsule(history_expected=False)
        repeated_audio = (audio * (MAX_AUDIO_BYTES // len(audio) + 1))[:MAX_AUDIO_BYTES]
        outcome = {}

        def transcribe_until_stopped():
            try:
                runtime.voice_lifecycle.transcribe(
                    repeated_audio,
                    cancellation_token=stop_capsule.cancellation_token,
                )
                outcome["result"] = "returned"
            except TaskCancelledError:
                outcome["result"] = "cancelled"
            except BaseException as exc:
                outcome["result"] = type(exc).__name__

        worker_thread = threading.Thread(
            target=transcribe_until_stopped,
            name="P14NativeSttAcceptance",
            daemon=True,
        )
        worker_thread.start()
        stop_identity, observed_cpu_s = _wait_for_native_worker_cpu(stop_capsule, worker_thread)
        stop_controller = stop_capsule.worker_controller
        _assert(stop_controller is not None, "In-flight STT capsule lost its worker controller.")
        runtime.supervisor.stop_task(stop_capsule.task_id, grace_s=0)
        worker_thread.join(timeout=10)
        _assert(not worker_thread.is_alive(), "Voice inference caller remained after worker STOP.")
        _assert(outcome.get("result") == "cancelled",
                f"In-flight STT did not report cancellation: {outcome.get('result')!r}.")
        _assert(stop_controller.verify_cleanup() is True,
                "STOP did not verify the native worker's process absence.")
        _assert_original_process_absent(stop_identity)
        stop_metadata = _cleanup_readback(runtime, stop_capsule, StopReason.USER_STOP.value)
        report["tasks"]["stop_during_native_stt"] = {
            "native_worker_cpu_seconds_observed": round(observed_cpu_s, 4),
            "worker_identity": stop_identity,
            "caller_returned_cancelled": True,
            "worker_process_absent": True,
            "cleanup_ledger_verified": True,
            "pre_execution_outcome": stop_metadata["pre_execution_outcome"],
        }

        _assert(ActivityQuery(runtime.db).task_by_id(success_capsule.task_id) is None,
                "Transcription-only fixture unexpectedly wrote a command task row.")
        _assert(ActivityQuery(runtime.db).task_by_id(stop_capsule.task_id) is None,
                "Stopped-before-transcript fixture unexpectedly wrote a command task row.")
        _assert(not runtime.tool_registry._worker_controllers,
                "Native STT test left task worker controllers registered.")
        persisted_audio = [
            path for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in {".wav", ".pcm", ".raw"}
        ]
        _assert(not persisted_audio, "The isolated PLUMA runtime persisted raw speech audio.")
        report["status"] = "passed"
        return report
    finally:
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--sample", required=True, type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/acceptance-report-final.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(args.model, args.sample, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
