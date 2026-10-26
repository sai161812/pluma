"""Native planner parity for fixture-transcribed voice and typed requests.

Uses the real local llama.cpp model and a bounded read-only owned directory.
The transcript is injected by an explicit fixture; no microphone is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteMode
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.voice.pipeline import VoicePipeline
from pluma.voice.stt_adapter import TranscriptResult
from pluma.voice.vad import EnergyVAD


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _tone() -> bytes:
    import math
    import struct

    count = 16000 // 2
    samples = [int(6000 * math.sin(2 * math.pi * 440 * index / 16000))
               for index in range(count)]
    return struct.pack(f"<{count}h", *samples)


class _FixtureTranscript:
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe(self, _audio, sample_rate=16000, cancellation_token=None):
        _assert(sample_rate == 16000, "Voice fixture used an unexpected sample rate.")
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()
        return TranscriptResult(text=self.text, confidence=0.92, is_low_confidence=False)


def _run_task(runtime, request, expected_mode: str, fixture_dir: Path) -> dict:
    result = runtime.orchestrator.execute(request)
    _assert(result.route == RouteMode.SMART, f"Expected SMART route, got {result.route}.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"Native planner task failed: {result.error or result.factual_summary}")
    expected_tools = ["list_folder", "file_info"]
    _assert([step.tool for step in result.steps] == expected_tools,
            "Voice/text planner did not select the requested two-step read-only plan.")
    _assert(all(step.result.ok and step.result.verified for step in result.steps),
            "A read-only fixture tool was not verified.")
    _assert(result.completion_verified and result.terminal_persisted is True,
            "Task terminal/ledger completion was not verified.")
    _assert(runtime.llm_lifecycle.state.value == "COLD",
            "Task-owned planner was not released after the request.")
    _assert(not runtime.tool_registry._worker_controllers,
            "Task-owned planner/tool worker remains registered.")
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
    expected_paths = [fixture_dir, fixture_dir / "voice-fixture.txt"]
    for action, expected_path in zip(actions, expected_paths, strict=True):
        arguments = json.loads(action["args_json_sanitized"])["args"]
        _assert(Path(arguments["path"]).resolve() == expected_path.resolve(),
                "Planner action escaped or changed the owned fixture path.")
    _assert(any(item.get("code") == "WORKER_ABSENCE_VERIFIED"
                for item in result.cleanup_evidence),
            "Planner worker absence was not verified.")
    return {
        "task_id": result.task_id,
        "input_mode": expected_mode,
        "route": result.route.value,
        "tools": [step.tool for step in result.steps],
        "paths_match_owned_fixtures": True,
        "ledger_verified": True,
        "worker_absence_verified": True,
    }


def run_acceptance(model_path: Path, report_path: Path) -> dict:
    _assert(sys.platform == "win32", "P14 native planner acceptance requires Windows.")
    model_path = model_path.resolve()
    _assert(model_path.is_file(), "Configured local GGUF model is missing.")
    root = report_path.parent.resolve() / "planner-runtime"
    fixture_dir = root / "owned-fixture"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    (fixture_dir / "voice-fixture.txt").write_text("voice fixture", encoding="utf-8")
    (fixture_dir / "typed-fixture.txt").write_text("typed fixture", encoding="utf-8")

    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["brain"]["model_path"] = str(model_path)
    config["agent"]["max_plan_steps"] = 8
    config["runtime"]["model_idle_unload_seconds"] = 30
    config["voice"]["required"] = False
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    runtime = PlumaApplicationRuntime(paths=paths, config=config)
    command = (
        "Use exactly two read-only registered file tools in this order: "
        f"first list_folder for {fixture_dir}, then file_info for "
        f"{fixture_dir / 'voice-fixture.txt'}. Do not open or change anything."
    )
    pipeline = VoicePipeline(
        lifecycle_manager=_FixtureTranscript(command),
        vad=EnergyVAD(energy_threshold=100.0),
    )
    voice_request = pipeline.process_audio(_tone())
    _assert(voice_request is not None and voice_request.input_mode == InputMode.VOICE,
            "Fixture transcription did not create a voice request.")
    _assert(voice_request.text == command and voice_request.original_transcript == command,
            "Voice request lost its canonical/original transcript fields.")
    typed_request = PlumaRequest.from_text(command)

    with model_path.open("rb") as model_file:
        model_sha256 = hashlib.file_digest(model_file, "sha256").hexdigest()
    report = {
        "source": "tests/windows/p14_voice_planner_acceptance.py",
        "python": sys.version,
        "platform": sys.platform,
        "llama_cpp_python": __import__("importlib.metadata", fromlist=["version"]).version(
            "llama-cpp-python"
        ),
        "model_path": str(model_path.resolve()),
        "model_size_bytes": model_path.stat().st_size,
        "model_sha256": model_sha256,
        "input": "fixture transcript; no microphone opened",
        "tasks": {},
    }
    try:
        report["tasks"]["text"] = _run_task(runtime, typed_request, "text", fixture_dir)
        report["tasks"]["voice"] = _run_task(runtime, voice_request, "voice", fixture_dir)
        voice_task, text_task = report["tasks"]["voice"], report["tasks"]["text"]
        _assert(voice_task["route"] == text_task["route"] == "SMART",
                "Voice and text equivalents selected different routes.")
        _assert(voice_task["tools"] == text_task["tools"],
                "Voice and text equivalents selected different registered tools.")
        report["voice_text_route_tool_parity"] = True
        report["status"] = "passed"
        return report
    finally:
        runtime.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument(
        "--report", type=Path,
        default=Path("output/p14-native/voice-planner-acceptance-report.json"),
    )
    args = parser.parse_args()
    report = run_acceptance(args.model, args.report)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
