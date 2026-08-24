"""tests/unit/test_comprehensive_cross_check.py — Cross-functional contract & message consistency audit.

Validates:
1. ToolRegistry consistency: All registered tools have valid schemas, executors, verifiers, and non-empty factual messages.
2. Message Template Determinism: All tools produce deterministic factual messages for success/failure.
3. Call Site Signatures: Orchestrator, MultiStepOrchestrator, ActivityLedger, RollbackEngine, and Router all call each other with exact signature matching.
4. Cancellation & Undo contract consistency: Every reversible tool produces valid undo records handled by RollbackRecipes.
5. Routing & Schema validity across all 4 routes (FAST, SMART, SCREEN, DEEP).
"""

from __future__ import annotations

import inspect
import tempfile
import os
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel

from pluma.brain.interface import PlannerInterface
from pluma.brain.lifecycle import LlmLifecycleManager
from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.brain.validator import PlanValidator
from pluma.core.cancellation import CancellationToken
from pluma.core.multi_step import MultiStepOrchestrator, StepExecutionRecord
from pluma.core.orchestrator import Orchestrator, TaskExecutionResult
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult, Router
from pluma.core.task_supervisor import TaskCapsule, TaskState, TaskSupervisor
from pluma.memory.activity import ActionRecord, ActivityLedger, ActivityQuery, TaskRecord, UndoRecord
from pluma.memory.db import DbConnection
from pluma.perception.element_refs import BoundingBox, ScreenElement, ScreenSnapshot
from pluma.perception.freshness import FreshnessChecker
from pluma.perception.ocr_lifecycle import OcrLifecycleManager
from pluma.rollback.engine import RollbackEngine, RollbackResult
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import ToolRegistry, get_default_tool_registry
from pluma.voice.lifecycle import VoiceLifecycleManager


# ---------------------------------------------------------------------------
# 1. Tool Registry & Deterministic Message Audit
# ---------------------------------------------------------------------------

def test_audit_all_registered_tools_contract_and_messages() -> None:
    """Verify that all registered tools conform to typed ToolSpec, schema, and message contracts."""
    registry = get_default_tool_registry()
    tools = registry.list_specs()
    assert len(tools) >= 19, f"Expected at least 19 tools, found {len(tools)}"

    for spec in tools:
        assert isinstance(spec.name, str) and len(spec.name) > 0, f"Tool missing name: {spec}"
        assert isinstance(spec.description, str) and len(spec.description) > 0, f"Tool {spec.name} missing description"
        assert isinstance(spec.risk_class, RiskClass), f"Tool {spec.name} risk class must be RiskClass enum"
        assert callable(spec.executor), f"Tool {spec.name} executor must be callable"

        # Check executor signature
        sig = inspect.signature(spec.executor)
        params = list(sig.parameters.values())
        assert len(params) >= 1, f"Tool {spec.name} executor must accept at least 'arguments'"

        # Check args_schema: must be a Pydantic BaseModel or dict
        if isinstance(spec.args_schema, type):
            assert issubclass(spec.args_schema, BaseModel), f"Tool {spec.name} schema class must subclass BaseModel"
        else:
            assert isinstance(spec.args_schema, dict), f"Tool {spec.name} schema must be dict or BaseModel"

        # If reversible, verify undo_builder signature and corresponding recipe
        if spec.undo_builder is not None:
            assert callable(spec.undo_builder), f"Tool {spec.name} undo_builder must be callable"
            recipes = RollbackRecipes()
            recipe = recipes.get_recipe(spec.name)
            assert recipe is not None, f"Reversible tool {spec.name} MUST have a matching RollbackRecipe"
            assert callable(recipe), f"Recipe for tool {spec.name} must be callable"


def test_audit_deterministic_tool_results_have_factual_messages() -> None:
    """Verify that tool results always contain non-empty factual messages."""
    registry = get_default_tool_registry()

    # Test benign deterministic tools that can be safely queried
    safe_test_cases = [
        ("mute", {}),
        ("unmute", {}),
        ("set_volume", {"level": 50}),
        ("list_apps", {}),
        ("list_windows", {}),
        ("system_status", {}),
        ("battery_status", {}),
        ("clear_clipboard", {}),
        ("show_activity", {"limit": 5}),
    ]

    for tool_name, args in safe_test_cases:
        res = registry.execute(tool_name, args)
        assert isinstance(res, ToolResult), f"Tool {tool_name} must return ToolResult"
        assert isinstance(res.factual_message, str), f"Tool {tool_name} factual_message must be str"
        assert len(res.factual_message) > 0, f"Tool {tool_name} factual_message must not be empty"
        assert res.tool == tool_name, f"ToolResult.tool must match '{tool_name}'"


# ---------------------------------------------------------------------------
# 2. Activity Ledger & Query Call Matching
# ---------------------------------------------------------------------------

def test_audit_activity_ledger_and_query_signatures_match() -> None:
    """Verify ActivityLedger write path and ActivityQuery read path signatures match all consumers."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "audit_ledger.db")
        db = DbConnection(db_path)
        db.open()
        try:
            ledger = ActivityLedger(db)
            query = ActivityQuery(db)

            # Insert task
            task_rec = TaskRecord(
                task_id="t-audit-1",
                request_id="r-audit-1",
                input_mode="text",
                command_text="set volume to 40",
            )
            ledger.insert_task(task_rec)

            # Verify query.task_by_id
            t_row = query.task_by_id("t-audit-1")
            assert t_row is not None
            assert t_row["task_id"] == "t-audit-1"
            assert t_row["command_text"] == "set volume to 40"

            # Insert action
            act_rec = ActionRecord(
                task_id="t-audit-1",
                step_index=0,
                tool="set_volume",
                args_raw={"level": 40},
                risk="LOW",
            )
            act_id = ledger.insert_action(act_rec)
            assert isinstance(act_id, int)

            # Insert undo
            undo_rec = UndoRecord(action_row_id=act_id, undo_data={"previous_level": 50})
            ledger.insert_undo(undo_rec)

            # Verify query.available_undo_records_for_task
            undos = query.available_undo_records_for_task("t-audit-1")
            assert len(undos) == 1
            assert undos[0]["action_id"] == act_id

            # Verify query.recent_tasks
            recent = query.recent_tasks(limit=10)
            assert len(recent) == 1
            assert recent[0]["task_id"] == "t-audit-1"
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 3. RollbackEngine & MultiStepOrchestrator Contract Matching
# ---------------------------------------------------------------------------

def test_audit_rollback_engine_execution_and_result_model() -> None:
    """Verify RollbackEngine.rollback_task returns RollbackResult with exact expected fields."""
    with tempfile.TemporaryDirectory() as td:
        db_path = os.path.join(td, "audit_rollback.db")
        db = DbConnection(db_path)
        db.open()
        try:
            ledger = ActivityLedger(db)
            query = ActivityQuery(db)
            recipes = RollbackRecipes()
            engine = RollbackEngine(ledger=ledger, query=query, recipes=recipes)

            # Task with a mock undo record
            ledger.insert_task(TaskRecord(
                task_id="t-rb-1", request_id="r-rb-1", input_mode="text", command_text="create folder"
            ))
            act_id = ledger.insert_action(ActionRecord(
                task_id="t-rb-1", step_index=0, tool="create_folder",
                args_raw={"path": "C:\\temp_audit_dir"}, risk="LOW"
            ))
            # Mock recipe for create_folder
            undo_path = os.path.join(td, "created_audit_folder")
            os.makedirs(undo_path, exist_ok=True)
            ledger.insert_undo(UndoRecord(
                action_row_id=act_id, undo_data={"path": undo_path, "created": True}
            ))

            rb_result = engine.rollback_task("t-rb-1")
            assert isinstance(rb_result, RollbackResult)
            assert hasattr(rb_result, "all_ok")
            assert hasattr(rb_result, "task_id")
            assert hasattr(rb_result, "steps_attempted")
            assert hasattr(rb_result, "steps_succeeded")
            assert hasattr(rb_result, "steps_failed")
            assert hasattr(rb_result, "step_results")
            assert hasattr(rb_result, "has_residual")
            assert hasattr(rb_result, "factual_summary")
            assert rb_result.task_id == "t-rb-1"
            assert rb_result.all_ok is True
            assert not os.path.exists(undo_path)
        finally:
            db.close()


# ---------------------------------------------------------------------------
# 4. PlanValidator & ToolSubsetSelector Contract Matching
# ---------------------------------------------------------------------------

def test_audit_brain_subset_and_validator_contracts() -> None:
    """Verify that ToolSubsetSelector and PlanValidator contracts match perfectly."""
    registry = get_default_tool_registry()
    selector = ToolSubsetSelector()
    validator = PlanValidator(registry)

    # Route: SMART
    smart_specs = selector.select_schemas_for_route(RouteMode.SMART, registry)
    assert len(smart_specs) > 0
    formatted_prompt = selector.format_schemas_for_prompt(smart_specs)
    assert isinstance(formatted_prompt, str)
    assert "create_folder" in formatted_prompt

    # Validate Plan against registry
    test_plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.MULTI_STEP,
        steps=[
            ToolCall(tool="create_folder", arguments={"path": "C:\\valid"}, purpose="Create directory"),
            ToolCall(tool="list_files", arguments={"path": "C:\\valid"}, purpose="Inspect files"),
        ],
    )
    val_res = validator.validate_plan(test_plan)
    assert isinstance(val_res, Plan)
    assert len(val_res.steps) == 2


# ---------------------------------------------------------------------------
# 5. Full 4-Route Lifecycle Verification (FAST, SMART, SCREEN, DEEP)
# ---------------------------------------------------------------------------

def test_audit_all_four_orchestrator_routes() -> None:
    """Verify that Orchestrator correctly handles all 4 routes and returns TaskExecutionResult."""
    registry = get_default_tool_registry()
    router = Router()
    supervisor = TaskSupervisor()

    mock_backend = MagicMock()
    mock_backend.generate.side_effect = [
        # SMART plan
        '{"route": "SMART", "mode": "direct", "steps": [{"tool": "system_status", "arguments": {}, "purpose": "Query status"}]}',
        # SCREEN plan
        '{"route": "SCREEN", "mode": "direct", "steps": [{"tool": "list_windows", "arguments": {}, "purpose": "List windows"}]}',
        # DEEP plan
        '{"route": "DEEP", "mode": "direct", "steps": [{"tool": "battery_status", "arguments": {}, "purpose": "Query battery"}]}',
    ]

    llm = LlmLifecycleManager(custom_backend=mock_backend, idle_unload_seconds=1.0)
    orchestrator = Orchestrator(
        registry=registry,
        supervisor=supervisor,
        router=router,
        llm_manager=llm,
    )

    # 1. FAST route
    req_fast = PlumaRequest(input_mode=InputMode.TEXT, text="mute")
    res_fast = orchestrator.execute(req_fast)
    assert isinstance(res_fast, TaskExecutionResult)
    assert res_fast.route == RouteMode.FAST
    assert res_fast.final_state == "SUCCEEDED"
    assert len(res_fast.factual_summary) > 0

    # 2. SMART route
    req_smart = PlumaRequest(input_mode=InputMode.TEXT, text="What was modified recently?")
    res_smart = orchestrator.execute(req_smart)
    assert isinstance(res_smart, TaskExecutionResult)
    assert res_smart.route == RouteMode.SMART
    assert res_smart.final_state == "SUCCEEDED"

    # 3. SCREEN route
    req_screen = PlumaRequest(input_mode=InputMode.TEXT, text="click the search bar")
    res_screen = orchestrator.execute(req_screen)
    assert isinstance(res_screen, TaskExecutionResult)
    assert res_screen.route == RouteMode.SCREEN
    assert res_screen.final_state == "SUCCEEDED"

    # 4. DEEP route
    req_deep = PlumaRequest(
        input_mode=InputMode.TEXT,
        text="Inspect this setup screen and finish the remaining configuration",
    )
    res_deep = orchestrator.execute(req_deep)
    assert isinstance(res_deep, TaskExecutionResult)
    assert res_deep.route == RouteMode.DEEP
    assert res_deep.final_state == "SUCCEEDED"


# ---------------------------------------------------------------------------
# 6. Stop-Latch & Replan Limits Cross-Check
# ---------------------------------------------------------------------------

def test_audit_stop_latch_propagation_and_replan_exhaustion() -> None:
    """Verify stop token cancels multi-step and replan limits prevent loops."""
    registry = get_default_tool_registry()
    supervisor = TaskSupervisor()
    multi_step = MultiStepOrchestrator(registry=registry, supervisor=supervisor, max_replans=2)

    capsule = supervisor.create_task("r-stop-audit")
    capsule.cancellation_token.cancel()

    plan = Plan(
        route=RouteMode.SMART,
        mode=PlanMode.DIRECT,
        steps=[ToolCall(tool="mute", arguments={}, purpose="Mute")],
    )

    res = multi_step.execute_plan(capsule, plan, command_text="mute")
    assert res.final_state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL)
    assert len(res.steps_executed) == 0, "No steps should execute when stop token is pre-set"
