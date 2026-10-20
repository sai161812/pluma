"""Native owned disposal must not invent a user cancellation in task history."""
import os
from types import SimpleNamespace

import pytest

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core import job_object
from pluma.core.cancellation import StopReason
from pluma.core.request import PlumaRequest
from pluma.core.router import RouteResult
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.tools.registry import WorkerRequest
from tests.unit.test_mutation_journal import EmptyArgs
from tests.unit.test_runtime_shutdown import NATIVE_JOB, runtime, reopened
from tests.unit.test_worker_cancellation import owned_noop


def observe(args, context):
    return ToolResult.success('disposal_probe', factual_message='Owned fixture read completed.')


def fail(args, context):
    return ToolResult.failure('disposal_probe', 'Owned fixture failed.', 'TOOL_FAILED')


def crash(args, context):
    os._exit(7)  # Runs only in the disposable PLUMA-owned native worker.


def verify(result):
    return VerifyResult(ok=result.ok, method='state', detail='Owned fixture outcome checked.')


@pytest.mark.parametrize('smart', [False, True])
@pytest.mark.parametrize('mode', ['success', 'failure', 'crash'])
def test_native_terminal_history_preserves_actual_cause(runtime, monkeypatch, smart, mode):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    runtime.tool_registry.register(ToolSpec(name='disposal_probe', description='Owned disposal fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=6, process_isolated=True,
        executor={'success': observe, 'failure': fail, 'crash': crash}[mode], verifier=verify))
    route = RouteMode.SMART if smart else RouteMode.FAST
    plan = Plan(route=route, mode=PlanMode.MULTI_STEP if smart else PlanMode.DIRECT,
        steps=[ToolCall(tool='disposal_probe', arguments={}, purpose='Owned disposal check')])
    runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
        route=route, reason='Owned disposal fixture', plan=plan))
    planned = []
    def planning(**kwargs):
        planned.append('plan')
        return plan
    runtime.orchestrator._llm_manager = SimpleNamespace(plan=planning)
    req = PlumaRequest.from_text('Owned disposal check')
    cap = runtime.supervisor.create_task_capsule(request_id=req.request_id)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    result = runtime.orchestrator.execute(req, cap)
    assert runtime.close(3).complete
    row = reopened(runtime, cap)
    expected = 'SUCCEEDED' if mode == 'success' else 'FAILED'
    assert result.final_state == row['final_state'] == expected
    assert result.success == (mode == 'success')
    assert cap.stop_latch_set and controller.verify_cleanup()
    assert controller.worker_identity['ownership'] == 'PLUMA_CREATED'
    assert not runtime.tool_registry._worker_controllers
    expected_cause = None if mode == 'success' else StopReason.INTERNAL_ERROR
    assert cap.cancellation_token.reason == expected_cause
    assert row['stop_reason'] == (expected_cause.value if expected_cause else None)
    assert len(planned) == (1 if smart else 0), 'A sealed worker must not trigger a replan.'


@pytest.mark.parametrize('cause', [None, StopReason.USER_STOP, StopReason.TASK_TIMEOUT])
def test_disposal_seals_native_admission_without_replacing_first_cause(runtime, monkeypatch, cause):
    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    cap = runtime.supervisor.create_task_capsule(request_id='owned-disposal', history_expected=False)
    controller = runtime.tool_registry.get_worker(cap.task_id)
    cap.worker_controller = controller
    cap._tool_registry = runtime.tool_registry
    assert controller.execute_call(owned_noop, {}, WorkerRequest(cap.task_id, 'fixture', {}, 6), 6,
        job_object=cap.job_object, cancellation_token=cap.cancellation_token)[0] == 'ok'
    if cause is not None:
        cap.cancellation_token.cancel(cause)
    cap.close_resources()
    assert controller.verify_cleanup() and cap.stop_latch_set
    assert cap.cancellation_token.reason == cause
    if cause is None:
        # Disposal fences admission; it must not suppress a real later STOP.
        assert cap.cancellation_token.cancel(StopReason.USER_STOP)
        assert cap.cancellation_token.reason == StopReason.USER_STOP
