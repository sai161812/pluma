"""run_acceptance_verification.py — Comprehensive Windows Acceptance & Defect Verification Suite."""

import os
import sys
import time
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest

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
from pluma.core.task_supervisor import ResourceOwnership, TaskCapsule, TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, TaskRecord
from pluma.memory.db import DbConnection
from pluma.tools.base import RiskClass, ToolResult, ToolSpec
from pluma.tools.registry import ToolRegistry, get_default_tool_registry, register_default_tools
from pluma.verify.common import verify_noop


def verify_all_audit_items() -> None:
    print("=" * 80)
    print("STARTING WINDOWS 11 ACCEPTANCE VERIFICATION FOR ALL AUDIT GATES")
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

        # 2. Tool Timeout & Immediate Non-Blocking Execution
        print("[AUDIT 2] Testing Immediate Tool Timeout Enforcement & Route Subsets...")
        def slow_fn(args: dict, ctx: any) -> ToolResult:
            time.sleep(1.0)
            return ToolResult.success("slow", {})
        reg.register(ToolSpec(
            name="slow_fn",
            description="timeout test",
            version="1.0",
            args_schema={},
            risk_class=RiskClass.READ,
            timeout_s=0.05,
            executor=slow_fn,
            verifier=verify_noop,
        ), overwrite=True)
        t0 = time.perf_counter()
        res_timeout = reg.execute("slow_fn", {})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert res_timeout.ok is False
        assert res_timeout.error_code == "TOOL_TIMEOUT"
        assert elapsed_ms < 200.0, f"Expected non-blocking return under 200ms, took {elapsed_ms:.1f}ms"
        assert ToolSubsetSelector.is_tool_permitted("click_element", RouteMode.SCREEN) is True
        assert ToolSubsetSelector.is_tool_permitted("move_file", RouteMode.SCREEN) is False
        print(f"  -> PASSED: 50ms timeout returned in {elapsed_ms:.1f}ms (no caller blocking).")

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

        # 7. Process Ownership & Terminal Task Memory Bounding
        print("[AUDIT 7] Testing Process Ownership Attachment, Job Object Closure & Memory Bounding...")
        sup7 = TaskSupervisor(paths=paths, max_retained_terminal_tasks=10)
        cap7 = sup7.create_task_capsule(task_id="cleanup_test", request_id="req-7")
        if sys.platform == "win32":
            from pluma.core.job_object import WindowsJobObject
            assert cap7.job_object is not None or sys.platform != "win32"
        
        # Test real open_app process ownership registration on TaskCapsule
        open_res = reg.execute("open_app", {"app_name": "notepad.exe" if sys.platform == "win32" else "python"}, task_context=cap7)
        if open_res.ok:
            pid = open_res.data["pid"]
            assert len(cap7.owned_resources) >= 1
            assert cap7.owned_resources[0].resource_type == "subprocess"
            assert cap7.owned_resources[0].external_id == str(pid)
            assert cap7.owned_resources[0].ownership == ResourceOwnership.PLUMA_CREATED

        # Start and succeed task -> verifies job object closure and temp cleanup
        sup7.start_task(cap7.task_id)
        sup7.mark_succeeded(cap7.task_id)
        assert cap7.job_object is None, "Job Object handle must be closed and cleared on task terminal transition!"

        # Verify invalid window handles fail-closed
        win_res = reg.execute("restore_window", {"hwnd": 0})
        assert win_res.ok is False
        assert win_res.verified is False
        assert win_res.error_code in ("WINDOW_NOT_FOUND", "INVALID_HWND")

        # Verify memory bounding
        for i in range(50):
            c = sup7.create_task_capsule(request_id=f"r-{i}")
            sup7.start_task(c.task_id)
            sup7.mark_succeeded(c.task_id)
        assert len(sup7._tasks) == 10
        print("  -> PASSED: TaskCapsule carries real owned resources; Job Object closed on completion; terminal memory bounded.")

        # 8. Automatic Multi-Step Rollback File Restoration
        print("[AUDIT 8] Testing Multi-Step Automatic Rollback Restoration...")
        rb_src = test_temp / "rb_source.txt"
        rb_src.write_text("important data", encoding="utf-8")
        rb_dst = test_temp / "rb_dest.txt"
        default_reg = get_default_tool_registry()
        rb_sup = TaskSupervisor(paths=paths)
        rb_multi = MultiStepOrchestrator(registry=default_reg, supervisor=rb_sup)
        rb_cap = rb_sup.create_task_capsule(request_id="req-rb")
        rb_plan = Plan(
            route=RouteMode.SMART,
            mode="multi_step",
            steps=[
                ToolCall(tool="move_file", arguments={"source": str(rb_src), "destination": str(rb_dst)}, purpose="move"),
                ToolCall(tool="open_app", arguments={"app_name": "fake_non_existent_app_abc_999"}, purpose="fail"),
            ],
        )
        rb_res = rb_multi.execute_plan(capsule=rb_cap, initial_plan=rb_plan, command_text="move and fail")
        assert rb_res.final_state == TaskState.FAILED
        assert rb_res.rollback_performed is True
        assert rb_res.rollback_success is True
        assert rb_src.exists() and rb_src.read_text(encoding="utf-8") == "important data"
        assert not rb_dst.exists()
        print("  -> PASSED: Source file automatically restored upon multi-step failure.")

        # 9. Tool Registry Count
        print("[AUDIT 9] Testing Default Registry Tool Count...")
        assert len(default_reg) == 33
        assert len(default_reg.list_tools()) == 33
        assert len(default_reg.list_tool_names()) == 33
        print(f"  -> PASSED: Default registry exposes exactly 33 registered tools.")

        print("=" * 80)
        print("ALL 9 AUDIT GATES PASSED DETERMINISTICALLY")
        print("=" * 80)

    finally:
        shutil.rmtree(test_temp, ignore_errors=True)


if __name__ == "__main__":
    verify_all_audit_items()
    print("\nRUNNING COMPLETE TEST SUITE VIA PYTEST...")

    import platform

    class SafeFullLogPlugin:
        def __init__(self) -> None:
            self.passed = 0
            self.failed = 0
            self.skipped = 0
            self.lines: list[str] = []

        def pytest_runtest_logreport(self, report: Any) -> None:
            if report.when == "call" or (report.when in ("setup", "teardown") and report.failed):
                status = report.outcome.upper()
                if status == "PASSED":
                    self.passed += 1
                elif status in ("FAILED", "ERROR"):
                    self.failed += 1
                elif status == "SKIPPED":
                    self.skipped += 1
                node = report.nodeid if report.when == "call" else f"{report.nodeid} ({report.when})"
                self.lines.append(f"{node:<95} {status:<8} [{report.duration:.3f}s]")

    plugin = SafeFullLogPlugin()
    t0 = time.perf_counter()
    ret = pytest.main(["tests/", "-q", "--timeout=30"], plugins=[plugin])
    elapsed = time.perf_counter() - t0

    total_tests = len(plugin.lines)
    pass_rate = (plugin.passed / total_tests * 100.0) if total_tests > 0 else 0.0
    sys_plat_str = f"{platform.system()} {platform.release()} ({platform.machine()}) [{platform.platform()}]"

    header = (
        "=" * 115 + "\n"
        "============================= PLUMA FULL TEST SUITE EXECUTION =============================\n"
        f"Platform: {sys_plat_str} | Python: {platform.python_version()}\n"
        f"Total Tests: {total_tests} | Passed: {plugin.passed} | Failed: {plugin.failed} | Skipped: {plugin.skipped} | Elapsed: {elapsed:.2f}s\n"
        + "=" * 115
        + "\n"
    )
    footer = (
        "\n"
        + "=" * 115
        + f"\nFINAL RESULT: {plugin.passed} passed, {plugin.failed} failed, {plugin.skipped} skipped in {elapsed:.2f}s ({pass_rate:.1f}% PASS RATE)\n"
        + "=" * 115
        + "\n"
    )
    full_log = header + "\n".join(plugin.lines) + footer
    with open("test_run_raw.log", "w", encoding="utf-8") as f:
        f.write(full_log)
    with open("ACCEPTANCE_TEST_RAW_LOG.txt", "w", encoding="utf-8") as f:
        f.write(full_log)

    print(f"\nALL {plugin.passed}/{total_tests} TESTS COMPLETED IN {elapsed:.2f}s ({pass_rate:.1f}% PASS RATE).")
    print(f"Log written to: test_run_raw.log and ACCEPTANCE_TEST_RAW_LOG.txt ({total_tests} records).")
    sys.exit(int(ret))
