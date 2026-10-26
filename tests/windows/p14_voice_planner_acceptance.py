"""Native STT-to-planner acceptance using an explicit generated speech fixture.

Uses the real local llama.cpp model and a bounded read-only owned directory.
The audio is transcribed by local whisper.cpp, then the resulting voice request
uses the same task capsule for native Qwen planning. No microphone is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid
import wave

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteMode
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.voice.pipeline import VoicePipeline


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _read_audio(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        _assert((source.getframerate(), source.getnchannels(), source.getsampwidth())
                == (16000, 1, 2), "Speech fixture must be 16 kHz mono signed 16-bit PCM WAV.")
        audio = source.readframes(source.getnframes())
    _assert(320 <= len(audio) <= 16000 * 2 * 30,
            "Speech fixture must fit the bounded native STT input.")
    return audio


def _file_digest(path: Path, algorithm: str) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, algorithm).hexdigest()


class _ObservedLifecycle:
    """Observe confidence only while delegating to the configured native STT."""

    def __init__(self, lifecycle) -> None:
        self.lifecycle = lifecycle
        self.confidence = None
        self.low_confidence = None

    def transcribe(self, audio, sample_rate=16000, cancellation_token=None):
        result = self.lifecycle.transcribe(
            audio, sample_rate=sample_rate, cancellation_token=cancellation_token
        )
        self.confidence = result.confidence
        self.low_confidence = result.is_low_confidence
        return result


def _run_task(runtime, request, expected_mode: str, capsule=None) -> dict:
    result = runtime.orchestrator.execute(request, capsule=capsule)
    _assert(result.route == RouteMode.SMART, f"Expected SMART route, got {result.route}.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"Native planner task failed: {result.error or result.factual_summary}")
    expected_tools = ["run_powershell"]
    _assert([step.tool for step in result.steps] == expected_tools,
            "Voice/text planner did not select the fixed read-only diagnostic.")
    _assert(all(step.result.ok and step.result.verified for step in result.steps),
            "A read-only fixture tool was not verified.")
    _assert(result.completion_verified and result.terminal_persisted is True,
            "Task terminal/ledger completion was not verified.")
    _assert(runtime.llm_lifecycle.state.value == "COLD",
            "Task-owned planner was not released after the request.")
    _assert(not runtime.tool_registry._worker_controllers,
            f"Task-owned planner/tool worker remains registered: "
            f"{list(runtime.tool_registry._worker_controllers)}")
    _assert("llama_cpp" not in sys.modules,
            "Planner runtime loaded into the resident process.")

    query = ActivityQuery(runtime.db)
    task = query.task_by_id(result.task_id)
    actions = query.actions_for_task(result.task_id)
    _assert(task is not None and task["input_mode"] == expected_mode,
            "Task input mode did not read back from SQLite.")
    _assert(task["final_state"] == TaskState.SUCCEEDED.value,
            "Task final state did not read back from SQLite.")
    _assert(task.get("original_transcript") == request.original_transcript,
            "Original voice transcript metadata did not read back from SQLite.")
    _assert([action["tool"] for action in actions] == expected_tools,
            "Registered tool sequence did not read back from SQLite.")
    action_arguments = [json.loads(action["args_json_sanitized"])["args"] for action in actions]
    _assert(action_arguments[0] == {"command_id": "os_version"},
            "Planner did not select the fixed read-only OS-version diagnostic.")
    _assert(any(item.get("code") == "WORKER_ABSENCE_VERIFIED"
                for item in result.cleanup_evidence),
            "Planner worker absence was not verified.")
    return {
        "task_id": result.task_id,
        "input_mode": expected_mode,
        "route": result.route.value,
        "tools": [step.tool for step in result.steps],
        "command_scope": "fixed read-only os_version diagnostic",
        "ledger_verified": True,
        "worker_absence_verified": True,
    }


def run_acceptance(model_path: Path, stt_model_path: Path,
                   speech_sample_path: Path, report_path: Path) -> dict:
    _assert(sys.platform == "win32", "P14 native planner acceptance requires Windows.")
    model_path = model_path.resolve()
    stt_model_path = stt_model_path.resolve()
    speech_sample_path = speech_sample_path.resolve()
    _assert(model_path.is_file(), "Configured local GGUF model is missing.")
    _assert(stt_model_path.is_file(), "Configured local Whisper GGML model is missing.")
    _assert(speech_sample_path.is_file(), "Generated speech fixture is missing.")
    audio = _read_audio(speech_sample_path)
    root = report_path.parent.resolve() / f"planner-runtime-native-stt-{uuid.uuid4().hex}"
    root.mkdir(parents=True, exist_ok=True)
    fixture_dir = root / "owned-fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["brain"]["model_path"] = str(model_path)
    config["agent"]["max_plan_steps"] = 8
    config["runtime"]["model_idle_unload_seconds"] = 30
    config["voice"]["required"] = False
    config["voice"]["model_path"] = str(stt_model_path)
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    runtime = PlumaApplicationRuntime(paths=paths, config=config)
    try:
        capsule = runtime.supervisor.create_task_capsule()
        observed = _ObservedLifecycle(runtime.voice_lifecycle)
        pipeline = VoicePipeline(
            lifecycle_manager=observed,
            vad=runtime.voice_pipeline.vad,
        )
        previous_cwd = Path.cwd()
        os.chdir(fixture_dir)
        try:
            voice_request = pipeline.process_audio(
                audio, cancellation_token=capsule.cancellation_token
            )
            _assert(isinstance(voice_request, PlumaRequest)
                    and voice_request.input_mode == InputMode.VOICE,
                    "Native Whisper did not create a routable voice request.")
            _assert(voice_request.text and voice_request.original_transcript,
                    "Native voice request lost its transcript metadata.")
            _assert(observed.confidence is not None and observed.low_confidence is not None,
                    "Native Whisper confidence was not returned.")
            _assert(runtime.voice_lifecycle.state == "COLD",
                    "Native Whisper did not return to COLD before planning.")
            capsule.request_id = str(voice_request.request_id)
            typed_request = PlumaRequest.from_text(voice_request.text)

            report = {
                "source": "tests/windows/p14_voice_planner_acceptance.py",
                "python": sys.version,
                "platform": sys.platform,
                "llama_cpp_python": __import__("importlib.metadata", fromlist=["version"]).version(
                    "llama-cpp-python"
                ),
                "model_path": str(model_path.resolve()),
                "model_size_bytes": model_path.stat().st_size,
                "model_sha256": _file_digest(model_path, "sha256"),
                "stt_model_path": str(stt_model_path),
                "stt_model_size_bytes": stt_model_path.stat().st_size,
                "stt_model_sha1": _file_digest(stt_model_path, "sha1"),
                "speech_sample_path": str(speech_sample_path),
                "speech_sample_sha256": hashlib.sha256(audio).hexdigest(),
                "speech_sample_bytes": len(audio),
                "input": "generated speech fixture transcribed by native Whisper; no microphone opened",
                "native_stt_confidence": observed.confidence,
                "native_stt_low_confidence": observed.low_confidence,
                "transcript_saved_in_report": False,
                "synthetic_transcript_read_back_from_ledger": True,
                "raw_audio_saved": False,
                "tasks": {},
            }
            report["tasks"]["voice"] = _run_task(
                runtime, voice_request, "voice", capsule=capsule
            )
            report["tasks"]["text"] = _run_task(runtime, typed_request, "text")
        finally:
            os.chdir(previous_cwd)
        voice_task, text_task = report["tasks"]["voice"], report["tasks"]["text"]
        _assert(voice_task["route"] == text_task["route"] == "SMART",
                "Voice and text equivalents selected different routes.")
        _assert(voice_task["tools"] == text_task["tools"],
                "Voice and text equivalents selected different registered tools.")
        report["voice_text_route_tool_parity"] = True
        report["same_task_capsule_for_stt_and_planner"] = True
        report["status"] = "passed"
        return report
    finally:
        audio = b""
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--stt-model", required=True, type=Path)
    parser.add_argument("--speech-sample", required=True, type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/voice-planner-acceptance-report.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(args.model, args.stt_model, args.speech_sample, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
