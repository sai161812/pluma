"""P24 owned-target end-to-end acceptance for corpus folder creation."""
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
_CASE_IDS = ("GC-080", "GC-081", "GC-086", "GC-090")
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
    """Use real task supervision and a ledger under pytest-owned storage."""
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


@pytest.mark.parametrize("case_id", _CASE_IDS)
def test_fixed_corpus_folder_creation_uses_owned_target_and_records_undo_prestate(
    app_runtime: PlumaApplicationRuntime,
    tmp_path: Path,
    case_id: str,
) -> None:
    case = _corpus_case(case_id)
    assert case["expected_route"] == "FAST"
    assert case["expected_tools"] == ["create_folder"]
    assert case["expected_risk"] == "LOW"
    assert case["expected_policy_decision"] == "ALLOW"
    assert case["expected_execution_status"] == "SUCCEEDED"

    root = tmp_path / "owned-corpus-root"
    root.mkdir()
    corpus_root = r"C:\PLUMA_Corpus"
    assert corpus_root in case["command"]
    command = case["command"].replace(corpus_root, str(root))
    target = Path(case["normalized_args"]["path"].replace(corpus_root, str(root)))
    assert not target.exists()
    request = PlumaRequest(input_mode=InputMode.TEXT, text=command)

    ml_before = {name for name in sys.modules if name.startswith(_ML_MODULE_PREFIXES)}
    route = app_runtime.router.route(request)
    assert route.route.value == case["expected_route"]
    assert route.plan is not None and len(route.plan.steps) == 1
    call = route.plan.steps[0]
    assert call.tool == "create_folder"
    assert call.arguments == {"path": str(target)}

    execution = app_runtime.orchestrator.execute(request)
    assert execution.success and execution.final_state == case["expected_execution_status"], execution
    assert execution.route.value == "FAST"
    assert len(execution.steps) == 1 and execution.steps[0].tool == "create_folder"
    result = execution.steps[0].result
    assert result.ok and result.verified and result.adapter_used == "native_handle"
    assert result.data == {"path": str(target)}
    assert target.is_dir() and list(target.iterdir()) == []

    capsule = app_runtime.supervisor.get_task(execution.task_id)
    assert capsule.state.value == "SUCCEEDED" and capsule.terminal_persisted is True
    assert capsule.worker_controller is None and capsule.job_object is None
    assert capsule.undo_stack and capsule.undo_stack[-1]["action"] == "create_folder"
    worker_entries = [
        entry for entry in capsule.cleanup_evidence
        if entry.kind == "worker" and entry.code == "WORKER_ABSENCE_VERIFIED"
    ]
    assert len(worker_entries) == 1 and worker_entries[0].verified
    worker = worker_entries[0].identity
    assert subprocess_absent(worker["pid"], worker["creation_time"])

    query = ActivityQuery(app_runtime.db)
    task_row = query.task_by_id(execution.task_id)
    assert task_row["route"] == "FAST" and task_row["final_state"] == "SUCCEEDED"
    actions = query.actions_for_task(execution.task_id)
    assert len(actions) == 1
    action = actions[0]
    assert action["tool"] == "create_folder" and action["risk"] == "LOW"
    assert action["approval_state"] == "ALLOW" and action["verified"] == 1
    saved_call = json.loads(action["args_json_sanitized"])
    canonical_args = app_runtime.tool_registry.lookup("create_folder").args_schema.model_validate(
        {"path": str(target)},
    ).model_dump(mode="json")
    assert saved_call == {"tool": "create_folder", "args": canonical_args}
    assert json.loads(action["result_json"]) == result.model_dump(mode="json")["data"]
    saved_verification = json.loads(action["verification_json"])
    assert saved_verification["ok"] is True
    assert saved_verification["method"] == "native_identity_and_digest"

    undo_rows = query.available_undo_records_for_task(execution.task_id)
    assert len(undo_rows) == 1
    undo_state = json.loads(undo_rows[0]["undo_json"])
    assert undo_state["action"] == "create_folder"
    assert undo_state["path"] == str(target) and undo_state["existed_before"] is False
    assert [entry["path"] for entry in undo_state["created"]] == [str(target)]
    assert undo_state["created"][0]["identity"]["file_id"]

    cleanup_row = query.cleanup_report_for_task(execution.task_id)
    assert cleanup_row is not None
    cleanup = json.loads(cleanup_row["metadata_json"])
    saved_workers = [
        entry for entry in cleanup["entries"]
        if entry["kind"] == "worker" and entry["code"] == "WORKER_ABSENCE_VERIFIED"
    ]
    assert len(saved_workers) == 1 and saved_workers[0]["verified"] is True
    ml_after = {name for name in sys.modules if name.startswith(_ML_MODULE_PREFIXES)}
    assert ml_after - ml_before == set(), f"FAST mutation loaded ML modules: {ml_after - ml_before}"
