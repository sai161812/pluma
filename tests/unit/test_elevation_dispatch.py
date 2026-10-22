"""P11 elevation routing is a closed, durable, one-operation contract."""

import pytest
from pydantic import ValidationError

from pluma.adapters.elevation import DNS_FLUSH_SCRIPT, dns_flush_arguments
from pluma.core import job_object
from pluma.memory.activity import ActivityQuery
from pluma.policy.elevation_broker import ElevationBroker, ElevationOpType, ElevationOperation
from pluma.tools.base import RiskClass, ToolResult
from pluma.tools.system import execute_flush_dns_cache, verify_flush_dns_cache
from tests.unit.test_runtime_shutdown import NATIVE_JOB, runtime, task


def inert_elevation_executor(args, context):
    """Pickleable process-isolated substitute; it never opens UAC or runs a command."""
    assert args == {}
    assert context.execution_binding == {"elevation_operation": "FLUSH_DNS"}
    pending = next(item for item in reversed(context.undo_stack)
        if item.get("action") == "pending_mutation" and item.get("tool") == "flush_dns_cache")
    assert pending["non_undoable"] is True
    assert pending["pre_state"]["operation"] == "FLUSH_DNS"
    return ToolResult.success("flush_dns_cache",
        data={"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True},
        factual_message="Inert one-operation elevation route completed.",
        verified=False, adapter_used="one_operation_uac")


def test_operation_schema_exposes_only_dns_flush():
    operation = ElevationOperation(op_type=ElevationOpType.FLUSH_DNS)
    assert operation.model_dump() == {"op_type": ElevationOpType.FLUSH_DNS}
    with pytest.raises(ValidationError):
        ElevationOperation(op_type=ElevationOpType.FLUSH_DNS, service_name="Spooler")
    assert "Clear-DnsClientCache" in DNS_FLUSH_SCRIPT
    assert "-ExecutionPolicy" not in dns_flush_arguments()
    assert "Bypass" not in " ".join(dns_flush_arguments())


def test_broker_dispatches_only_to_injected_native_runner():
    received = {}

    def runner(**kwargs):
        received.update(kwargs)
        return ToolResult.success("flush_dns_cache",
            data={"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True},
            factual_message="Inert runner receipt.", verified=False, adapter_used="one_operation_uac")

    context = object()
    broker = ElevationBroker(timeout_s=9.0, runner=runner)
    result = broker.execute_operation(ElevationOperation(op_type=ElevationOpType.FLUSH_DNS),
        task_id="p11-owned-fixture", task_context=context, timeout_s=20.0)

    assert result.ok and result.tool == "flush_dns_cache"
    assert received == {"task_id": "p11-owned-fixture", "timeout_s": 9.0, "task_context": context}
    assert verify_flush_dns_cache(result).ok


def test_registered_admin_call_uses_policy_binding_journal_and_owned_worker(runtime, monkeypatch):
    monkeypatch.setattr(job_object, "WindowsJobObject", NATIVE_JOB)
    spec = runtime.tool_registry.lookup("flush_dns_cache")
    monkeypatch.setattr(spec, "executor", inert_elevation_executor)
    cap = task(runtime)

    result = runtime.tool_registry.execute("flush_dns_cache", {}, cap, runtime.ledger)

    assert result.ok and result.verified and result.adapter_used == "one_operation_uac"
    row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
    assert row["risk"] == RiskClass.ADMIN.value
    assert row["approval_state"] == "REQUIRE_ELEVATION"
    assert row["verified"] == 1
    assert row["result_json"]
    assert len(cap.undo_stack) == 1
    commit = cap.undo_stack[0]
    assert commit["action"] == "non_undoable_commit"
    assert commit["non_undoable"] is True
    assert commit["effect_state"] == "committed"


def test_unsupported_admin_tool_fails_closed_before_executor(runtime):
    from pydantic import BaseModel
    from pluma.tools.base import ToolSpec, VerifyResult

    class EmptyArgs(BaseModel):
        model_config = {"extra": "forbid", "strict": True}

    calls = []
    def forbidden_executor(args, context=None):
        calls.append(True)
        return ToolResult.success("unsupported_admin", factual_message="Must not run.")

    runtime.tool_registry.register(ToolSpec(
        name="unsupported_admin", description="Unmapped ADMIN fixture.", args_schema=EmptyArgs,
        risk_class=RiskClass.ADMIN, timeout_s=2, executor=forbidden_executor,
        verifier=lambda result: VerifyResult(ok=True, method="fixture", detail="Must not be called."),
    ))
    cap = task(runtime)
    result = runtime.tool_registry.execute("unsupported_admin", {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == "ELEVATION_UNSUPPORTED"
    assert calls == []


def test_flush_executor_requires_exact_runtime_binding_and_durable_intent(monkeypatch):
    class Token:
        def raise_if_cancelled(self):
            return None

    class Context:
        task_id = "p11-flush-fixture"
        execution_binding = {"elevation_operation": "FLUSH_DNS"}
        cancellation_token = Token()
        undo_stack = [{"action": "pending_mutation", "tool": "flush_dns_cache",
            "non_undoable": True, "pre_state": {"action": "non_undoable_elevation",
                "guard_version": 1, "non_undoable": True, "tool": "flush_dns_cache",
                "operation": "FLUSH_DNS", "operation_id": "6b75cd0d-6d3f-45a1-9b80-6af5306e30ae"}}]

    class NoIntent(Context):
        undo_stack = []

    denied = execute_flush_dns_cache({}, NoIntent())
    assert not denied.ok and denied.error_code == "COMMIT_JOURNAL_REQUIRED"

    context = Context()
    context.execution_binding = {"elevation_operation": "RESTART_SERVICE"}
    denied = execute_flush_dns_cache({}, context)
    assert not denied.ok and denied.error_code == "ELEVATION_BINDING_INVALID"

    calls = []
    def inert_execute_operation(self, operation, *, task_id, task_context, timeout_s=None):
        calls.append((operation, task_id, task_context, timeout_s))
        return ToolResult.success("flush_dns_cache",
            data={"operation": "FLUSH_DNS", "exit_code": 0, "process_exit_observed": True},
            factual_message="Inert broker result.", adapter_used="one_operation_uac")

    monkeypatch.setattr(ElevationBroker, "execute_operation", inert_execute_operation)
    context = Context()
    result = execute_flush_dns_cache({}, context)
    assert result.ok and len(calls) == 1
    operation, task_id, task_context, timeout_s = calls[0]
    assert operation.op_type == ElevationOpType.FLUSH_DNS
    assert task_id == context.task_id and task_context is context and timeout_s == 15.0
