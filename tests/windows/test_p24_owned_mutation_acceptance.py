"""P24 owned-target end-to-end acceptance for corpus file mutations."""
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
from pluma.tools.base import RiskClass
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse


_CORPUS_PATH = Path(__file__).parents[1] / "fixtures" / "golden_commands.yaml"
_CASE_IDS = ("GC-082", "GC-083")
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
def test_fixed_corpus_move_and_rename_use_scoped_confirmation_and_owned_files(
    app_runtime: PlumaApplicationRuntime,
    tmp_path: Path,
    case_id: str,
) -> None:
    case = _corpus_case(case_id)
    assert case["expected_route"] == "FAST"
    assert case["expected_tools"] in (["move_file"], ["rename_file"])
    assert case["expected_risk"] == "MEDIUM"
    assert case["expected_policy_decision"] == "REQUIRE_CONFIRMATION"
    assert case["expected_execution_status"] == "SUCCEEDED"

    root = tmp_path / "owned-corpus-root"
    root.mkdir()
    corpus_root = r"C:\PLUMA_Corpus"
    assert corpus_root in case["command"]
    command = case["command"].replace(corpus_root, str(root))
    request = PlumaRequest(input_mode=InputMode.TEXT, text=command)
    call_args = case["normalized_args"].copy()
    for key, value in call_args.items():
        if isinstance(value, str):
            call_args[key] = value.replace(corpus_root, str(root))

    if case["id"] == "GC-082":
        source = Path(call_args["source"])
        destination = Path(call_args["destination"])
        source.write_bytes(b"owned move fixture\n")
        expected_data = {"source": str(source), "destination": str(destination)}
    else:
        source = Path(call_args["path"])
        destination = source.with_name(call_args["new_name"])
        source.write_bytes(b"owned rename fixture\n")
        expected_data = {"original_path": str(source), "new_path": str(destination)}

    assert source.is_file() and not destination.exists()
    before_bytes = source.read_bytes()
    decisions = []
    app_runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda decision: decisions.append(decision)
        or ConfirmationResponse(approved=True, reason="Owned P24 fixture approval.")
    )

    ml_before = {name for name in sys.modules if name.startswith(_ML_MODULE_PREFIXES)}
    route = app_runtime.router.route(request)
    assert route.route.value == case["expected_route"]
    assert route.plan is not None and len(route.plan.steps) == 1
    call = route.plan.steps[0]
    tool_name = case["expected_tools"][0]
    assert call.tool == tool_name
    assert call.arguments == call_args

    execution = app_runtime.orchestrator.execute(request)
    if not execution.success or execution.final_state != case["expected_execution_status"]:
        steps = [
            {
                "tool": step.tool,
                "ok": step.result.ok,
                "verified": step.result.verified,
                "error_code": step.result.error_code,
                "error": step.result.error,
                "factual_message": step.result.factual_message,
            }
            for step in execution.steps
        ]
        pytest.fail(
            f"Task execution failed: state={execution.final_state}; error={execution.error}; "
            f"summary={execution.factual_summary}; steps={steps}; "
            f"cleanup={execution.cleanup_evidence}"
        )
    assert execution.route.value == "FAST"
    assert len(execution.steps) == 1 and execution.steps[0].tool == tool_name
    result = execution.steps[0].result
    assert result.ok and result.verified and result.adapter_used == "native_handle"
    assert result.data == expected_data
    assert not source.exists() and destination.is_file()
    assert destination.read_bytes() == before_bytes

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.task_id == execution.task_id
    assert decision.tool_name == tool_name
    assert decision.risk_class == RiskClass.MEDIUM
    spec = app_runtime.tool_registry.lookup(tool_name)
    canonical_args = spec.args_schema.model_validate(call_args).model_dump(mode="json")
    assert decision.arguments == canonical_args

    capsule = app_runtime.supervisor.get_task(execution.task_id)
    assert capsule.state.value == "SUCCEEDED" and capsule.terminal_persisted is True
    assert capsule.worker_controller is None and capsule.job_object is None
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
    assert task_row["input_mode"] == "text"
    actions = query.actions_for_task(execution.task_id)
    assert len(actions) == 1
    action = actions[0]
    assert action["tool"] == tool_name and action["risk"] == "MEDIUM"
    assert action["approval_state"] == "ALLOW" and action["verified"] == 1
    assert action["adapter"] == "native_handle"
    assert json.loads(action["args_json_sanitized"]) == {
        "tool": tool_name,
        "args": canonical_args,
    }
    assert json.loads(action["result_json"]) == expected_data
    saved_verification = json.loads(action["verification_json"])
    assert saved_verification["ok"] is True
    assert saved_verification["method"] == "native_identity_and_digest"

    undo_rows = query.available_undo_records_for_task(execution.task_id)
    assert len(undo_rows) == 1
    undo_state = json.loads(undo_rows[0]["undo_json"])
    assert undo_state["action"] == tool_name
    assert undo_state["identity"]["file_id"]
    if tool_name == "move_file":
        assert undo_state["source"] == str(source)
        assert undo_state["destination"] == str(destination)
    else:
        assert undo_state["original_path"] == str(source)
        assert undo_state["new_path"] == str(destination)

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
