"""tests.unit.test_schemas — Contract and schema tests (PLUMA_ACCEPTANCE_TESTS A-01 to A-07).

These tests prove Phase 0 gate requirements:
  A-01: Config loads without starting ML workers.
  A-02: Invalid tool name → rejected before executor.
  A-03: Invalid arguments → schema validation fails before policy/execution.
  A-04: Unknown target reference → rejected.
  A-05: Excessive plan → rejected.
  A-06: Malformed planner output → no fabricated fallback success.
  A-07: Factual message is structurally enforced (not LLM text).

Additional: PlumaRequest, CancellationToken, TaskCapsule, TaskSupervisor contracts.
"""

from __future__ import annotations

import sys
import pytest
from datetime import datetime, timezone, timedelta
from typing import Any

from pydantic import BaseModel, ValidationError


# ---------------------------------------------------------------------------
# A-01: No ML runtime imported after loading contracts
# ---------------------------------------------------------------------------

class TestNoMlAtImport:
    """Confirm that importing PLUMA contracts does not load any ML runtime."""

    def test_import_pluma_no_ml_modules(self) -> None:
        """A-01: Importing pluma and loading config must not trigger ML imports."""
        # These modules are already imported by the time this test runs.
        # We check that the heavy runtimes remain absent.
        ML_MODULES = {
            "whisper", "whisper_cpp", "llama_cpp", "llama", "paddle",
            "paddleocr", "onnxruntime", "torch", "tensorflow",
            "transformers", "sounddevice",
        }
        loaded = {m for m in ML_MODULES if m in sys.modules}
        assert loaded == set(), (
            f"ML runtimes were imported at startup: {loaded!r}. "
            "These must never be loaded merely because PLUMA is imported."
        )

    def test_load_config_no_ml_modules(self) -> None:
        """A-01: load_config() must not trigger ML imports."""
        from pluma.config.loader import load_config
        config = load_config()
        assert isinstance(config, dict)
        ML_MODULES = {
            "whisper", "whisper_cpp", "llama_cpp", "llama", "paddle",
            "paddleocr", "onnxruntime", "torch", "tensorflow",
            "transformers", "sounddevice",
        }
        loaded = {m for m in ML_MODULES if m in sys.modules}
        assert loaded == set(), f"load_config() triggered ML imports: {loaded!r}"

    def test_config_has_required_keys(self) -> None:
        """A-01: Loaded config must contain the required Appendix A sections."""
        from pluma.config.loader import load_config
        config = load_config()
        required_sections = {"agent", "runtime", "voice", "perception", "brain",
                              "policy", "stop", "memory", "ui"}
        missing = required_sections - set(config.keys())
        assert missing == set(), f"Config missing sections: {missing!r}"

    def test_config_agent_defaults(self) -> None:
        """A-01: Key agent defaults must match spec Appendix A."""
        from pluma.config.loader import load_config, get
        config = load_config()
        assert get(config, "agent", "max_plan_steps") == 8
        assert get(config, "agent", "fast_path_enabled") is True
        assert get(config, "agent", "continuous_screen_polling") is False
        assert get(config, "voice", "required") is True
        assert get(config, "voice", "save_audio") is False
        assert get(config, "perception", "uia_first") is True
        assert get(config, "perception", "persist_screenshots") is False
        assert get(config, "memory", "deterministic_activity_text") is True
        assert get(config, "stop", "touch_preexisting_user_apps") is False


# ---------------------------------------------------------------------------
# A-02: Unknown tool name → UnknownToolError before execution
# ---------------------------------------------------------------------------

class TestUnknownToolRejection:
    """A-02: Plans referencing unregistered tools are rejected."""

    def test_lookup_unknown_raises(self) -> None:
        from pluma.tools.registry import ToolRegistry, UnknownToolError
        registry = ToolRegistry()
        with pytest.raises(UnknownToolError):
            registry.lookup("definitely_not_registered")

    def test_validate_call_unknown_raises(self) -> None:
        from pluma.tools.registry import ToolRegistry, UnknownToolError
        registry = ToolRegistry()
        with pytest.raises(UnknownToolError):
            registry.validate_call("not_a_tool", {"arg": "val"})

    def test_contains_returns_false_for_unknown(self) -> None:
        from pluma.tools.registry import ToolRegistry
        registry = ToolRegistry()
        assert not registry.contains("ghost_tool")

    def test_plan_with_invalid_tool_name_format(self) -> None:
        """A-02: Tool name must match snake_case pattern."""
        from pluma.brain.schemas import ToolCall
        with pytest.raises(ValidationError):
            ToolCall(tool="Not-Valid-Name", arguments={}, purpose="test")

    def test_plan_with_empty_tool_name(self) -> None:
        from pluma.brain.schemas import ToolCall
        with pytest.raises(ValidationError):
            ToolCall(tool="", arguments={}, purpose="test")


# ---------------------------------------------------------------------------
# A-03: Invalid arguments → ToolArgumentError before execution
# ---------------------------------------------------------------------------

class TestArgumentValidation:
    """A-03: Argument validation runs before policy or execution."""

    def _make_registry_with_tool(self):
        """Helper: register a simple volume tool with a Pydantic args schema."""
        from pluma.tools.registry import ToolRegistry
        from pluma.tools.base import ToolSpec, RiskClass, ToolResult, VerifyResult

        class VolumeArgs(BaseModel):
            level: int

        def fake_executor(level: int) -> ToolResult:  # pragma: no cover
            return ToolResult(ok=True, tool="set_volume", factual_message="Volume set.")

        def fake_verifier(result: ToolResult) -> VerifyResult:  # pragma: no cover
            return VerifyResult(ok=True, method="api", detail="OK.")

        spec = ToolSpec(
            name="set_volume",
            description="Set the system audio volume.",
            args_schema=VolumeArgs,
            risk_class=RiskClass.LOW,
            timeout_s=5.0,
            executor=fake_executor,
            verifier=fake_verifier,
        )
        registry = ToolRegistry()
        registry.register(spec)
        return registry

    def test_valid_args_pass(self) -> None:
        registry = self._make_registry_with_tool()
        # Should not raise
        registry.validate_call("set_volume", {"level": 30})

    def test_wrong_type_raises(self) -> None:
        from pluma.tools.registry import ToolArgumentError
        registry = self._make_registry_with_tool()
        with pytest.raises(ToolArgumentError):
            registry.validate_call("set_volume", {"level": "banana"})

    def test_missing_required_field_raises(self) -> None:
        from pluma.tools.registry import ToolArgumentError
        registry = self._make_registry_with_tool()
        with pytest.raises(ToolArgumentError):
            registry.validate_call("set_volume", {})


# ---------------------------------------------------------------------------
# A-04: Unknown / stale target reference → rejected
# ---------------------------------------------------------------------------

class TestTargetRefValidation:
    """A-04: Plans with stale or unknown target_ref are rejected."""

    def test_expired_snapshot_raises(self) -> None:
        from pluma.perception.element_refs import (
            ScreenSnapshot, BoundingBox, SnapshotFreshness, StaleSnapshotError
        )
        expired = ScreenSnapshot(
            created_at=datetime.now(timezone.utc) - timedelta(seconds=60),
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=57),
            active_process="notepad.exe",
            active_window_title="Untitled - Notepad",
            window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
            dpi_scale=1.0,
        )
        assert expired.is_expired
        with pytest.raises(StaleSnapshotError):
            SnapshotFreshness.assert_fresh(expired)

    def test_fresh_snapshot_passes(self) -> None:
        from pluma.perception.element_refs import ScreenSnapshot, BoundingBox, SnapshotFreshness
        fresh = ScreenSnapshot(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=3),
            active_process="notepad.exe",
            active_window_title="Untitled - Notepad",
            window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
            dpi_scale=1.0,
        )
        assert not fresh.is_expired
        SnapshotFreshness.assert_fresh(fresh)  # Must not raise.

    def test_window_mismatch_detected(self) -> None:
        from pluma.perception.element_refs import ScreenSnapshot, BoundingBox, SnapshotFreshness
        snapshot = ScreenSnapshot(
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=3),
            active_process="notepad.exe",
            active_window_title="Untitled - Notepad",
            window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
            dpi_scale=1.0,
        )
        # Window has changed — a different process is now active.
        assert not SnapshotFreshness.window_matches(snapshot, "chrome.exe", "Google - Chrome")


# ---------------------------------------------------------------------------
# A-05: Excessive plan → rejected
# ---------------------------------------------------------------------------

class TestPlanStepLimit:
    """A-05: Plans exceeding the configured maximum are rejected."""

    def _make_tool_call(self, index: int):
        from pluma.brain.schemas import ToolCall
        return ToolCall(tool=f"tool_{index:02d}", arguments={}, purpose=f"step {index}")

    def test_plan_within_limit_accepted(self) -> None:
        from pluma.brain.schemas import Plan, PlanMode
        steps = [self._make_tool_call(i) for i in range(3)]
        plan = Plan(task_id="test-task-1", mode=PlanMode.MULTI_STEP, steps=steps)
        assert len(plan.steps) == 3

    def test_plan_over_hard_cap_rejected(self) -> None:
        from pluma.brain.schemas import Plan, PlanMode, MAX_PLAN_STEPS_HARD_CAP
        steps = [self._make_tool_call(i) for i in range(MAX_PLAN_STEPS_HARD_CAP + 1)]
        with pytest.raises(ValidationError, match="hard cap"):
            Plan(task_id="test-task-2", mode=PlanMode.MULTI_STEP, steps=steps)

    def test_direct_plan_with_two_steps_rejected(self) -> None:
        """A DIRECT plan must have exactly one step."""
        from pluma.brain.schemas import Plan, PlanMode
        steps = [self._make_tool_call(0), self._make_tool_call(1)]
        with pytest.raises(ValidationError, match="exactly 1 step"):
            Plan(task_id="test-task-3", mode=PlanMode.DIRECT, steps=steps)


# ---------------------------------------------------------------------------
# A-06: Malformed planner output → ValidationError, no fabricated success
# ---------------------------------------------------------------------------

class TestMalformedPlannerOutput:
    """A-06: Invalid/extra fields from the planner are rejected immediately."""

    def test_extra_field_in_tool_call_rejected(self) -> None:
        from pluma.brain.schemas import ToolCall
        with pytest.raises(ValidationError, match="unexpected fields"):
            ToolCall(
                tool="set_volume",
                arguments={"level": 30},
                purpose="set volume",
                injected_extra="bypass policy",  # type: ignore[call-arg]
            )

    def test_missing_purpose_rejected(self) -> None:
        from pluma.brain.schemas import ToolCall
        with pytest.raises(ValidationError):
            ToolCall(tool="set_volume", arguments={"level": 30})  # missing purpose

    def test_missing_tool_field_rejected(self) -> None:
        from pluma.brain.schemas import ToolCall
        with pytest.raises(ValidationError):
            ToolCall(arguments={"level": 30}, purpose="set volume")  # type: ignore[call-arg]

    def test_empty_plan_steps_rejected(self) -> None:
        from pluma.brain.schemas import Plan, PlanMode
        with pytest.raises(ValidationError):
            Plan(task_id="t", mode=PlanMode.MULTI_STEP, steps=[])


# ---------------------------------------------------------------------------
# A-07: ToolResult.factual_message is structurally required
# ---------------------------------------------------------------------------

class TestFactualMessage:
    """A-07: factual_message is a required field — not optional LLM text."""

    def test_tool_result_requires_factual_message(self) -> None:
        from pluma.tools.base import ToolResult
        with pytest.raises(ValidationError):
            ToolResult(ok=True, tool="set_volume")  # missing factual_message  # type: ignore[call-arg]

    def test_tool_result_failure_convenience(self) -> None:
        from pluma.tools.base import ToolResult
        result = ToolResult.failure("set_volume", "Device not found")
        assert not result.ok
        assert result.error == "Device not found"
        assert "Failed:" in result.factual_message
        assert result.verified is False

    def test_tool_result_ok_with_message(self) -> None:
        from pluma.tools.base import ToolResult
        result = ToolResult(
            ok=True,
            tool="set_volume",
            factual_message="Volume set to 30%.",
            verified=True,
        )
        assert result.ok
        assert result.verified


# ---------------------------------------------------------------------------
# CancellationToken tests
# ---------------------------------------------------------------------------

class TestCancellationToken:
    """Verify atomic latch semantics."""

    def test_initially_not_cancelled(self) -> None:
        from pluma.core.cancellation import CancellationToken
        token = CancellationToken()
        assert not token.is_cancelled

    def test_cancel_sets_latch(self) -> None:
        from pluma.core.cancellation import CancellationToken, StopReason
        token = CancellationToken()
        result = token.cancel(StopReason.USER_STOP)
        assert result is True
        assert token.is_cancelled
        assert token.reason == StopReason.USER_STOP

    def test_cancel_is_one_way(self) -> None:
        """Second cancel() call returns False — first caller wins."""
        from pluma.core.cancellation import CancellationToken, StopReason
        token = CancellationToken()
        r1 = token.cancel(StopReason.USER_STOP)
        r2 = token.cancel(StopReason.INTERNAL_ERROR)
        assert r1 is True
        assert r2 is False
        assert token.reason == StopReason.USER_STOP  # First reason preserved.

    def test_raise_if_cancelled(self) -> None:
        from pluma.core.cancellation import CancellationToken, StopReason, TaskCancelledError
        token = CancellationToken()
        token.cancel(StopReason.USER_STOP)
        with pytest.raises(TaskCancelledError):
            token.raise_if_cancelled()

    def test_raise_if_not_cancelled_does_nothing(self) -> None:
        from pluma.core.cancellation import CancellationToken
        token = CancellationToken()
        token.raise_if_cancelled()  # Must not raise.


# ---------------------------------------------------------------------------
# TaskCapsule and TaskSupervisor tests
# ---------------------------------------------------------------------------

class TestTaskStateMachine:
    def test_created_to_running(self) -> None:
        from pluma.core.task_supervisor import TaskSupervisor, TaskState
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task(request_id="r1")
        assert capsule.state == TaskState.CREATED
        supervisor.start_task(capsule.task_id)
        assert capsule.state == TaskState.RUNNING
        assert capsule.started_at is not None

    def test_invalid_transition_raises(self) -> None:
        from pluma.core.task_supervisor import TaskSupervisor, TaskState, InvalidTaskTransition
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task(request_id="r2")
        with pytest.raises(InvalidTaskTransition):
            supervisor._transition(capsule, TaskState.SUCCEEDED)

    def test_terminal_state_is_final(self) -> None:
        from pluma.core.task_supervisor import TaskSupervisor, TaskState, InvalidTaskTransition
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task(request_id="r3")
        supervisor.start_task(capsule.task_id)
        supervisor.mark_succeeded(capsule.task_id)
        
        with pytest.raises(InvalidTaskTransition):
            supervisor._transition(capsule, TaskState.RUNNING)

    def test_stop_sets_latch_first(self) -> None:
        from pluma.core.task_supervisor import TaskSupervisor, TaskState
        supervisor = TaskSupervisor()
        capsule = supervisor.create_task(request_id="r4")
        supervisor.start_task(capsule.task_id)
        supervisor.stop_task(capsule.task_id)
        assert capsule.cancellation_token.is_cancelled
        # State should be STOPPED immediately after synchronous cleanup in our implementation
        assert capsule.state == TaskState.STOPPED

    def test_resource_ownership_separation(self) -> None:
        from pluma.core.task_supervisor import TaskSupervisor, ResourceOwnership
        from pluma.core.ownership import OwnershipRegistry
        registry = OwnershipRegistry()
        supervisor = TaskSupervisor(ownership_registry=registry)
        capsule = supervisor.create_task(request_id="r5")
        
        registry.register_resource(capsule.task_id, "temp_dir", ResourceOwnership.PLUMA_CREATED, "/tmp/a")
        registry.register_resource(capsule.task_id, "file", ResourceOwnership.PREEXISTING, "/etc/passwd")
        
        owned = registry.get_owned_resources(capsule.task_id, ResourceOwnership.PLUMA_CREATED)
        assert len(owned) == 1
        assert owned[0].resource_type == "temp_dir"


# ---------------------------------------------------------------------------
# PlumaRequest tests
# ---------------------------------------------------------------------------

class TestPlumaRequest:
    """Voice and text produce the same request type."""

    def test_text_request(self) -> None:
        from pluma.core.request import PlumaRequest, InputMode
        req = PlumaRequest(input_mode=InputMode.TEXT, text="open notepad")
        assert req.input_mode == InputMode.TEXT
        assert req.original_transcript is None

    def test_voice_request(self) -> None:
        from pluma.core.request import PlumaRequest, InputMode
        req = PlumaRequest(
            input_mode=InputMode.VOICE,
            text="open notepad",
            original_transcript="open note pad",
        )
        assert req.input_mode == InputMode.VOICE
        assert req.original_transcript == "open note pad"

    def test_whitespace_only_text_rejected(self) -> None:
        from pluma.core.request import PlumaRequest, InputMode
        with pytest.raises(ValidationError):
            PlumaRequest(input_mode=InputMode.TEXT, text="   ")

    def test_transcript_on_text_input_rejected(self) -> None:
        from pluma.core.request import PlumaRequest, InputMode
        with pytest.raises(ValidationError):
            PlumaRequest(
                input_mode=InputMode.TEXT,
                text="open notepad",
                original_transcript="should not be here",
            )
