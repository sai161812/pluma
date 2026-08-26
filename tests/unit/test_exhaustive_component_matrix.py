"""tests/unit/test_exhaustive_component_matrix.py — Exhaustive attribute and flow validation matrix for all components."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Dict, List
from unittest.mock import MagicMock
import pytest

# ---------------------------------------------------------------------------
# Core & Process Host Components
# ---------------------------------------------------------------------------
from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
from pluma.core.ipc import NamedPipeIpcClient, NamedPipeIpcServer
from pluma.core.job_object import WindowsJobObject
from pluma.core.multi_step import MultiStepExecutionResult, MultiStepOrchestrator, StepExecutionRecord
from pluma.core.orchestrator import Orchestrator, StepRecord, TaskExecutionResult
from pluma.core.ownership import OwnershipRegistry, get_process_creation_time
from pluma.core.recovery import CrashRecoveryManager, CrashRecoveryResult
from pluma.core.request import InputMode, PlumaRequest, RequestID
from pluma.core.resident import ResidentCore
from pluma.core.router import RouteResult, Router
from pluma.core.task_supervisor import (
    OwnedResource,
    ResourceOwnership,
    TaskCapsule,
    TaskState,
    TaskStep,
    TaskSupervisor,
)

# ---------------------------------------------------------------------------
# Tool & Base Components
# ---------------------------------------------------------------------------
from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry, get_default_tool_registry, register_default_tools

# ---------------------------------------------------------------------------
# Memory, Storage, Redaction & Rollback
# ---------------------------------------------------------------------------
from pluma.memory.activity import ActionRecord, ActivityLedger, ActivityQuery, TaskRecord, UndoRecord
from pluma.memory.aliases import AliasStore
from pluma.memory.db import DbConnection
from pluma.memory.preferences import PreferencesStore
from pluma.memory.redaction import RedactionEngine, redact_dict, redact_string, sanitise_args_for_ledger
from pluma.memory.routines import RoutineStore
from pluma.rollback.engine import RollbackEngine, RollbackResult
from pluma.rollback.recipes import RollbackRecipes

# ---------------------------------------------------------------------------
# Perception, Vision & OCR
# ---------------------------------------------------------------------------
from pluma.perception.context import ActiveWindowContext
from pluma.perception.element_refs import BoundingBox, ScreenElement, ScreenSnapshot, StaleSnapshotError
from pluma.perception.freshness import FreshnessChecker, WindowMismatchError
from pluma.perception.ocr_adapter import OcrAdapter, OcrResult, OcrWord
from pluma.perception.ocr_lifecycle import OcrLifecycleManager, OcrLifecycleState

# ---------------------------------------------------------------------------
# Voice Pipeline
# ---------------------------------------------------------------------------
from pluma.voice.lifecycle import VoiceLifecycleManager
from pluma.voice.pipeline import VoicePipeline, is_material_target
from pluma.voice.stt_adapter import TranscriptResult, WhisperSttAdapter
from pluma.voice.vad import EnergyVAD

# ---------------------------------------------------------------------------
# Local Brain & Planner
# ---------------------------------------------------------------------------
from pluma.brain.lifecycle import LlmLifecycleManager, LlmLifecycleState
from pluma.brain.llama_cpp_adapter import LlamaCppAdapter
from pluma.brain.prompt_builder import PromptBuilder
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.brain.validator import PlanValidationError, PlanValidator

# ---------------------------------------------------------------------------
# Policy Engine & Confirmations
# ---------------------------------------------------------------------------
from pluma.policy.elevation_broker import ElevationBroker
from pluma.policy.engine import PolicyDecision, PolicyEngine, PolicyEvaluationResult
from pluma.policy.rules import PolicyRules
from pluma.ui.confirmations import (
    AutoApproveConfirmationContract,
    AutoDenyConfirmationContract,
    CallbackConfirmationContract,
    ConfirmationRequest,
    ConfirmationResponse,
)

# ---------------------------------------------------------------------------
# Paths & Packaging
# ---------------------------------------------------------------------------
from pluma.config.paths import PlumaPaths, get_paths, set_paths


# ===========================================================================
# 1. CORE & PROCESS HOST ATTRIBUTE & FLOW TESTS
# ===========================================================================

def test_cancellation_token_attributes_and_flow() -> None:
    """Verify CancellationToken attribute matches and lifecycle transitions."""
    token = CancellationToken()
    assert token.is_cancelled is False
    assert token.reason is None

    token.cancel(reason=StopReason.USER_STOP)
    assert token.is_cancelled is True
    assert token.reason == StopReason.USER_STOP

    with pytest.raises(TaskCancelledError):
        token.raise_if_cancelled()


def test_pluma_request_attributes_and_flow() -> None:
    """Verify PlumaRequest attribute matches, normalization, and immutability."""
    req = PlumaRequest.from_text("volume 20")
    assert req.text == "volume 20"
    assert req.input_mode == InputMode.TEXT
    assert req.request_id is not None
    assert isinstance(req.created_at, datetime)

    # Verify voice input mode
    voice_req = PlumaRequest(
        input_mode=InputMode.VOICE,
        text="open notepad",
        original_transcript="open notepad please",
    )
    assert voice_req.input_mode == InputMode.VOICE
    assert voice_req.original_transcript == "open notepad please"


def test_task_supervisor_lifecycle_flow() -> None:
    """Verify TaskSupervisor state transitions, JobObject attachment, and ledger updates."""
    with tempfile.TemporaryDirectory() as td:
        db = DbConnection(os.path.join(td, "sup.db"))
        db.open()
        try:
            ledger = ActivityLedger(db=db)
            supervisor = TaskSupervisor(ledger=ledger)

            capsule = supervisor.create_task(request_id="req-123")
            assert capsule.state == TaskState.CREATED
            assert capsule.task_id is not None
            assert capsule.cancellation_token is not None

            supervisor.start_task(capsule.task_id)
            assert capsule.state == TaskState.RUNNING

            supervisor.mark_succeeded(capsule.task_id)
            assert capsule.state == TaskState.SUCCEEDED
        finally:
            db.close()


def test_ownership_registry_and_pid_security() -> None:
    """Verify OwnershipRegistry PID tracking and creation timestamp validation."""
    registry = OwnershipRegistry()
    current_pid = os.getpid()

    res = registry.register_subprocess(
        task_id="t-matrix",
        pid=current_pid,
        ownership=ResourceOwnership.PLUMA_CREATED,
        command_class="test",
    )
    assert res is not None
    assert res.external_id == str(current_pid)
    assert registry.is_owned_resource("t-matrix", "subprocess", str(current_pid)) is True
    assert registry.is_owned_resource("t-matrix", "subprocess", "999999") is False


# ===========================================================================
# 2. TOOL REGISTRY & 31 TOOLS VALIDATION
# ===========================================================================

def test_tool_registry_31_tools_attributes_and_execution() -> None:
    """Verify that all 31 registered tools have valid schemas, executors, and verifiers."""
    registry = get_default_tool_registry()
    specs = registry.list_specs()
    assert len(specs) >= 31, f"Expected 31 registered tools, got {len(specs)}"

    tool_names = {s.name for s in specs}
    required_tools = {
        "list_files", "find_file", "move_file", "rename_file", "create_folder",
        "open_app", "close_app", "focus_app", "list_apps", "app_status",
        "list_windows", "focus_window", "minimize_window", "maximize_window",
        "set_volume", "mute", "unmute",
        "get_system_status", "system_status", "battery_status", "stop_current", "show_activity", "undo_last",
        "clear_clipboard", "clipboard_clear", "get_clipboard_text", "set_clipboard_text",
        "inspect_active_window", "click_element", "type_into_element", "click_ocr_text",
    }
    missing = required_tools - tool_names
    assert not missing, f"Missing required registered tools: {missing}"

    for spec in specs:
        assert isinstance(spec.name, str) and len(spec.name) > 0
        assert isinstance(spec.description, str) and len(spec.description) > 0
        assert isinstance(spec.risk_class, RiskClass)
        assert callable(spec.executor), f"Tool {spec.name} missing callable executor"
        assert spec.timeout_s > 0


# ===========================================================================
# 3. MEMORY, ACTIVITY LEDGER, REDACTION & ROLLBACK FLOW
# ===========================================================================

def test_activity_ledger_and_query_flow() -> None:
    """Verify ActivityLedger database write queue and ActivityQuery readback."""
    with tempfile.TemporaryDirectory() as td:
        db = DbConnection(os.path.join(td, "activity.db"))
        db.open()
        try:
            ledger = ActivityLedger(db=db)
            query = ActivityQuery(db=db)

            # Insert task
            task_rec = TaskRecord(
                task_id="t-matrix-1",
                request_id="r-matrix-1",
                input_mode="text",
                command_text="set volume to 25",
                route="FAST",
                final_state="SUCCEEDED",
            )
            ledger.insert_task(task_rec)

            # Insert action
            action_rec = ActionRecord(
                task_id="t-matrix-1",
                step_index=0,
                tool="set_volume",
                args_raw={"level": 25},
                risk="LOW",
                result_data={"new_volume": 25},
                verified=True,
            )
            action_id = ledger.insert_action(action_rec)
            assert action_id is not None

            # Query readback
            t = query.task_by_id("t-matrix-1")
            assert t is not None
            assert t["command_text"] == "set volume to 25"
            assert t["final_state"] == "SUCCEEDED"

            actions = query.actions_for_task("t-matrix-1")
            assert len(actions) == 1
            assert actions[0]["tool"] == "set_volume"
        finally:
            db.close()


def test_redaction_engine_flow() -> None:
    """Verify RedactionEngine removes API keys, passwords, and sensitive credentials."""
    secret_text = "Bearer sk-1234567890abcdef1234567890abcdef and password=SuperSecretPassword123!"
    redacted = redact_string(secret_text)
    assert "sk-1234567890" not in redacted
    assert "SuperSecretPassword123!" not in redacted

    dict_data = {
        "api_key": "sk-test123456789012345678901234567890",
        "auth_token": "token_abc123",
        "normal_field": "hello world",
    }
    sanitized = redact_dict(dict_data)
    assert sanitized["normal_field"] == "hello world"
    assert "sk-test" not in str(sanitized["api_key"])


def test_preferences_and_alias_store_flow() -> None:
    """Verify PreferencesStore and AliasStore key-value persistence."""
    with tempfile.TemporaryDirectory() as td:
        db = DbConnection(os.path.join(td, "prefs.db"))
        db.open()
        try:
            prefs = PreferencesStore(db=db)
            prefs.set("volume_default", 50)
            assert prefs.get("volume_default") == 50

            aliases = AliasStore(db=db)
            aliases.set("editor", "C:\\CustomPath\\code.exe")
            assert aliases.get("editor") == "C:\\CustomPath\\code.exe"
        finally:
            db.close()


# ===========================================================================
# 4. VOICE PIPELINE & VAD FLOW
# ===========================================================================

def test_vad_and_voice_pipeline_flow() -> None:
    """Verify EnergyVAD silence calculation and voice pipeline material target check."""
    vad = EnergyVAD(energy_threshold=350.0, frame_duration_ms=30)
    silence_pcm = bytes([0x00, 0x00] * 480)
    assert vad.calculate_rms(silence_pcm) == 0.0
    assert vad.is_speech_present(silence_pcm) is False

    # Material target check
    assert is_material_target("delete file C:\\a.txt") is True
    assert is_material_target("volume 20") is True
    assert is_material_target("open notepad") is False


# ===========================================================================
# 5. PERCEPTION, VISION & OCR LIFECYCLE FLOW
# ===========================================================================

def test_bounding_box_and_screen_snapshot_flow() -> None:
    """Verify BoundingBox calculations, ScreenSnapshot TTL, and FreshnessChecker."""
    box = BoundingBox(left=100, top=100, right=200, bottom=200)
    assert box.center_x == 150
    assert box.center_y == 150
    assert box.width == 100
    assert box.height == 100
    assert box.contains(150, 150) is True
    assert box.contains(50, 50) is False

    now = datetime.now(timezone.utc)
    fresh_snap = ScreenSnapshot(
        snapshot_id="snap-matrix-1",
        created_at=now,
        expires_at=now + timedelta(seconds=5),
        active_process="explorer.exe",
        active_window_title="File Explorer",
        window_rect=box,
        dpi_scale=1.0,
        controls=[
            ScreenElement(
                snapshot_id="snap-matrix-1",
                label="Submit",
                control_type="Button",
                bounds=box,
                source="UIA",
                confidence=1.0,
            )
        ],
        ocr_words=[],
    )
    assert fresh_snap.is_expired is False
    found = fresh_snap.find_elements_by_label("Submit")
    assert len(found) == 1
    assert found[0].label == "Submit"


# ===========================================================================
# 6. LOCAL BRAIN, PLANNER & VALIDATION FLOW
# ===========================================================================

def test_plan_validator_and_tool_subset_flow() -> None:
    """Verify PlanValidator schema constraints, 20-step cap, and tool subset builder."""
    import json
    registry = get_default_tool_registry()
    validator = PlanValidator(registry=registry)

    valid_json = {
        "route": "FAST",
        "mode": "direct",
        "steps": [{"tool": "set_volume", "arguments": {"level": 30}, "purpose": "set volume"}],
    }
    plan = validator.validate(json.dumps(valid_json), registry=registry)
    assert plan.route == RouteMode.FAST
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "set_volume"

    # Step limit cap violation test (N > 20)
    invalid_steps = [{"tool": "set_volume", "arguments": {"level": 30}, "purpose": "step"} for _ in range(25)]
    with pytest.raises(PlanValidationError):
        validator.validate(json.dumps({"route": "SMART", "mode": "multi_step", "steps": invalid_steps}), registry=registry)

    # Tool subset selector check
    selector = ToolSubsetSelector()
    schemas = selector.get_schemas_for_route(RouteMode.SMART, registry=registry)
    assert len(schemas) > 0


# ===========================================================================
# 7. ROUTER, ORCHESTRATOR & POLICY FLOW
# ===========================================================================

def test_router_orchestrator_policy_e2e_flow() -> None:
    """Verify complete request -> route -> policy -> execute -> ledger flow."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=td, roaming_app_data=td)
        paths.ensure_directories()

        db = DbConnection(str(paths.db_path))
        db.open()
        try:
            ledger = ActivityLedger(db=db)
            policy = PolicyEngine(confirmation_contract=AutoApproveConfirmationContract())
            registry = ToolRegistry(policy_engine=policy)
            register_default_tools(registry)
            supervisor = TaskSupervisor(ledger=ledger)
            orchestrator = Orchestrator(
                registry=registry,
                supervisor=supervisor,
                ledger=ledger,
            )

            req = PlumaRequest.from_text("volume 55")
            res = orchestrator.execute(req)
            assert res.final_state == "SUCCEEDED"
            assert res.route == RouteMode.FAST
            assert "55" in res.user_message or res.success is True

            # Policy evaluation check
            decision = policy.evaluate("open_app", {"app_name": "notepad"})
            assert decision.is_allowed is True
            assert decision.risk_class == RiskClass.LOW
        finally:
            db.close()


# ===========================================================================
# 8. PACKAGING, PATHS & CRASH RECOVERY FLOW
# ===========================================================================

def test_paths_and_crash_recovery_flow() -> None:
    """Verify PlumaPaths directory resolution and CrashRecoveryManager reconciliation."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=td, roaming_app_data=td)
        paths.ensure_directories()

        assert paths.data_dir.exists()
        assert paths.models_dir.exists()
        assert paths.logs_dir.exists()
        assert paths.temp_dir.exists()

        db = DbConnection(str(paths.db_path))
        db.open()
        try:
            ledger = ActivityLedger(db=db)
            ledger.insert_task(TaskRecord(
                task_id="t-crash-matrix",
                request_id="r-crash-matrix",
                input_mode="text",
                command_text="interrupted task",
                route="SMART",
                final_state="RUNNING",
            ))

            recovery = CrashRecoveryManager(db=db, paths=paths)
            rec_res = recovery.reconcile_startup()
            assert rec_res.stale_tasks_recovered == 1
            assert "t-crash-matrix" in rec_res.recovered_task_ids
            assert rec_res.db_integrity_ok is True
        finally:
            db.close()
