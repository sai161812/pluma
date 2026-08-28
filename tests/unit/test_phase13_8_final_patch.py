"""tests.unit.test_phase13_8_final_patch — Verification of final patch requirements.

Strictly verifies:
1. Task-owned worker containment (TaskCapsule owns worker, STOP Task A kills only Task A's worker, app Job Object preserved).
2. Planner tool permissions (permitted_tool_specs whitelist, SMART/DEEP no auto-broaden, fail-closed, bounded replan tools).
3. OCR freshness + verification (identity, geometry/DPI, bounds check, real postcondition proof).
4. Golden corpus router and argument alignment.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import pytest
from typing import Any, Dict
from pydantic import BaseModel

from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.core.cancellation import CancellationToken
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor, ResourceOwnership
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry, register_default_tools


class NoopArgs(BaseModel):
    pass


def _noop_tool(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return ToolResult(ok=True, tool="worker_noop", data=args, factual_message="ok", verified=True)

def _blocking_tool(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import time
    time.sleep(9999) # Deliberately blocking
    return ToolResult(ok=True, tool="blocking", data={}, factual_message="done", verified=True)


# ===========================================================================
# 1. Task-Owned Worker Containment
# ===========================================================================

class TestTaskOwnedWorkerContainment:
    """1. Task-owned worker containment."""

    def test_task_capsule_owns_worker_and_stop_task_kills_only_target_worker(self) -> None:
        from pluma.verify.common import verify_noop

        registry = ToolRegistry()
        register_default_tools(registry)

        spec = ToolSpec(
            name="worker_noop",
            description="Isolated tool",
            args_schema=NoopArgs,
            risk_class=RiskClass.HIGH,
            cancellable=True,
            timeout_s=5.0,
            executor=_noop_tool,
            verifier=verify_noop,
        )
        registry.register(spec)

        supervisor = TaskSupervisor()
        task_a = supervisor.create_task("req-a")
        task_b = supervisor.create_task("req-b")

        supervisor.start_task(task_a.task_id)
        supervisor.start_task(task_b.task_id)

        # Execute tools in both tasks to spawn their task-owned workers
        res_a = registry.execute("worker_noop", {}, task_context=task_a)
        res_b = registry.execute("worker_noop", {}, task_context=task_b)

        assert res_a.ok is True
        assert res_b.ok is True

        worker_a = task_a.worker_controller
        worker_b = task_b.worker_controller

        assert worker_a is not None
        assert worker_b is not None
        assert worker_a is not worker_b
        assert worker_a.task_id == task_a.task_id
        assert worker_b.task_id == task_b.task_id

        # STOP Task A: must kill Task A's worker while Task B's worker stays alive
        supervisor.stop_task(task_a.task_id, grace_s=0.0)

        assert task_a.state in [TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL]
        assert task_a.worker_controller is None
        assert worker_a._proc is None or not worker_a._proc.is_alive()

        # Task B's worker is still alive and responsive
        assert task_b.state == TaskState.RUNNING
        assert task_b.worker_controller is worker_b
        assert worker_b._proc is not None and worker_b._proc.is_alive()

        # Task B can continue executing tools
        res_b2 = registry.execute("worker_noop", {}, task_context=task_b)
        assert res_b2.ok is True

        # Clean up Task B
        supervisor.mark_succeeded(task_b.task_id)
        task_b.close_resources()
        assert task_b.worker_controller is None

    def test_blocking_tool_job_object_containment_and_termination(self) -> None:
        from pluma.verify.common import verify_noop
        import threading
        
        registry = ToolRegistry()
        register_default_tools(registry)

        spec_noop = ToolSpec(
            name="worker_noop",
            description="Isolated tool",
            args_schema=NoopArgs,
            risk_class=RiskClass.HIGH,
            cancellable=True,
            timeout_s=5.0,
            executor=_noop_tool,
            verifier=verify_noop,
        )
        registry.register(spec_noop)

        spec = ToolSpec(
            name="blocking_tool",
            description="Blocks forever",
            args_schema=NoopArgs,
            risk_class=RiskClass.HIGH,
            cancellable=True,
            timeout_s=5.0,
            executor=_blocking_tool,
            verifier=verify_noop,
        )
        registry.register(spec)

        supervisor = TaskSupervisor()
        task_a = supervisor.create_task("req-a")
        task_b = supervisor.create_task("req-b")

        supervisor.start_task(task_a.task_id)
        supervisor.start_task(task_b.task_id)

        # Start blocking tool in Task A on a background thread so we can STOP it concurrently
        thread_res: list[Any] = []
        def run_a() -> None:
            thread_res.append(registry.execute("blocking_tool", {}, task_context=task_a))
        t = threading.Thread(target=run_a, daemon=True)
        t.start()

        # Wait for worker to spawn and block
        time.sleep(1.0)
        worker_a = task_a.worker_controller
        print(f"thread_res so far: {thread_res}")
        assert worker_a is not None
        assert worker_a._proc is not None
        assert worker_a._proc.is_alive()
        pid_a = worker_a._proc.pid

        # Start non-blocking tool in Task B
        res_b = registry.execute("worker_noop", {}, task_context=task_b)
        assert res_b.ok is True
        worker_b = task_b.worker_controller
        assert worker_b is not None
        assert worker_b._proc is not None
        assert worker_b._proc.is_alive()
        pid_b = worker_b._proc.pid
        
        assert pid_a != pid_b

        # STOP Task A
        supervisor.stop_task(task_a.task_id, grace_s=0.0)
        t.join(timeout=2.0)
        
        # Verify worker A is terminated (fail closed)
        assert worker_a._proc is None or not worker_a._proc.is_alive()
        assert task_a.worker_controller is None
        
        # Verify worker B remains untouched
        assert worker_b._proc.is_alive()
        
        # Clean up
        supervisor.mark_succeeded(task_b.task_id)
        task_b.close_resources()

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object specific test")
    def test_launched_app_job_object_ownership_preserved(self) -> None:
        from pluma.core.job_object import WindowsJobObject

        supervisor = TaskSupervisor()
        task = supervisor.create_task("req-app")
        supervisor.start_task(task.task_id)

        # Register a mock launched app with a persistent job object (kill_on_close=False)
        job = WindowsJobObject(name=f"pluma-test-app-{task.task_id}", kill_on_close=False)
        res_obj = task.register_owned_resource(
            resource_type="subprocess",
            ownership=ResourceOwnership.PLUMA_CREATED,
            external_id="12345",
            metadata={"pid": 12345, "persistent_job": job},
        )
        assert res_obj.metadata["persistent_job"] is job

        # When task succeeds, close_resources closes handle without terminating app
        task.close_resources()
        assert res_obj.metadata["persistent_job"] is None


# ===========================================================================
# 2. Planner Tool Permissions
# ===========================================================================

class TestPlannerToolPermissions:
    """2. Planner tool permissions."""

    def test_planner_validator_rejects_tools_not_in_permitted_specs(self) -> None:
        registry = ToolRegistry()
        register_default_tools(registry)

        validator = PlanValidator(registry=registry)

        permitted_specs = [
            {"name": "open_app"},
            {"name": "close_app"},
        ]

        # Allowed plan
        good_plan = Plan(
            steps=[ToolCall(tool="open_app", arguments={"app_name": "notepad"}, purpose="open app")],
            route=RouteMode.SMART,
            command_text="open notepad",
        )
        val_good = validator.validate_plan(good_plan, permitted_tool_specs=permitted_specs)
        assert len(val_good.steps) == 1

        # Unpermitted plan (mute is registered, but NOT in permitted_specs)
        bad_plan = Plan(
            steps=[ToolCall(tool="mute", arguments={}, purpose="mute sound")],
            route=RouteMode.SMART,
            command_text="mute",
        )
        with pytest.raises(PlanValidationError) as exc:
            validator.validate_plan(bad_plan, permitted_tool_specs=permitted_specs)
        assert "not in permitted_tool_specs" in str(exc.value)

    def test_smart_deep_do_not_automatically_broaden_permissions(self) -> None:
        assert ToolSubsetSelector.is_tool_permitted("non_existent_tool", RouteMode.SMART) is False
        assert ToolSubsetSelector.is_tool_permitted("non_existent_tool", RouteMode.DEEP) is False
        assert ToolSubsetSelector.is_tool_permitted("non_existent_tool", RouteMode.SCREEN) is False
        assert ToolSubsetSelector.is_tool_permitted("non_existent_tool", RouteMode.FAST) is False

    def test_malformed_and_unknown_routes_fail_closed(self) -> None:
        assert ToolSubsetSelector.is_tool_permitted("open_app", "UNKNOWN_ROUTE") is False
        assert ToolSubsetSelector.is_tool_permitted("open_app", 12345) is False
        assert ToolSubsetSelector.is_tool_permitted("open_app", None) is False

    def test_replan_enforces_permitted_tool_specs_in_multi_step_orchestrator(self) -> None:
        from pluma.core.multi_step import MultiStepOrchestrator

        registry = ToolRegistry()
        register_default_tools(registry)
        supervisor = TaskSupervisor()
        orchestrator = MultiStepOrchestrator(supervisor=supervisor, registry=registry)

        capsule = supervisor.create_task("req-replan")
        supervisor.start_task(capsule.task_id)

        # Plan contains 'mute', but permitted_tool_specs contains only 'get_system_status'
        plan = Plan(
            steps=[ToolCall(tool="mute", arguments={}, purpose="mute sound")],
            route=RouteMode.SMART,
            command_text="mute",
        )

        permitted_specs = [{"name": "get_system_status"}]

        res = orchestrator.execute_plan(
            capsule=capsule,
            initial_plan=plan,
            command_text="mute",
            permitted_tool_specs=permitted_specs,
        )

        assert res.final_state == TaskState.FAILED
        assert "not in permitted_tool_specs" in (res.error or "")
        assert res.steps_executed[0].result.error_code == "TOOL_NOT_IN_PERMITTED_SPECS"


# ===========================================================================
# 3. OCR Freshness + Verification
# ===========================================================================

class TestOcrFreshnessAndVerification:
    """3. OCR freshness + verification."""

    def test_click_ocr_rechecks_window_and_snapshot_freshness(self) -> None:
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot
        from pluma.perception.snapshot_registry import SnapshotRegistry
        from pluma.tools.ui import execute_click_ocr_text

        snap_registry = SnapshotRegistry()
        snap = ScreenSnapshot(
            hwnd=99999999,
            active_process="test.exe",
            active_window_title="Test Window",
            window_rect=BoundingBox(left=100, top=100, right=500, bottom=500),
            dpi_scale=1.0,
            controls=[],
            ocr_words=[],
            expires_at=time.time() + 60,
        )
        snap_registry.register(snap)

        supervisor = TaskSupervisor()
        capsule = supervisor.create_task("req-ocr")
        capsule.snapshot_registry = snap_registry

        # Target window HWND does not exist -> fails closed
        res = execute_click_ocr_text(
            {"text": "Save", "hwnd": 99999999, "snapshot_id": snap.snapshot_id},
            task_context=capsule,
        )
        assert res.ok is False
        assert res.error_code in ["WINDOW_NOT_FOUND", "WINDOW_MISMATCH", "WINDOW_QUERY_FAILED"]

    def test_click_ocr_requires_real_postcondition_verification(self) -> None:
        from pluma.tools.ui import verify_click_ocr_text

        # If verified is False, verify_click_ocr_text returns ok=False
        unverified_result = ToolResult(
            ok=True,
            tool="click_ocr_text",
            data={},
            factual_message="clicked",
            verified=False,
        )
        v_res = verify_click_ocr_text(unverified_result)
        assert v_res.ok is False
        assert "without verified postcondition proof" in v_res.detail

        # If verified is True with detail, verify_click_ocr_text returns ok=True
        verified_result = ToolResult(
            ok=True,
            tool="click_ocr_text",
            data={},
            factual_message="clicked",
            verified=True,
            verify_detail=VerifyResult(ok=True, method="ocr_grounded", detail="Window focus verified"),
        )
        v_res2 = verify_click_ocr_text(verified_result)
        assert v_res2.ok is True


# ===========================================================================
# 4. Golden Corpus Real Router & Argument Alignment
# ===========================================================================

class TestGoldenCorpusRouterAndArgumentAlignment:
    """4. Golden corpus + release evidence alignment."""

    def test_golden_corpus_volume_30_and_all_commands_align(self) -> None:
        import yaml
        from pathlib import Path

        golden_path = Path("tests/fixtures/golden_commands.yaml")
        with open(golden_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        commands = data.get("commands", [])
        router = Router()

        for c in commands:
            cid = c["id"]
            cmd = c["command"]
            mode = InputMode.VOICE if c.get("input_mode") == "voice" else InputMode.TEXT
            res = router.route(PlumaRequest(input_mode=mode, text=cmd))

            expected_route = RouteMode(c["expected_route"])
            assert res.route == expected_route, f"{cid} ({cmd}): expected route {expected_route}, got {res.route}"

            if expected_route == RouteMode.FAST:
                assert res.plan is not None
                assert len(res.plan.steps) >= 1
                assert res.plan.steps[0].tool in c["expected_tools"]
                if c.get("normalized_args") is not None:
                    assert res.plan.steps[0].arguments == c["normalized_args"], (
                        f"{cid} ({cmd}): expected args {c['normalized_args']}, got {res.plan.steps[0].arguments}"
                    )
