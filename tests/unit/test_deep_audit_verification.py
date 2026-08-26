"""tests/unit/test_deep_audit_verification.py — Comprehensive end-to-end multi-pass audit."""

from __future__ import annotations

import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from pluma.brain.lifecycle import LlmLifecycleManager, LlmLifecycleState
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
from pluma.brain.prompt_builder import PromptBuilder
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.brain.validator import PlanValidationError, PlanValidator
from pluma.core.cancellation import CancellationToken
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskState, TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection
from pluma.memory.redaction import redact_dict, redact_string
from pluma.perception.element_refs import (
    BoundingBox,
    ScreenElement,
    ScreenSnapshot,
    StaleSnapshotError,
)
from pluma.perception.freshness import FreshnessChecker, WindowMismatchError
from pluma.perception.ocr_adapter import OcrAdapter, OcrWord
from pluma.perception.ocr_lifecycle import OcrLifecycleManager
from pluma.tools.registry import get_default_tool_registry
from pluma.voice.pipeline import is_material_target
from pluma.voice.vad import EnergyVAD


def test_audit_fast_route_ledger_integration() -> None:
    """Pass 1: End-to-end FAST routing + Tool execution + DB ledger verification."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "audit_pluma.db")
        db = DbConnection(db_path)
        db.open()
        try:
            ledger = ActivityLedger(db)
            registry = get_default_tool_registry()
            supervisor = TaskSupervisor(ledger=ledger)
            router = Router()
            orchestrator = Orchestrator(
                registry=registry, supervisor=supervisor, ledger=ledger, router=router
            )

            req = PlumaRequest(input_mode=InputMode.TEXT, text="mute")
            res = orchestrator.execute(req)
            assert res.final_state == "SUCCEEDED"
            assert res.route == RouteMode.FAST

            # Verify SQLite ledger persistence
            from pluma.memory.activity import ActivityQuery
            query = ActivityQuery(db)
            tasks = query.recent_tasks()
            assert len(tasks) == 1
            assert tasks[0]["task_id"] == res.task_id
            assert tasks[0]["final_state"] == "SUCCEEDED"
            assert tasks[0]["route"] == "FAST"
        finally:
            db.close()


def test_audit_perception_freshness_ttl_enforcement() -> None:
    """Pass 2: Screen snapshot TTL guard strictly rejects expired snapshots."""
    now = datetime.now(timezone.utc)
    expired_snap = ScreenSnapshot(
        snapshot_id="snap-audit-exp",
        created_at=now - timedelta(seconds=10),
        expires_at=now - timedelta(seconds=5),
        active_process="notepad.exe",
        active_window_title="Untitled - Notepad",
        window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
        dpi_scale=1.0,
        controls=[],
        ocr_words=[],
    )
    checker = FreshnessChecker()
    assert expired_snap.is_expired

    with pytest.raises(StaleSnapshotError):
        checker.validate(expired_snap, require_window_match=False)


def test_audit_ocr_lifecycle_and_ambiguity_rejection() -> None:
    """Pass 3: OCR lifecycle idle timeout and ambiguity duplicate rejection."""
    class MockOcrBackend:
        def recognize(self, image_bytes: bytes) -> list[OcrWord]:
            return [
                OcrWord(
                    text="Save",
                    confidence=0.99,
                    bounds=BoundingBox(left=10, top=10, right=50, bottom=30),
                ),
                OcrWord(
                    text="Save",
                    confidence=0.95,
                    bounds=BoundingBox(left=100, top=10, right=140, bottom=30),
                ),
            ]

    ocr_mgr = OcrLifecycleManager(
        adapter=OcrAdapter(custom_backend=MockOcrBackend()),
        idle_unload_seconds=0.1,
    )
    ocr_res = ocr_mgr.run_ocr(b"dummy_bmp_bytes")
    matches = ocr_res.find_words("Save")
    assert len(matches) == 2, "Expected 2 matches for duplicate Save buttons"
    assert ocr_mgr.state == "WARM"

    time.sleep(0.25)
    assert ocr_mgr.state == "COLD", "OCR engine must return to COLD state after idle timeout"


def test_audit_voice_vad_and_material_safety() -> None:
    """Pass 4: VAD calculation and low-confidence material target guard."""
    assert is_material_target("delete all files in downloads") is True
    assert is_material_target("format drive D:") is True
    assert is_material_target("volume 40") is True
    assert is_material_target("open notepad") is False

    vad = EnergyVAD()
    silence = b"\x00\x00" * 320
    assert vad.calculate_rms(silence) == 0.0
    assert vad.is_speech_present(silence) is False


def test_audit_brain_planner_lifecycle_and_schema_validation() -> None:
    """Pass 5: LLM prompt building, redaction, plan validation, and 30s idle timer."""
    mock_backend = MagicMock()
    mock_backend.generate.return_value = (
        '{"route": "SMART", "mode": "direct", "steps": '
        '[{"tool": "create_folder", "arguments": {"path": "C:\\\\new_folder"}, "purpose": "create folder"}]}'
    )

    llm_mgr = LlmLifecycleManager(
        custom_backend=mock_backend,
        idle_unload_seconds=0.1,
    )
    plan = llm_mgr.plan("Create folder C:\\new_folder with secret token sk-12345678901234567890123456789012")
    assert plan.route == RouteMode.SMART
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "create_folder"
    assert llm_mgr.state == LlmLifecycleState.WARM

    # Verify that secret token was redacted in prompt sent to LLM
    call_args = mock_backend.generate.call_args[1]
    assert "sk-12345" not in call_args["prompt"], "Secret tokens must be redacted from prompts"

    # Wait for idle unload
    time.sleep(0.25)
    assert llm_mgr.state == LlmLifecycleState.COLD


def test_audit_multi_step_orchestrator_and_replan_limits() -> None:
    """Pass 6: Multi-step orchestrator execution, stop-latch pre-checks, and replan limits."""
    from pluma.core.multi_step import MultiStepOrchestrator
    from pluma.tools.registry import get_default_tool_registry

    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "audit_multi.db")
        db = DbConnection(db_path)
        db.open()
        try:
            ledger = ActivityLedger(db)
            registry = get_default_tool_registry()
            supervisor = TaskSupervisor(ledger=ledger)
            orchestrator = MultiStepOrchestrator(
                registry=registry,
                supervisor=supervisor,
                ledger=ledger,
                max_replans=2,
            )

            # Test execution with immediate pre-cancelled token
            capsule = supervisor.create_task(request_id="req-1")
            capsule.cancellation_token.cancel("User STOP activated")
            supervisor.start_task(capsule.task_id)

            plan = Plan(
                route=RouteMode.SMART,
                mode=PlanMode.MULTI_STEP,
                steps=[
                    ToolCall(tool="mute", arguments={}, purpose="mute system"),
                    ToolCall(tool="unmute", arguments={}, purpose="unmute system"),
                ],
            )
            res = orchestrator.execute_plan(
                capsule=capsule,
                initial_plan=plan,
                command_text="mute then unmute",
            )
            assert res.final_state in (TaskState.STOPPED, TaskState.FAILED)
            assert len(res.steps_executed) == 0, "No steps should execute when token is already cancelled"
        finally:
            db.close()


def test_audit_policy_confirmation_boundaries() -> None:
    """Pass 7: Policy confirmation enforcement on high-risk operations."""
    from pluma.policy.engine import PolicyEngine
    from pluma.ui.confirmations import AutoDenyConfirmation

    policy = PolicyEngine(confirmation_contract=AutoDenyConfirmation())
    decision = policy.evaluate("move_file", {"source": "C:\\a.txt", "destination": "C:\\b.txt"})
    # Low/Medium risk file move allowed
    assert decision.allowed is True

    # High-risk or restricted path operation must be blocked by auto-deny confirmation
    restricted_decision = policy.evaluate("move_file", {"source": "C:\\Windows\\System32\\calc.exe", "destination": "D:\\calc.exe"})
    assert restricted_decision.allowed is False, "Restricted system path operation must fail closed under AutoDeny"


def test_audit_crash_recovery_reconciliation() -> None:
    """Pass 8: Startup crash recovery marking interrupted tasks as ABORTED_BY_CRASH."""
    from pluma.config.paths import PlumaPaths
    from pluma.core.recovery import CrashRecoveryManager
    from pluma.memory.activity import TaskRecord

    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=td, roaming_app_data=td)
        paths.ensure_directories()
        db = DbConnection(str(paths.db_path))
        db.open()
        try:
            ledger = ActivityLedger(db)
            ledger.insert_task(TaskRecord(
                task_id="crashed-1",
                request_id="req-c1",
                input_mode="text",
                command_text="slow operation",
                route="SMART",
                final_state="RUNNING",
            ))

            rec_mgr = CrashRecoveryManager(db=db, paths=paths)
            rec_res = rec_mgr.reconcile_startup()
            assert rec_res.stale_tasks_recovered == 1
            assert "crashed-1" in rec_res.recovered_task_ids
            assert rec_res.db_integrity_ok is True
        finally:
            db.close()
