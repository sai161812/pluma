"""P21 owned native workers/files, no desktop/hotkey/model/device activation."""
import json
from pathlib import Path
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.config.settings import SettingsStore
from pluma.core import job_object
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_runtime_shutdown import NATIVE_JOB, task


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setattr(job_object, "WindowsJobObject", NATIVE_JOB)
    paths = PlumaPaths(tmp_path / "local", tmp_path / "roaming")
    paths.ensure_directories()
    value = PlumaApplicationRuntime(paths, config=load_config(tmp_path / "absent.json"))
    value.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: ConfirmationResponse(approved=True))
    yield value
    assert value.close(5).complete
    assert value.tool_registry.work_gate.wait_idle(0)
    assert not value.tool_registry._worker_controllers


def query(runtime):
    return runtime.resident_core.handle_ipc_command({"protocol_version": 1,
        "message_type": "settings_edit_query", "request_id": str(uuid.uuid4())})


def save_args(runtime, **changes):
    return {"expected_revision": SettingsStore(runtime.settings_path).snapshot().revision,
            "changes": changes or {"max_plan_steps": 4}}


def wait_terminal(runtime, ack):
    end = time.monotonic() + 8
    while time.monotonic() < end:
        reply = runtime.resident_core.handle_ipc_command({"protocol_version": 1,
            "message_type": "terminal_readback", "request_id": ack["request_id"], "task_id": ack["task_id"]})
        if reply.get("terminal"):
            return reply
        time.sleep(.01)
    pytest.fail("Owned settings task did not reach persisted terminal state.")


def test_typed_save_duplicate_restart_projection_and_ledger(runtime):
    original = query(runtime)
    assert original["revision"] == "absent" and original["restart_fields"] == []
    payload = dict(protocol_version=1, message_type="settings_save", request_id=str(uuid.uuid4()),
                   **save_args(runtime, max_plan_steps=4))
    ack = runtime.resident_core.handle_ipc_command(payload)
    assert ack["accepted"]
    duplicate = runtime.resident_core.handle_ipc_command(payload)
    assert duplicate["task_id"] == ack["task_id"]
    terminal = wait_terminal(runtime, ack)
    assert terminal["final_state"] == "SUCCEEDED" and terminal["completion_verified"]
    current = query(runtime)
    assert current["persisted"]["max_plan_steps"] == 4
    assert current["effective"]["max_plan_steps"] == 8
    assert current["restart_fields"] == ["max_plan_steps"]
    from pluma.config.settings_contract import FIELDS
    assert current["editable_fields"] == list(FIELDS)
    assert runtime.llm_lifecycle.adapter.max_plan_steps == 8
    assert runtime.llm_lifecycle.state.value == "COLD"
    rows = ActivityQuery(runtime.db).actions_for_task(ack["task_id"])
    assert len(rows) == 1 and rows[0]["tool"] == "save_settings" and rows[0]["verified"]
    assert json.loads(rows[0]["verification_json"])["method"] == "independent_settings_readback"
    resources = runtime.db.execute_read("SELECT released_at FROM resources WHERE task_id=? AND resource_type='temp_dir' AND ownership='PLUMA_CREATED'", (ack["task_id"],))
    assert resources and all(row["released_at"] is not None for row in resources)
    assert runtime.resident_core.handle_ipc_command(dict(payload, changes={"max_plan_steps": 5}))["error_code"] == "REQUEST_ID_REUSED"


def test_native_settings_write_semantic_undo_and_private_prestate(runtime):
    path = Path(runtime.settings_path)
    path.write_text(json.dumps({"custom": {"password": "PRIVATE_OWNED_SETTINGS_FIXTURE"},
                               "agent": {"max_plan_steps": 3}}), encoding="utf-8")
    cap = task(runtime)
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), cap, runtime.ledger)
    assert result.ok and result.verified
    proof = cap.undo_stack[-1]
    assert proof["action"] == "settings_write" and proof["before"] == {"agent.max_plan_steps": {"present": True, "value": 3}}
    assert "PRIVATE_OWNED_SETTINGS_FIXTURE" not in json.dumps(proof)
    assert "PRIVATE_OWNED_SETTINGS_FIXTURE" not in json.dumps(query(runtime))
    assert RollbackRecipes().apply("settings_write", proof).ok
    assert load_config(path)["agent"]["max_plan_steps"] == 3
    assert load_config(path)["custom"]["password"] == "PRIVATE_OWNED_SETTINGS_FIXTURE"
    assert not RollbackRecipes().apply("settings_write", proof).ok


def test_undo_restores_absence_and_refuses_owner_edit(runtime):
    cap = task(runtime)
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), cap, runtime.ledger)
    assert result.ok
    proof = cap.undo_stack[-1]
    assert RollbackRecipes().apply("settings_write", proof).ok
    assert not Path(runtime.settings_path).exists()
    cap2 = task(runtime, "settings-second")
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), cap2, runtime.ledger)
    assert result.ok
    proof2 = cap2.undo_stack[-1]
    store = SettingsStore(runtime.settings_path)
    latest = store.save({"agent.max_plan_steps": 6}, expected_revision=store.snapshot().revision)
    assert not RollbackRecipes().apply("settings_write", proof2).ok
    assert store.snapshot() == latest


def test_policy_denial_and_stale_revision_never_mutate(runtime):
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: ConfirmationResponse(approved=False))
    cap = task(runtime)
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), cap, runtime.ledger)
    assert not result.ok and result.error_code == "POLICY_DENIED"
    assert cap.worker_controller is None and not Path(runtime.settings_path).exists()
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: ConfirmationResponse(approved=True))
    store = SettingsStore(runtime.settings_path)
    latest = store.save({"agent.max_plan_steps": 6}, expected_revision="absent")
    result = runtime.tool_registry.execute("save_settings", {"expected_revision": "absent", "changes": {"max_plan_steps": 4}}, cap, runtime.ledger)
    assert not result.ok and store.snapshot() == latest


def test_typed_denial_is_a_verified_failed_terminal_not_a_verified_action(runtime):
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: ConfirmationResponse(approved=False))
    ack = runtime.resident_core.handle_ipc_command(dict(protocol_version=1, message_type="settings_save",
        request_id=str(uuid.uuid4()), **save_args(runtime)))
    terminal = wait_terminal(runtime, ack)
    # Completion verification describes the terminal lifecycle, not action success.
    end = time.monotonic() + 2
    while not terminal["completion_verified"] and time.monotonic() < end:
        terminal = wait_terminal(runtime, ack)
    assert terminal["completion_verified"] and terminal["final_state"] == "FAILED"
    assert terminal["terminal_persisted"] and not terminal["has_residual"]
    assert not Path(runtime.settings_path).exists()
    assert not ActivityQuery(runtime.db).actions_for_task(ack["task_id"])[0]["verified"]


@pytest.mark.parametrize("changes", [{}, {"max_plan_steps": True}, {"max_plan_steps": 21},
    {"stop_hotkey": None}, {"stop_hotkey": "ctrl+unknown+s"}, {"voice_required": False},
    {"model_path": "C:/unverified.gguf"}, {"permanent_elevation": True}])
def test_invalid_edits_are_rejected_before_policy_or_admission(runtime, changes):
    payload = dict(protocol_version=1, message_type="settings_save", request_id=str(uuid.uuid4()),
                   expected_revision="absent", changes=changes)
    assert runtime.resident_core.handle_ipc_command(payload)["error_code"] == "INVALID_REQUEST"
    assert not Path(runtime.settings_path).exists()
    with pytest.raises((ValueError, ToolArgumentError)):
        runtime.tool_registry.execute("save_settings", {"expected_revision": "absent", "changes": changes},
                                      task(runtime, "bad-input"), runtime.ledger)


def test_storage_path_cannot_be_supplied_as_tool_authority(runtime, tmp_path):
    cap = task(runtime)
    other = tmp_path / "never.json"
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute("save_settings", dict(save_args(runtime), settings_path=str(other)), cap, runtime.ledger)
    assert not other.exists() and cap.worker_controller is None


def test_selected_manual_settings_undo_is_verified_and_consumed_once(runtime):
    from pluma.core.task_supervisor import TaskState
    from pluma.memory.history_detail import selection

    original = task(runtime)
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), original, runtime.ledger)
    assert result.ok and result.verified
    runtime.supervisor.finalize_task(original.task_id, TaskState.SUCCEEDED)
    action = ActivityQuery(runtime.db).actions_for_task(original.task_id)[0]
    with runtime.db.read_snapshot() as connection:
        selected = selection(connection, original.task_id, action["id"])
    assert "Reset to default" in selected["material"]
    undo = task(runtime, "settings-undo")
    restored = runtime.tool_registry.execute("undo_last", {"selection": selected}, undo, runtime.ledger)
    assert restored.ok and restored.verified and not Path(runtime.settings_path).exists()
    claim = runtime.db.execute_read_one("SELECT state FROM undo_claims WHERE action_id=?", (action["id"],))
    assert claim["state"] == "verified"
    record = runtime.db.execute_read_one("SELECT available,rollback_ok FROM undo_records WHERE action_id=?", (action["id"],))
    assert list(record) == [0, 1]
    again = task(runtime, "settings-undo-again")
    refused = runtime.tool_registry.execute("undo_last", {}, again, runtime.ledger)
    assert not refused.ok and not Path(runtime.settings_path).exists()


def test_explicit_source_is_used_for_runtime_read_edit_and_write(tmp_path):
    paths = PlumaPaths(tmp_path / "local", tmp_path / "roaming")
    explicit = tmp_path / "explicit.json"
    explicit.write_text('{"agent":{"max_plan_steps":3}}', encoding="utf-8")
    runtime = PlumaApplicationRuntime(paths, settings_path=str(explicit))
    try:
        observed = query(runtime)
        assert observed["persisted"]["max_plan_steps"] == observed["effective"]["max_plan_steps"] == 3
        assert runtime.tool_registry.settings_path == runtime.resident_core.settings_path == str(explicit)
    finally:
        assert runtime.close(5).complete


def test_actual_settings_wire_fixture_starts_and_joins_its_graph(tmp_path):
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2] / "PLUMA.UI" / "CoreIpc.Tests" / "fixture_server.py"
    result = subprocess.run([sys.executable, str(script), "pluma_p21_" + uuid.uuid4().hex,
        str(tmp_path), "settings"], input="stop\n", text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "READY"
    assert not (tmp_path / "p21-owned" / "roaming" / "user_settings.json").exists()


def blocked_save(args, context):
    staging = Path(context.execution_binding["settings_staging"]["path"])
    (staging / "partial.tmp").write_text("owned partial transaction fixture", encoding="utf-8")
    marker = Path(context.settings_path).with_suffix(".entered")
    marker.write_text("owned settings worker", encoding="utf-8")
    while True:
        context.cancellation_token.raise_if_cancelled()
        time.sleep(.01)


def committed_then_blocked(args, context):
    from pluma.tools.settings import execute_settings
    result = execute_settings(args, context)
    if not result.ok:
        raise RuntimeError("Owned fixture did not commit settings.")
    return blocked_save(args, context)


@pytest.mark.parametrize("stop", [True, False])
@pytest.mark.parametrize("committed", [True, False])
def test_stop_or_timeout_recovers_atomic_state_and_owned_staging(runtime, stop, committed):
    spec = runtime.tool_registry.lookup("save_settings")
    runtime.tool_registry.register(spec.model_copy(update={"executor": committed_then_blocked if committed else blocked_save,
                                                        "timeout_s": 2.5}), overwrite=True)
    cap = task(runtime)
    owner_file = Path(runtime.settings_path).with_name("owner-preserved.txt")
    owner_file.write_text("preserve owner file", encoding="utf-8")
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(runtime.tool_registry.execute, "save_settings", save_args(runtime), cap, runtime.ledger)
        marker = Path(runtime.settings_path).with_suffix(".entered")
        end = time.monotonic() + 4
        while not marker.exists() and time.monotonic() < end:
            time.sleep(.01)
        assert marker.exists()
        worker = cap.worker_controller
        identity = dict(worker.worker_identity)
        directory = Path(next(resource.external_id for resource in cap.owned_resources if resource.resource_type == "temp_dir"))
        assert (directory / "partial.tmp").is_file()
        assert Path(runtime.settings_path).exists() == committed
        journal = runtime.db.execute_read_one("SELECT ownership,metadata_json FROM resources WHERE task_id=? AND external_id=?",
                                              (cap.task_id, str(directory)))
        assert journal["ownership"] == "PLUMA_CREATED" and "cleanup_identity" in json.loads(journal["metadata_json"])
        if stop:
            runtime.supervisor.stop_task(cap.task_id)
        result = future.result(5)
    if not stop:
        runtime.supervisor.stop_task(cap.task_id)
    assert not result.ok and not Path(runtime.settings_path).exists()
    assert worker.verify_cleanup() and worker.worker_identity["exit_code"] is not None
    assert worker.worker_identity["pid"] == identity["pid"]
    assert not directory.exists() and owner_file.read_text(encoding="utf-8") == "preserve owner file"
    assert any(check.identity.get("resource_type") == "temp_dir" and check.verified for check in cap.cleanup_evidence)
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert rows and not any(row["verified"] for row in rows)
    assert not cap.undo_stack and not cap.cleanup_pending
    record = runtime.db.execute_read_one("SELECT available,rollback_ok FROM undo_records WHERE action_id=?", (rows[0]["id"],))
    assert list(record) == [0, 1]


def test_pending_recovery_refuses_a_third_owner_state(runtime):
    from pluma.tools.settings import recover_pending_settings

    cap = task(runtime)
    result = runtime.tool_registry.execute("save_settings", save_args(runtime), cap, runtime.ledger)
    assert result.ok
    proof = cap.undo_stack[-1]
    store = SettingsStore(runtime.settings_path)
    owner = store.save({"agent.max_plan_steps": 6}, expected_revision=store.snapshot().revision)
    assert not recover_pending_settings({"pre_state": proof}).ok
    assert store.snapshot() == owner and cap.undo_stack[-1] == proof
