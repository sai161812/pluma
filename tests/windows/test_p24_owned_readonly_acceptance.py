"""P24 owned-target, end-to-end read-only corpus acceptance.

This first P24 slice runs seven explicit file-list/search cases from the fixed
corpus. Every target and ledger is owned by the test; the real router,
registered tool, verifier and terminal ledger path run without touching user
files or desktop state. Only find_file uses its registered owned worker.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from pluma.app import PlumaApplicationRuntime
from pluma.config.paths import PlumaPaths
from pluma.core.ownership import subprocess_absent
from pluma.core.request import InputMode, PlumaRequest
from pluma.memory.activity import ActivityQuery


_CORPUS_PATH = Path(__file__).parents[1] / "fixtures" / "golden_commands.yaml"
_READ_CASES = {
    "GC-076": "listed-fixture.txt",
    "GC-077": "listed-fixture.txt",
    "GC-084": "listed-fixture.txt",
    "GC-078": "test.txt",
    "GC-079": "script.py",
    "GC-085": "report.docx",
    "GC-087": "config.yaml",
}
_ML_MODULE_PREFIXES = (
    "llama_cpp", "paddle", "onnxruntime", "whisper", "torch", "tensorflow",
)


def _corpus_case(case_id: str) -> dict[str, Any]:
    with _CORPUS_PATH.open("r", encoding="utf-8") as stream:
        cases = yaml.safe_load(stream)["commands"]
    matches = [case for case in cases if case["id"] == case_id]
    assert len(matches) == 1, f"Expected one fixed corpus entry for {case_id}."
    return matches[0]


@pytest.fixture
def app_runtime(tmp_path: Path):
    """Use a real TaskSupervisor/Job Object and a database under pytest temp."""
    paths = PlumaPaths(tmp_path / "local", tmp_path / "roaming")
    paths.ensure_directories()
    runtime = PlumaApplicationRuntime(
        paths,
        config={
            "voice": {"required": False},
            "runtime": {"allow_short_warm_grace": False},
        },
    )
    try:
        yield runtime
    finally:
        report = runtime.close(3)
        assert report.complete, report


def _owned_readonly_case(
    app_runtime: PlumaApplicationRuntime,
    tmp_path: Path,
    case_id: str,
    input_mode: InputMode,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, Any], Any, Any, Path]:
    case = _corpus_case(case_id)
    assert case["expected_route"] == "FAST"
    tool_name = case["expected_tools"][0]
    assert tool_name in {"list_files", "find_file"}
    assert case["expected_risk"] == "READ"
    assert case["expected_policy_decision"] == "ALLOW"
    assert case["expected_execution_status"] == "SUCCEEDED"

    root = tmp_path / ("owned-corpus-" + case_id.lower() + "-" + input_mode.value)
    root.mkdir()
    target = root / _READ_CASES[case_id]
    target.write_bytes(b"PLUMA P24 owned read-only fixture\n")

    original_root = r"C:\PLUMA_Corpus"
    if tool_name == "find_file":
        assert original_root in case["command"]
        command = case["command"].replace(original_root, str(root))
    else:
        command = case["command"]
    request = PlumaRequest(
        input_mode=input_mode,
        text=command,
        original_transcript=command if input_mode is InputMode.VOICE else None,
    )

    # The fixed corpus uses path='.' for listing. Resolve that only inside this
    # test's owned directory, then pytest restores the process working directory.
    if tool_name == "list_files":
        monkeypatch.chdir(root)

    ml_before = {name for name in sys.modules if name.startswith(_ML_MODULE_PREFIXES)}
    route = app_runtime.router.route(request)
    assert route.route.value == case["expected_route"]
    assert route.plan is not None and len(route.plan.steps) == 1
    call = route.plan.steps[0]
    assert call.tool == tool_name
    if tool_name == "find_file":
        expected_pattern = case["normalized_args"]["pattern"]
        expected_args = {"pattern": expected_pattern, "directory": str(root)}
    else:
        expected_args = case["normalized_args"]
    assert call.arguments == expected_args

    execution = app_runtime.orchestrator.execute(request)
    assert execution.success and execution.final_state == case["expected_execution_status"], execution
    assert execution.route.value == case["expected_route"]
    assert len(execution.steps) == 1 and execution.steps[0].tool == tool_name
    tool_result = execution.steps[0].result
    assert tool_result.ok and tool_result.verified
    if tool_name == "find_file":
        assert tool_result.adapter_used == "native_handle"
        assert tool_result.data["count"] == 1 and not tool_result.data["limited"]
        assert tool_result.data["unambiguous"] is True
        assert len(tool_result.data["matches"]) == 1
        match = tool_result.data["matches"][0]
        assert match["path"] == str(target)
        assert match["identity"]["file_id"]
    else:
        assert tool_result.data["path"] == str(root)
        assert tool_result.data["count"] == 1
        assert len(tool_result.data["entries"]) == 1
        entry = tool_result.data["entries"][0]
        assert entry["name"] == target.name and entry["path"] == str(target)
        assert target.read_bytes() == b"PLUMA P24 owned read-only fixture\n"
    assert target.is_file() and target.read_bytes() == b"PLUMA P24 owned read-only fixture\n"

    capsule = app_runtime.supervisor.get_task(execution.task_id)
    assert capsule.state.value == "SUCCEEDED" and capsule.terminal_persisted is True
    assert capsule.worker_controller is None and capsule.job_object is None
    worker_entries = [entry for entry in capsule.cleanup_evidence
                      if entry.kind == "worker" and entry.code == "WORKER_ABSENCE_VERIFIED"]
    worker_identity = None
    worker_absent = False
    if app_runtime.tool_registry.lookup(tool_name).process_isolated:
        assert len(worker_entries) == 1 and worker_entries[0].verified
        worker_identity = worker_entries[0].identity
        worker_absent = subprocess_absent(worker_identity["pid"], worker_identity["creation_time"])
        assert worker_absent
    else:
        assert worker_entries == []
        controller = app_runtime.tool_registry.get_worker(execution.task_id)
        assert controller.worker_identity is None and controller.verify_cleanup()
        worker_absent = True

    query = ActivityQuery(app_runtime.db)
    task_row = query.task_by_id(execution.task_id)
    assert task_row["route"] == "FAST" and task_row["final_state"] == "SUCCEEDED"
    assert task_row["input_mode"] == input_mode.value
    actions = query.actions_for_task(execution.task_id)
    assert len(actions) == 1
    action = actions[0]
    assert action["tool"] == tool_name and action["risk"] == "READ"
    assert action["approval_state"] == "ALLOW" and action["verified"] == 1
    assert action["adapter"] == tool_result.adapter_used
    saved_call = json.loads(action["args_json_sanitized"])
    canonical_args = app_runtime.tool_registry.lookup(tool_name).args_schema.model_validate(
        expected_args,
    ).model_dump(mode="json")
    assert saved_call == {"tool": tool_name, "args": canonical_args}
    args = saved_call["args"]
    saved_result = json.loads(action["result_json"])
    assert saved_result["count"] == 1
    if tool_name == "find_file":
        assert saved_result["unambiguous"] is True
    else:
        assert saved_result["path"] == str(root)
        assert saved_result["entries"][0]["path"] == str(target)
    saved_verification = json.loads(action["verification_json"])
    assert saved_verification["ok"] is True
    if tool_name == "find_file":
        assert "native_candidate_and_directory_readback" in saved_verification["method"]

    cleanup_row = query.cleanup_report_for_task(execution.task_id)
    assert cleanup_row is not None
    cleanup = json.loads(cleanup_row["metadata_json"])
    saved_workers = [entry for entry in cleanup["entries"]
                     if entry["kind"] == "worker" and entry["code"] == "WORKER_ABSENCE_VERIFIED"]
    if worker_identity is not None:
        assert len(saved_workers) == 1 and saved_workers[0]["verified"] is True
    else:
        assert saved_workers == []

    ml_after = {name for name in sys.modules if name.startswith(_ML_MODULE_PREFIXES)}
    assert ml_after - ml_before == set(), f"FAST read-only request loaded ML modules: {ml_after - ml_before}"

    print("P24_EVIDENCE " + json.dumps({
        "case_id": case_id,
        "input_mode": input_mode.value,
        "route": execution.route.value,
        "tool": call.tool,
        "arguments": args,
        "risk": action["risk"],
        "policy": action["approval_state"],
        "postcondition": "native read result matches owned fixture; fixture unchanged",
        "ledger_readback": "task, action, saved verifier and applicable worker cleanup verified",
        "worker_pid": worker_identity["pid"] if worker_identity else None,
        "worker_absent": worker_absent,
        "duration_ms": action["duration_ms"],
        "ml_modules_loaded": sorted(ml_after - ml_before),
    }, sort_keys=True))
    return case, execution, tool_result, target


@pytest.mark.parametrize("case_id", tuple(_READ_CASES))
def test_fixed_corpus_readonly_file_operation_uses_owned_full_pipeline(
    app_runtime: PlumaApplicationRuntime, tmp_path: Path, case_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _owned_readonly_case(app_runtime, tmp_path, case_id, InputMode.TEXT, monkeypatch)


def test_fixed_corpus_readonly_search_has_text_voice_semantic_parity(
    app_runtime: PlumaApplicationRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_case, text_result, text_tool, text_target = _owned_readonly_case(
        app_runtime, tmp_path, "GC-078", InputMode.TEXT, monkeypatch,
    )
    voice_case, voice_result, voice_tool, voice_target = _owned_readonly_case(
        app_runtime, tmp_path, "GC-078", InputMode.VOICE, monkeypatch,
    )

    assert text_case["command"] == voice_case["command"]
    assert text_result.route.value == voice_result.route.value
    assert text_result.steps[0].tool == voice_result.steps[0].tool == "find_file"
    assert text_tool.data["count"] == voice_tool.data["count"] == 1
    assert text_tool.data["matches"][0]["name"] == voice_tool.data["matches"][0]["name"]
    assert text_target.name == voice_target.name == "test.txt"
    print("P24_PARITY same FAST route, typed tool, owned-file postcondition and ledger contract")


def test_fixed_corpus_readonly_listing_has_text_voice_semantic_parity(
    app_runtime: PlumaApplicationRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    text_case, text_result, text_tool, text_target = _owned_readonly_case(
        app_runtime, tmp_path, "GC-076", InputMode.TEXT, monkeypatch,
    )
    voice_case, voice_result, voice_tool, voice_target = _owned_readonly_case(
        app_runtime, tmp_path, "GC-076", InputMode.VOICE, monkeypatch,
    )

    assert text_case["command"] == voice_case["command"]
    assert text_result.route.value == voice_result.route.value == "FAST"
    assert text_result.steps[0].tool == voice_result.steps[0].tool == "list_files"
    project_text = [
        (entry["name"], entry["is_dir"], entry["size_bytes"])
        for entry in text_tool.data["entries"]
    ]
    project_voice = [
        (entry["name"], entry["is_dir"], entry["size_bytes"])
        for entry in voice_tool.data["entries"]
    ]
    assert project_text == project_voice
    assert text_target.name == voice_target.name == "listed-fixture.txt"
    print("P24_PARITY same FAST route, typed tool, owned-directory read result and ledger contract")
