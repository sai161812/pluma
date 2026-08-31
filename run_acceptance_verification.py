"""run_acceptance_verification.py — Comprehensive Windows Acceptance & Defect Verification Suite."""

import os
import sys
import time
import shutil
import tempfile
import pytest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pluma.app import PlumaApplicationRuntime
from pluma.brain.schemas import Plan, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.cancellation import CancellationToken
from pluma.core.multi_step import MultiStepOrchestrator
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec
from pluma.tools.registry import ToolRegistry, register_default_tools
from pluma.verify.common import verify_noop


def verify_all_audit_items() -> None:
    print("=" * 80)
    print("STARTING WINDOWS 11 ACCEPTANCE VERIFICATION FOR ALL AUDIT ITEMS")
    print(f"Platform: {sys.platform} | Python: {sys.version}")
    print("=" * 80)

    test_temp = Path(tempfile.mkdtemp(prefix="pluma_acceptance_"))

    try:
        # 1. Pre-mutation Rollback Capture
        print("[AUDIT 1] Testing Pre-mutation Rollback State Capture...")
        reg = ToolRegistry()
        register_default_tools(reg)
        src = test_temp / "original.txt"
        src.write_text("initial-content", encoding="utf-8")
        dst = test_temp / "moved.txt"
        capsule = TaskCapsule(request_id="req-1")
        res = reg.execute("move_file", {"source": str(src), "destination": str(dst)}, task_context=capsule)
        assert res.ok is True
        assert res.undo_record is not None
        assert res.undo_record["source"] == str(src)
        assert res.undo_record["destination"] == str(dst)
        assert dst.exists() and dst.read_text(encoding="utf-8") == "initial-content"
        print("  -> PASSED: Undo record captured pre-state; file moved cleanly.")

        # 2. Tool Timeout & Route Subset Enforcement
        print("[AUDIT 2] Testing Tool Timeout & Route-Specific Tool Subsets...")
        def slow_fn(args: dict, ctx: any) -> ToolResult:
            time.sleep(1.0)
            return ToolResult.success("slow", {})
        reg.register(ToolSpec(
            name="slow_fn",
            description="timeout test",
            version="1.0",
            args_schema={},
            risk_class=RiskClass.READ,
            timeout_s=0.1,
            executor=slow_fn,
            verifier=verify_noop,
        ))
        res_timeout = reg.execute("slow_fn", {})
        assert res_timeout.ok is False
        assert res_timeout.error_code == "TOOL_TIMEOUT"
        assert ToolSubsetSelector.is_tool_permitted("click_element", RouteMode.SCREEN) is True
        assert ToolSubsetSelector.is_tool_permitted("move_file", RouteMode.SCREEN) is False
        print("  -> PASSED: Timeout triggered after 0.1s and route subset gating active.")

        # 3. STOP Latch Prevents SUCCEEDED State
        print("[AUDIT 3] Testing Strict STOP Latch & Cancellation Transitions...")
        supervisor = TaskSupervisor()
        multi = MultiStepOrchestrator(registry=reg, supervisor=supervisor)
        def cancel_fn(args: dict, ctx: any) -> ToolResult:
            if ctx and hasattr(ctx, "cancellation_token"):
                ctx.cancellation_token.cancel()
            return ToolResult.success("get_system_status", data={}, factual_message="Ran")
        reg.register(ToolSpec(
            name="get_system_status",
            description="cancels during run",
            version="1.0",
            args_schema={},
            risk_class=RiskClass.READ,
            timeout_s=5.0,
            executor=cancel_fn,
            verifier=verify_noop,
        ), overwrite=True)
        cap3 = supervisor.create_task_capsule(request_id="req-3")
        plan3 = Plan(route=RouteMode.SMART, mode="direct", steps=[ToolCall(tool="get_system_status", arguments={}, purpose="test stop")])
        res3 = multi.execute_plan(capsule=cap3, initial_plan=plan3, command_text="cancel test")
        assert res3.final_state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
        assert cap3.state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
        assert res3.final_state != TaskState.SUCCEEDED
        print("  -> PASSED: Cancelled task transitioned strictly to STOPPED.")

        # 4. Comprehensive SQLite Redaction
        print("[AUDIT 4] Testing Comprehensive SQLite Redaction...")
        db_path = test_temp / "redact.db"
        db = DbConnection(str(db_path))
        db.open()
        ledger = ActivityLedger(db=db)
        ledger.insert_task(TaskRecord(
            task_id="t-redact",
            request_id="r-redact",
            input_mode="text",
            command_text="save token sk-proj-12345678901234567890 to disk",
        ))
        row = db.execute_read_one("SELECT command_text FROM tasks WHERE task_id = ?", ("t-redact",))
        assert "sk-proj-12345678901234567890" not in row[0]
        assert "[REDACTED]" in row[0]
        action = ActionRecord(
            task_id="t-redact",
            step_index=1,
            tool="clipboard_read",
            args_raw={"api_key": "ghp_123456789012345678901234567890123456"},
            risk="LOW",
            adapter="native",
            result_data={"secret": "SuperSecretPassword123!"},
            verification_detail={"auth": "AKIAIOSFODNN7EXAMPLE"},
            error_detail={"err": "auth failure token=sk-abcdefghijklmnopqrstuvwxyz123456"},
        )
        row_id = ledger.insert_action(action)
        act_row = db.execute_read_one("SELECT args_json_sanitized, result_json, verification_json, error_json FROM actions WHERE rowid = ?", (row_id,))
        for col in act_row:
            assert "SuperSecretPassword123!" not in col
            assert "ghp_123456789012345678901234567890123456" not in col
            assert "AKIAIOSFODNN7EXAMPLE" not in col
            assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in col
            assert "[REDACTED]" in col
        db.close()
        print("  -> PASSED: All secret patterns and dictionary values redacted before SQLite writes.")

        # 5. Production Runtime Planner & Model Lifecycle Wiring
        print("[AUDIT 5] Testing Production Runtime Dependency Graph & Model Wiring...")
        paths = PlumaPaths(local_app_data=test_temp)
        runtime = PlumaApplicationRuntime(paths=paths)
        assert runtime.llm_lifecycle is not None
        assert runtime.voice_lifecycle is not None
        assert runtime.orchestrator._llm_manager is runtime.llm_lifecycle
        runtime.close()
        print("  -> PASSED: Runtime successfully wires LLM & Voice model lifecycles.")

        # 6. Config Path Loading
        print("[AUDIT 6] Testing load_config(user_config_path)...")
        custom_cfg = test_temp / "override.yaml"
        custom_cfg.write_text("agent:\n  max_plan_steps: 12\n", encoding="utf-8")
        loaded = load_config(user_config_path=custom_cfg)
        assert loaded["agent"]["max_plan_steps"] == 12
        print("  -> PASSED: Custom configuration path loaded and merged successfully.")

        # 7. Process Ownership & Terminal Task Cleanup
        print("[AUDIT 7] Testing Terminal Task Temp Cleanup & Ownership...")
        task_dir = paths.task_temp_dir("cleanup_test")
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "temp.dat").write_text("temp", encoding="utf-8")
        sup7 = TaskSupervisor(paths=paths)
        cap7 = sup7.create_task_capsule(task_id="cleanup_test", request_id="req-7")
        sup7.start_task(cap7.task_id)
        sup7.mark_succeeded(cap7.task_id)
        assert not task_dir.exists()
        print("  -> PASSED: Terminal state transition automatically purged task temp directory.")

        print("=" * 80)
        print("ALL 7 AUDIT CHECKS PASSED DETERMINISTICALLY")
        print("=" * 80)

    finally:
        shutil.rmtree(test_temp, ignore_errors=True)


if __name__ == "__main__":
    verify_all_audit_items()
    print("\nRUNNING COMPLETE PYTEST SUITE (467 TESTS)...")
    pytest_exit = pytest.main(["tests/", "-v", "--tb=short"])
    print(f"\nFINAL PYTEST EXIT CODE: {pytest_exit}")
    sys.exit(pytest_exit)
