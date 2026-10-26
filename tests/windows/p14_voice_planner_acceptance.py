"""Native Whisper-to-Qwen acceptance over an owned, read-only file fixture.

An explicitly generated speech fixture is transcribed by the configured local
whisper.cpp runtime. The voice request then uses the same task capsule for
native Qwen planning and two registered read-only filesystem tools. A temporary
subst drive gives the spoken fixture a short literal path; every proposed path
is resolved through a Windows handle and checked against the owned fixture root
before the plan can reach execution. No microphone is opened.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
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


_FIXTURE_DRIVE = "P:"
_FIXTURE_FILENAME = "note.txt"
_FIXTURE_CONTENT = b"PLUMA owned read-only voice acceptance fixture.\r\n"
_ALLOWED_TOOLS = {"list_folder", "file_info"}


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


def _drive_is_present(drive: str) -> bool:
    mask = ctypes.WinDLL("kernel32", use_last_error=True).GetLogicalDrives()
    bit = 1 << (ord(drive[0].upper()) - ord("A"))
    return bool(mask & bit)


def _canonical_windows_path(path: str | Path) -> Path:
    """Resolve a path through its opened handle, including subst drive aliases."""
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.GetFinalPathNameByHandleW.argtypes = (
        wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD,
    )
    kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL

    handle = kernel.CreateFileW(
        str(path), 0, 0x1 | 0x2 | 0x4, None, 3, 0x02000000, None
    )  # metadata-only access; FILE_FLAG_BACKUP_SEMANTICS for directories
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = kernel.GetFinalPathNameByHandleW(handle, None, 0, 0)
        if not size:
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_unicode_buffer(size + 1)
        written = kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
        if not written or written >= len(buffer):
            raise ctypes.WinError(ctypes.get_last_error())
        resolved = buffer.value
    finally:
        if not kernel.CloseHandle(handle):
            raise ctypes.WinError(ctypes.get_last_error())

    if resolved.startswith("\\\\?\\UNC\\"):
        resolved = "\\\\" + resolved[8:]
    elif resolved.startswith("\\\\?\\"):
        resolved = resolved[4:]
    return Path(os.path.normpath(resolved))


def _is_within(path: str | Path, root: str | Path) -> bool:
    candidate = os.path.normcase(os.path.abspath(str(path)))
    boundary = os.path.normcase(os.path.abspath(str(root)))
    try:
        return os.path.commonpath((candidate, boundary)) == boundary
    except ValueError:
        return False


def _same_path(left: str | Path, right: str | Path) -> bool:
    return os.path.normcase(os.path.abspath(str(left))) == os.path.normcase(
        os.path.abspath(str(right))
    )


def _map_fixture_drive(fixture_dir: Path) -> None:
    _assert(not _drive_is_present(_FIXTURE_DRIVE),
            f"{_FIXTURE_DRIVE} is already present; refusing to reuse a user drive.")
    try:
        subprocess.run(
            ["subst", _FIXTURE_DRIVE, str(fixture_dir)],
            check=True, capture_output=True, text=True, timeout=5,
        )
        _assert(_drive_is_present(_FIXTURE_DRIVE), "Fixture drive did not appear after subst.")
        _assert(_same_path(_canonical_windows_path(f"{_FIXTURE_DRIVE}\\"), fixture_dir),
                "Fixture drive readback did not resolve to the owned directory.")
    except BaseException:
        if _drive_is_present(_FIXTURE_DRIVE):
            _unmap_fixture_drive(fixture_dir)
        raise


def _unmap_fixture_drive(fixture_dir: Path) -> None:
    if not _drive_is_present(_FIXTURE_DRIVE):
        return
    _assert(_same_path(_canonical_windows_path(f"{_FIXTURE_DRIVE}\\"), fixture_dir),
            f"{_FIXTURE_DRIVE} no longer maps to the owned fixture; refusing removal.")
    subprocess.run(
        ["subst", _FIXTURE_DRIVE, "/D"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    _assert(not _drive_is_present(_FIXTURE_DRIVE), "Fixture drive remained mapped after cleanup.")


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


class _OwnedFilesystemPlanner:
    """Delegate native planning, but refuse any plan outside read-only fixture scope."""

    def __init__(self, planner, fixture_dir: Path) -> None:
        self._planner = planner
        self.fixture_dir = _canonical_windows_path(fixture_dir)
        self.checked_paths: list[str] = []

    def __getattr__(self, name):
        return getattr(self._planner, name)

    def plan(self, **kwargs):
        plan = self._planner.plan(**kwargs)
        tools = [step.tool for step in plan.steps]
        _assert(len(plan.steps) == 2 and set(tools) == _ALLOWED_TOOLS,
                "Native Qwen must produce exactly list_folder and file_info read steps.")
        for step in plan.steps:
            target = step.arguments.get("path")
            _assert(isinstance(target, str) and target,
                    f"{step.tool} did not supply one explicit fixture path.")
            canonical = _canonical_windows_path(target)
            _assert(_is_within(canonical, self.fixture_dir),
                    f"Planner proposed a path outside the owned fixture: {step.tool}.")
            self.checked_paths.append(str(canonical))
        return plan


def _run_task(runtime, request, expected_mode: str, fixture_dir: Path,
              expected_capsule=None) -> dict:
    capsule = expected_capsule
    result = runtime.orchestrator.execute(request, capsule=capsule)
    _assert(result.route == RouteMode.SMART, f"Expected SMART route, got {result.route}.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"Native planner task failed: {result.error or result.factual_summary}")
    expected_tools = ["list_folder", "file_info"]
    _assert([step.tool for step in result.steps] == expected_tools,
            "Voice/text planner did not execute the expected read-only file sequence.")
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

    folder_result = next(step.result for step in result.steps if step.tool == "list_folder")
    info_result = next(step.result for step in result.steps if step.tool == "file_info")
    _assert(folder_result.data["path"].casefold() == f"{_FIXTURE_DRIVE}\\".casefold(),
            "Folder listing did not read the owned fixture directory.")
    _assert(any(entry["name"] == _FIXTURE_FILENAME for entry in folder_result.data["entries"]),
            "Verified folder results did not include the owned fixture file.")
    _assert(info_result.data["kind"] == "file"
            and info_result.data["size_bytes"] == len(_FIXTURE_CONTENT)
            and info_result.data["file_id"] > 0,
            "File metadata did not read back the owned fixture identity and size.")
    _assert(_is_within(_canonical_windows_path(info_result.data["path"]), fixture_dir),
            "File metadata result escaped the owned fixture root.")

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
    _assert(all(_is_within(_canonical_windows_path(args["path"]), fixture_dir)
                for args in action_arguments),
            "Ledger arguments included a path outside the owned fixture.")
    _assert(any(item.get("code") == "WORKER_ABSENCE_VERIFIED"
                for item in result.cleanup_evidence),
            "Planner worker absence was not verified.")
    _assert(expected_capsule is None or result.task_id == expected_capsule.task_id,
            "STT and native planner did not keep the original task capsule.")
    return {
        "task_id": result.task_id,
        "input_mode": expected_mode,
        "route": result.route.value,
        "tools": [step.tool for step in result.steps],
        "file_result": {
            "listed_fixture_file": _FIXTURE_FILENAME,
            "metadata_size_bytes": info_result.data["size_bytes"],
            "file_identity_read_back": True,
        },
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
    root.mkdir(parents=True, exist_ok=False)
    fixture_dir = root / "owned-fixture"
    fixture_dir.mkdir(parents=True, exist_ok=False)
    (fixture_dir / _FIXTURE_FILENAME).write_bytes(_FIXTURE_CONTENT)

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
    mapped = False
    try:
        _map_fixture_drive(fixture_dir)
        mapped = True
        capsule = runtime.supervisor.create_task_capsule()
        observed = _ObservedLifecycle(runtime.voice_lifecycle)
        pipeline = VoicePipeline(
            lifecycle_manager=observed,
            vad=runtime.voice_pipeline.vad,
        )
        native_guard = _OwnedFilesystemPlanner(runtime.llm_lifecycle, fixture_dir)
        runtime.orchestrator._llm_manager = native_guard
        runtime.orchestrator._multi_step.planner = native_guard

        voice_request = pipeline.process_audio(
            audio, cancellation_token=capsule.cancellation_token
        )
        _assert(isinstance(voice_request, PlumaRequest)
                and voice_request.input_mode == InputMode.VOICE,
                "Native Whisper did not create a routable high-confidence voice request.")
        _assert(voice_request.text and voice_request.original_transcript,
                "Native voice request lost its transcript metadata.")
        _assert(observed.confidence is not None and observed.low_confidence is False,
                "Native Whisper did not establish a non-low-confidence file request.")
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
            "raw_audio_saved": False,
            "fixture_directory_owned": True,
            "fixture_drive_mapping_read_back": True,
            "planner_paths_checked_before_execution": True,
            "tasks": {},
        }
        report["tasks"]["voice"] = _run_task(
            runtime, voice_request, "voice", fixture_dir, expected_capsule=capsule
        )
        report["tasks"]["text"] = _run_task(
            runtime, typed_request, "text", fixture_dir
        )
        voice_task, text_task = report["tasks"]["voice"], report["tasks"]["text"]
        _assert(voice_task["route"] == text_task["route"] == "SMART",
                "Voice and text equivalents selected different routes.")
        _assert(voice_task["tools"] == text_task["tools"] == ["list_folder", "file_info"],
                "Voice and text equivalents selected different registered tools.")
        _assert(voice_task["file_result"] == text_task["file_result"],
                "Voice and text equivalents returned different fixture file results.")
        _assert(len(native_guard.checked_paths) == 4,
                "Each voice/text planner path was not checked before tool execution.")
        report["voice_text_route_tool_parity"] = True
        report["same_task_capsule_for_stt_and_voice_planner"] = True
        report["owned_fixture_readback"] = True
        report["status"] = "passed"
        return report
    finally:
        audio = b""
        try:
            runtime.close()
        finally:
            if mapped:
                _unmap_fixture_drive(fixture_dir)


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
