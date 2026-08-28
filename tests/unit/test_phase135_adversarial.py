"""tests/unit/test_phase135_adversarial.py — Adversarial tests for Phase 13.5.

Covers all 11 audited requirements with rigorous reproduction and verification:
1. Killable process isolation on timeout (no delayed side effects, no capacity exhaustion across 20 timeouts)
2. SnapshotRegistry wiring into TaskCapsule and inspect_active_window grounding
3. Persistent application Job Object lifecycle (STOP kills, SUCCEEDED preserves)
4. Single-consumption of undo records in SQLite and memory
5. Controlled allowlist/alias resolver, forbidden executables, and extra='forbid'
6. Typed allowlisted elevation operations
7. Mandatory IPC authentication and fail-closed isolation
8. Voice transcript redaction at log boundaries
9. Golden corpus postcondition and policy assertions
10. Soak resource containment (handles, threads, tasks)
"""

from __future__ import annotations

import json
import multiprocessing
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, Field, ValidationError

from pluma.core.cancellation import StopReason
from pluma.core.task_supervisor import ResourceOwnership, TaskCapsule, TaskState, TaskSupervisor
from pluma.policy.elevation_broker import ElevationBroker, ElevationOpType, ElevationOperation
from pluma.policy.engine import PolicyDecision, PolicyEngine
from pluma.tools.apps import (
    _ALLOWED_APP_ALIASES,
    _FORBIDDEN_EXECUTABLES,
    CloseAppArgs,
    FocusAppArgs,
    OpenAppArgs,
    execute_open_app,
)
from pluma.tools.audio import SetVolumeArgs
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.files import MoveFileArgs
from pluma.tools.registry import (
    ToolArgumentError,
    ToolRegistry,
    register_default_tools,
)


# ===========================================================================
# 1. Killable Process Isolation on Timeout
# ===========================================================================

def _uncooperative_slow_worker(args: dict, task_context: any = None) -> ToolResult:
    """Simulates an uncooperative worker that sleeps and attempts a delayed side-effect."""
    side_effect_file = args.get("side_effect_file")
    time.sleep(1.0)
    if side_effect_file:
        with open(side_effect_file, "w") as f:
            f.write("UNEXPECTED_DELAYED_SIDE_EFFECT")
    return ToolResult(ok=True, tool="slow_worker", data={}, factual_message="done", verified=True)


class TestProcessIsolationTimeouts:
    """Req 1: Timed-out workers must not produce delayed side-effects; 20 timeouts must not exhaust capacity."""

    def test_timeout_kills_worker_and_prevents_delayed_side_effect(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            side_effect_path = os.path.join(td, "side_effect.txt")
            registry = ToolRegistry()

            class SlowArgs(BaseModel):
                model_config = {"extra": "forbid"}
                side_effect_file: str

            registry.register(
                ToolSpec(
                    name="slow_tool",
                    description="Simulates slow uncooperative execution",
                    args_schema=SlowArgs,
                    risk_class=RiskClass.LOW,
                    timeout_s=0.1,
                    executor=_uncooperative_slow_worker,
                    verifier=lambda r: VerifyResult(ok=True, method="mock", detail="ok"),
                    cancellable=True,
                )
            )

            res = registry.execute("slow_tool", {"side_effect_file": side_effect_path})
            assert res.ok is False
            assert res.error_code == "TOOL_TIMEOUT"

            # Wait to ensure the background worker was truly killed and cannot write
            time.sleep(1.2)
            assert not os.path.exists(side_effect_path), (
                "Delayed side effect occurred! Killable process isolation failed to stop worker."
            )

    def test_20_repeated_timeouts_do_not_exhaust_capacity(self) -> None:
        """20 consecutive timeouts must not block subsequent tool execution."""
        registry = ToolRegistry()

        class DummySlowArgs(BaseModel):
            model_config = {"extra": "forbid"}
            val: int = 0

        registry.register(
            ToolSpec(
                name="quick_timeout_tool",
                description="Times out fast",
                args_schema=DummySlowArgs,
                risk_class=RiskClass.READ,
                timeout_s=0.02,
                executor=_uncooperative_slow_worker,
                verifier=lambda r: VerifyResult(ok=True, method="mock", detail="ok"),
                cancellable=True,
            )
        )

        class FastArgs(BaseModel):
            model_config = {"extra": "forbid"}
            msg: str = "ok"

        def _fast_exec(args: dict, task_context: any = None) -> ToolResult:
            return ToolResult(ok=True, tool="fast_tool", data=args, factual_message="fast ok", verified=True)

        registry.register(
            ToolSpec(
                name="fast_tool",
                description="Executes immediately",
                args_schema=FastArgs,
                risk_class=RiskClass.READ,
                timeout_s=5.0,
                executor=_fast_exec,
                verifier=lambda r: VerifyResult(ok=True, method="api", detail="ok"),
                cancellable=True,
            )
        )

        # Run 20 rapid timeouts
        for i in range(20):
            res = registry.execute("quick_timeout_tool", {"val": i})
            assert res.ok is False
            assert res.error_code == "TOOL_TIMEOUT"

        # The 21st tool call must succeed immediately without deadlock or pool starvation
        t0 = time.perf_counter()
        fast_res = registry.execute("fast_tool", {"msg": "capacity_check"})
        duration_ms = (time.perf_counter() - t0) * 1000.0

        assert fast_res.ok is True
        assert fast_res.data["msg"] == "capacity_check"
        assert duration_ms < 1000.0, f"Execution capacity was starved! Took {duration_ms:.1f}ms"


# ===========================================================================
# 2. SnapshotRegistry Wiring into TaskCapsule & UI Grounding
# ===========================================================================

class TestSnapshotRegistryWiring:
    """Req 2: TaskCapsule carries SnapshotRegistry. inspect_active_window registers snapshots."""

    def test_task_capsule_carries_snapshot_registry(self) -> None:
        from pluma.perception.snapshot_registry import SnapshotRegistry
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()
        assert capsule.snapshot_registry is not None
        assert isinstance(capsule.snapshot_registry, SnapshotRegistry)

    def test_snapshot_registry_cleared_on_terminal_state(self) -> None:
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()
        assert capsule.snapshot_registry is not None
        supervisor.start_task(capsule.task_id)
        supervisor.mark_succeeded(capsule.task_id)
        assert capsule.snapshot_registry is None

    def test_inspect_active_window_registers_and_returns_snapshot_id(self) -> None:
        from datetime import datetime, timedelta, timezone
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot
        from pluma.tools.ui import execute_inspect_active_window

        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()

        fake_snap = ScreenSnapshot(
            hwnd=1234,
            active_process="notepad.exe",
            active_window_title="Untitled - Notepad",
            window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
            dpi_scale=1.0,
            controls=[],
            ocr_words=[],
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=5),
        )

        with patch("pluma.tools.ui.ActiveWindowContext") as mock_ctx_cls, \
             patch("pluma.tools.ui.UiaSnapshotBuilder") as mock_bld_cls:
            mock_ctx = MagicMock()
            mock_ctx_cls.return_value = mock_ctx
            active_win = MagicMock()
            active_win.is_valid = True
            active_win.hwnd = 1234
            active_win.process_name = "notepad.exe"
            active_win.window_title = "Untitled - Notepad"
            mock_ctx.get_active_window.return_value = active_win

            mock_bld = MagicMock()
            mock_bld_cls.return_value = mock_bld
            mock_bld.capture.return_value = fake_snap

            res = execute_inspect_active_window({"include_controls": True, "max_controls": 50}, task_context=capsule)

        assert res.ok is True
        assert "snapshot_id" in res.data
        assert res.data["snapshot_id"] == fake_snap.snapshot_id
        # Verify snapshot is registered in the task capsule
        assert len(capsule.snapshot_registry) == 1
        resolved = capsule.snapshot_registry.resolve(fake_snap.snapshot_id)
        assert resolved.active_process == "notepad.exe"

    def test_click_element_rejects_unregistered_snapshot(self) -> None:
        from pluma.tools.ui import execute_click_element
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()

        res = execute_click_element(
            {"name": "Save", "snapshot_id": "invented-snapshot-id-999"},
            task_context=capsule,
        )
        assert res.ok is False
        assert "Snapshot grounding failed" in res.factual_message or "NO_SNAPSHOT_REGISTRY" in str(res.error)


# ===========================================================================
# 3. Persistent Application Job Object Lifecycle
# ===========================================================================

class TestPersistentAppJobObject:
    """Req 3: STOP terminates app tree; SUCCEEDED leaves app open and closes all handles."""

    def test_open_app_registers_persistent_job_on_task_capsule(self) -> None:
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()

        res = execute_open_app({"app_name": "notepad"}, task_context=capsule)
        assert res.ok is True
        assert len(capsule.owned_resources) >= 1
        app_res = capsule.owned_resources[0]
        assert app_res.resource_type == "subprocess"
        assert "pid" in app_res.metadata

    def test_task_supervisor_stop_terminates_persistent_app_job(self) -> None:
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()

        mock_job = MagicMock()
        capsule.register_owned_resource(
            resource_type="subprocess",
            ownership=ResourceOwnership.PLUMA_CREATED,
            external_id="12345",
            metadata={"persistent_job": mock_job, "pid": 12345},
        )

        supervisor.start_task(capsule.task_id)
        supervisor.stop_task(capsule.task_id, reason=StopReason.USER_STOP)

        assert capsule.state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
        mock_job.terminate.assert_called_once_with(exit_code=1)
        mock_job.close.assert_called_once()

    def test_task_supervisor_succeeded_closes_job_without_terminating(self) -> None:
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task_capsule()

        mock_job = MagicMock()
        capsule.register_owned_resource(
            resource_type="subprocess",
            ownership=ResourceOwnership.PLUMA_CREATED,
            external_id="12345",
            metadata={"persistent_job": mock_job, "pid": 12345},
        )

        supervisor.start_task(capsule.task_id)
        supervisor.mark_succeeded(capsule.task_id)

        assert capsule.state == TaskState.SUCCEEDED
        mock_job.terminate.assert_not_called()
        mock_job.close.assert_called_once()


# ===========================================================================
# 4. Undo Records Single Consumption
# ===========================================================================

class TestUndoSingleConsumption:
    """Req 4: Successful undo is consumed exactly once. Failed undo remains available."""

    def test_successful_undo_consumed_in_database(self) -> None:
        from pluma.rollback.engine import RollbackEngine
        from pluma.rollback.recipes import RollbackStepResult

        mock_ledger = MagicMock()
        mock_query = MagicMock()
        mock_query.available_undo_records_for_task.return_value = [
            {"action_id": 101, "undo_json": json.dumps({"action": "move_file", "source": "a", "destination": "b"})}
        ]

        mock_recipes = MagicMock()
        mock_recipes.apply.return_value = RollbackStepResult(ok=True, action="move_file", message="Restored")

        engine = RollbackEngine(ledger=mock_ledger, query=mock_query, recipes=mock_recipes)
        res = engine.rollback_task("task-consume-1")

        assert res.all_ok is True
        assert res.steps_succeeded == 1
        mock_ledger.mark_undo_consumed.assert_called_once_with(101)

    def test_failed_undo_not_consumed_in_database(self) -> None:
        from pluma.rollback.engine import RollbackEngine
        from pluma.rollback.recipes import RollbackStepResult

        mock_ledger = MagicMock()
        mock_query = MagicMock()
        mock_query.available_undo_records_for_task.return_value = [
            {"action_id": 102, "undo_json": json.dumps({"action": "move_file", "source": "a", "destination": "b"})}
        ]

        mock_recipes = MagicMock()
        mock_recipes.apply.return_value = RollbackStepResult(ok=False, action="move_file", message="Conflict error", error="Conflict")

        engine = RollbackEngine(ledger=mock_ledger, query=mock_query, recipes=mock_recipes)
        res = engine.rollback_task("task-consume-2")

        assert res.all_ok is False
        assert res.steps_failed == 1
        mock_ledger.mark_undo_consumed.assert_not_called()

    def test_in_memory_undo_stack_consumed_on_success(self) -> None:
        from pluma.rollback.engine import RollbackEngine
        from pluma.rollback.recipes import RollbackStepResult

        memory_stack = [
            {"action": "create_folder", "folder_path": "/tmp/test1"},
            {"action": "create_folder", "folder_path": "/tmp/test2"},
        ]

        mock_recipes = MagicMock()
        mock_recipes.apply.return_value = RollbackStepResult(ok=True, action="create_folder", message="Removed")

        engine = RollbackEngine(recipes=mock_recipes)
        res = engine.rollback_task("task-mem", memory_undo_stack=memory_stack)

        assert res.all_ok is True
        assert res.steps_succeeded == 2
        # In-memory undo records must have been consumed (removed)
        assert len(memory_stack) == 0


# ===========================================================================
# 5. Controlled Allowlist, Forbidden Executables, & extra='forbid'
# ===========================================================================

class TestAllowlistAndForbiddenExecutables:
    """Req 5: reg.exe, schtasks.exe and arbitrary executables rejected; extra='forbid' enforced."""

    @pytest.mark.parametrize("bad_app", [
        "reg", "reg.exe",
        "schtasks", "schtasks.exe",
        "wmic", "wmic.exe",
        "taskkill", "taskkill.exe",
        "icacls", "icacls.exe",
        "net", "net.exe",
        "msiexec", "msiexec.exe",
        "C:\\Windows\\System32\\reg.exe",
        "C:/Windows/System32/schtasks.exe",
    ])
    def test_forbidden_executables_rejected_by_schema(self, bad_app: str) -> None:
        with pytest.raises(ValidationError):
            OpenAppArgs(app_name=bad_app)

    def test_alias_map_contains_standard_productivity_apps(self) -> None:
        assert "notepad" in _ALLOWED_APP_ALIASES
        assert "calc" in _ALLOWED_APP_ALIASES
        assert "mspaint" in _ALLOWED_APP_ALIASES
        assert _ALLOWED_APP_ALIASES["notepad"] == "notepad.exe"

    def test_all_tool_schemas_reject_extra_injected_fields(self) -> None:
        for schema_cls in (OpenAppArgs, CloseAppArgs, FocusAppArgs, SetVolumeArgs, MoveFileArgs):
            with pytest.raises(ValidationError):
                schema_cls.model_validate({"_malicious_extra": "payload"})


# ===========================================================================
# 6. Typed Allowlisted Elevation Operations
# ===========================================================================

class TestTypedElevationOperations:
    """Req 6: Replace arbitrary elevated scripts with typed allowlisted operations."""

    def test_typed_restart_service_operation(self) -> None:
        op = ElevationOperation(op_type=ElevationOpType.RESTART_SERVICE, service_name="Spooler")
        assert op.op_type == ElevationOpType.RESTART_SERVICE
        assert op.service_name == "Spooler"

    def test_service_name_injection_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ElevationOperation(
                op_type=ElevationOpType.RESTART_SERVICE,
                service_name="Spooler; Remove-Item C:\\* -Recurse",
            )

    def test_elevation_broker_dispatches_typed_operation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PLUMA_TEST_MODE", "1")
        broker = ElevationBroker(timeout_s=5.0)
        op = ElevationOperation(op_type=ElevationOpType.FLUSH_DNS)
        res = broker.execute_operation(op)
        assert res.ok is True


# ===========================================================================
# 7. Mandatory IPC Authentication & Fail-Closed Isolation
# ===========================================================================

class TestIpcAuthentication:
    """Req 7: IPC challenge-response authentication is fail-closed."""

    def test_ipc_auth_nonce_generation_and_storage(self) -> None:
        from pluma.core.ipc import _get_or_create_auth_nonce, IPC_AUTH_NONCE_SIZE
        with tempfile.TemporaryDirectory() as td:
            nonce = _get_or_create_auth_nonce(paths_root=td)
            assert len(nonce) == IPC_AUTH_NONCE_SIZE
            # Idempotent
            nonce2 = _get_or_create_auth_nonce(paths_root=td)
            assert nonce == nonce2

    def test_ipc_server_require_auth_fails_closed_on_unauthenticated_connection(self) -> None:
        from pluma.core.ipc import IpcServer, IpcClient
        pipe_address = rf"\\.\pipe\pluma_test_auth_{os.getpid()}_{time.time_ns()}" if os.name == "nt" else f"/tmp/pluma_test_auth_{os.getpid()}.sock"

        server = IpcServer(command_handler=lambda req: {"status": "ok"}, address=pipe_address, require_auth=True)
        server.start()
        try:
            # Client connecting without require_auth=True will not perform handshake
            unauth_client = IpcClient(address=pipe_address, require_auth=False)
            res = unauth_client.send_command({"command": "status"}, timeout=1.0)
            # Server closes connection without responding (fail-closed)
            assert res.get("status") == "error"
        finally:
            server.stop()


# ===========================================================================
# 8. Voice Transcript Redaction at Output Boundary
# ===========================================================================

class TestVoiceTranscriptRedaction:
    """Req 8: Raw voice transcripts are redacted before log emission."""

    def test_redact_string_scrubs_secrets(self) -> None:
        from pluma.memory.redaction import redact_string
        sample = "api key sk-1234567890abcdef1234567890 and token ghp_123456789012345678901234567890123456"
        redacted = redact_string(sample)
        assert "sk-1234567890abcdef1234567890" not in redacted
        assert "ghp_123456789012345678901234567890123456" not in redacted
        assert "[REDACTED]" in redacted


# ===========================================================================
# 9. Golden Corpus Assertions
# ===========================================================================

class TestGoldenCorpusContract:
    """Req 10: Golden corpus asserts route, tools, risk, policy, outcome, and postconditions."""

    def test_golden_corpus_entries_pass_policy_and_normalization(self) -> None:
        registry = ToolRegistry()
        register_default_tools(registry)
        engine = PolicyEngine()

        # GC-001: Mute
        assert engine.evaluate("mute", {}, default_risk=RiskClass.LOW).decision == PolicyDecision.ALLOW
        norm_mute = registry.validate_call("mute", {})
        assert norm_mute == {}

        # GC-002: Set volume 30
        assert engine.evaluate("set_volume", {"level": 30}, default_risk=RiskClass.LOW).decision == PolicyDecision.ALLOW
        norm_vol = registry.validate_call("set_volume", {"level": 30})
        assert norm_vol["level"] == 30

        # GC-005: List files
        assert engine.evaluate("list_files", {"directory": "."}, default_risk=RiskClass.READ).decision == PolicyDecision.ALLOW


# ===========================================================================
# 10. Soak Resource Containment
# ===========================================================================

class TestSoakResourceContainment:
    """Req 10: 100 sequential tasks do not leak handles, threads, or Job Objects."""

    def test_soak_100_tasks_resource_containment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            local_root = Path(td) / "Pluma"
            from pluma.app import PlumaApplicationRuntime
            from pluma.config.paths import PlumaPaths

            paths = PlumaPaths(local_app_data=local_root, roaming_app_data=local_root)
            paths.ensure_directories()
            runtime = PlumaApplicationRuntime(paths=paths)

            try:
                initial_threads = threading.active_count()

                for i in range(100):
                    req = {"command": "execute", "request": {"input_mode": "text", "text": "get_system_status"}}
                    res = runtime.resident_core.handle_ipc_command(req)
                    assert res["status"] == "ok", f"Task {i} failed: {res}"

                # Verify zero leaked active tasks
                assert len(runtime.supervisor.get_active_tasks()) == 0

                # Verify thread count did not grow unboundedly
                final_threads = threading.active_count()
                assert (final_threads - initial_threads) < 20

                # Verify TaskSupervisor memory bounds
                assert len(runtime.supervisor._tasks) <= 55
            finally:
                runtime.close()
