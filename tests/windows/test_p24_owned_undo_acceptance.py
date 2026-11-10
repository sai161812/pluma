"""P24 owned-target end-to-end acceptance for corpus undo requests."""
from __future__ import annotations

import json
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
_CASE_IDS = ("GC-054", "GC-055")


def _corpus_case(case_id: str) -> dict[str, Any]:
    with _CORPUS_PATH.open("r", encoding="utf-8") as stream:
        cases = yaml.safe_load(stream)["commands"]
    matches = [case for case in cases if case["id"] == case_id]
    assert len(matches) == 1, f"Expected one fixed corpus entry for {case_id}."
    return matches[0]


def _failure_detail(execution: Any) -> str:
    steps = [
        {
            "tool": step.tool,
            "ok": step.result.ok,
            "verified": step.result.verified,
            "error_code": step.result.error_code,
            "error": step.result.error,
        }
        for step in execution.steps
    ]
    return (
        f"state={execution.final_state}; error={execution.error}; "
        f"summary={execution.factual_summary}; steps={steps}; "
        f"cleanup={execution.cleanup_evidence}"
    )


@pytest.fixture
def app_runtime(tmp_path: Path):
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
def test_fixed_corpus_undo_request_reverses_one_confirmed_owned_move(
    app_runtime: PlumaApplicationRuntime,
    tmp_path: Path,
    case_id: str,
) -> None:
    case = _corpus_case(case_id)
    assert case["expected_route"] == "FAST"
    assert case["expected_tools"] == ["undo_last"]
    assert case["expected_risk"] == "MEDIUM"
    assert case["expected_policy_decision"] == "REQUIRE_CONFIRMATION"
    assert case["expected_execution_status"] == "SUCCEEDED"

    root = tmp_path / "owned-undo-root"
    root.mkdir()
    source, destination = root / "before.txt", root / "after.txt"
    source_bytes = b"Owned file used to verify one manual undo.\n"
    source.write_bytes(source_bytes)
    assert not destination.exists()

    decisions = []
    app_runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda decision: decisions.append(decision)
        or ConfirmationResponse(approved=True, reason="Owned P24 undo fixture approval.")
    )

    move_request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=f"move file {source} to {destination}",
    )
    move_route = app_runtime.router.route(move_request)
    assert move_route.route.value == "FAST"
    assert move_route.plan is not None and len(move_route.plan.steps) == 1
    assert move_route.plan.steps[0].tool == "move_file"
    moved = app_runtime.orchestrator.execute(move_request)
    assert moved.success and moved.final_state == "SUCCEEDED", _failure_detail(moved)
    assert not source.exists() and destination.read_bytes() == source_bytes

    query = ActivityQuery(app_runtime.db)
    move_actions = query.actions_for_task(moved.task_id)
    assert len(move_actions) == 1
    move_action = move_actions[0]
    assert move_action["tool"] == "move_file"
    assert move_action["risk"] == "MEDIUM" and move_action["approval_state"] == "ALLOW"
    assert move_action["verified"] == 1
    move_undo = query.available_undo_records_for_task(moved.task_id)
    assert len(move_undo) == 1
    assert json.loads(move_undo[0]["undo_json"])["identity"]["file_id"]

    undo_request = PlumaRequest(input_mode=InputMode.TEXT, text=case["command"])
    undo_route = app_runtime.router.route(undo_request)
    assert undo_route.route.value == case["expected_route"]
    assert undo_route.plan is not None and len(undo_route.plan.steps) == 1
    undo_call = undo_route.plan.steps[0]
    assert undo_call.tool == "undo_last" and undo_call.arguments == {}

    undone = app_runtime.orchestrator.execute(undo_request)
    assert undone.success and undone.final_state == case["expected_execution_status"], _failure_detail(undone)
    assert len(undone.steps) == 1 and undone.steps[0].tool == "undo_last"
    undo_result = undone.steps[0].result
    assert undo_result.ok and undo_result.verified
    assert undo_result.data == {"action_row_id": move_action["id"], "action": "move_file"}
    assert source.read_bytes() == source_bytes and not destination.exists()

    assert len(decisions) == 2
    assert [(item.tool_name, item.risk_class) for item in decisions] == [
        ("move_file", RiskClass.MEDIUM), ("undo_last", RiskClass.MEDIUM),
    ]
    assert decisions[0].arguments["source"] == str(source)
    assert decisions[0].arguments["destination"] == str(destination)

    undo_task = query.task_by_id(undone.task_id)
    assert undo_task["route"] == "FAST" and undo_task["final_state"] == "SUCCEEDED"
    undo_actions = query.actions_for_task(undone.task_id)
    assert len(undo_actions) == 1
    action = undo_actions[0]
    assert action["tool"] == "undo_last" and action["risk"] == "MEDIUM"
    assert action["approval_state"] == "ALLOW" and action["verified"] == 1
    assert json.loads(action["result_json"]) == undo_result.data
    verification = json.loads(action["verification_json"])
    assert verification["ok"] is True
    assert verification["method"] == "inverse_and_sqlite_readback"
    assert query.available_undo_records_for_task(moved.task_id) == []
    claim = app_runtime.db.execute_read_one(
        "SELECT state FROM undo_claims WHERE action_id=?", (move_action["id"],)
    )
    assert claim is not None and claim["state"] == "verified"

    for task_id in (moved.task_id, undone.task_id):
        capsule = app_runtime.supervisor.get_task(task_id)
        assert capsule.terminal_persisted is True and capsule.worker_controller is None
        assert capsule.job_object is None
        workers = [
            item for item in capsule.cleanup_evidence
            if item.kind == "worker" and item.code == "WORKER_ABSENCE_VERIFIED"
        ]
        assert len(workers) == 1 and workers[0].verified
        worker = workers[0].identity
        assert subprocess_absent(worker["pid"], worker["creation_time"])
        cleanup = query.cleanup_report_for_task(task_id)
        assert cleanup is not None
        saved = json.loads(cleanup["metadata_json"])
        saved_workers = [
            item for item in saved["entries"]
            if item["kind"] == "worker" and item["code"] == "WORKER_ABSENCE_VERIFIED"
        ]
        assert len(saved_workers) == 1 and saved_workers[0]["verified"] is True
    assert source.read_bytes() == source_bytes and not destination.exists()
