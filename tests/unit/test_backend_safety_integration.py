"""P10 combined Windows safety: owned files/processes/pipes, inert devices.

The policy owner and router are fixture-only. No real application, model,
microphone, hotkey or elevation is activated. Native containment is not mocked.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from pluma.brain.schemas import Plan, PlanMode, RouteMode, ToolCall
from pluma.core import job_object
from pluma.core.ipc import IpcClient
from pluma.core.ownership import get_process_creation_time, subprocess_absent
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteResult
from pluma.core.stop_protocol import StopReply, StopOutcome
from pluma.core.task_supervisor import ResourceOwnership
from pluma.memory.activity import ActivityQuery
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from tests.unit.test_runtime_shutdown import runtime, NATIVE_JOB, reopened
from tests.unit.test_worker_cancellation import EmptyArgs, OwnedProbe, await_file


@pytest.mark.skipif(sys.platform != 'win32', reason='Requires real Windows Jobs and native pipes')
@pytest.mark.parametrize('route', [RouteMode.FAST, RouteMode.SMART])
@pytest.mark.parametrize('conflict', [False, True], ids=['restored', 'conflict-preserved'])
def test_native_stop_reconciles_rollback_processes_history_and_shutdown(
        runtime, monkeypatch, tmp_path, conflict, route, record_property):
    import _winapi

    monkeypatch.setattr(job_object, 'WindowsJobObject', NATIVE_JOB)
    # Only registered fixture tools are routed; no policy/elevation acceptance.
    runtime.tool_registry._policy_engine = None
    source, moved = tmp_path / 'source.txt', tmp_path / 'moved.txt'
    source.write_text('owned original', encoding='utf-8')
    survivor_file = tmp_path / 'preexisting.txt'
    survivor_file.write_text('preexisting fixture', encoding='utf-8')
    survivor = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                creationflags=subprocess.CREATE_NO_WINDOW)
    survivor_created = get_process_creation_time(survivor.pid)
    child_handle = None
    release = threading.Event()
    cap = None
    try:
        assert survivor_created is not None
        req = PlumaRequest(input_mode=InputMode.TEXT, text='P10 owned integration fixture')
        cap = runtime.supervisor.create_task_capsule(request_id=req.request_id, history_expected=False)
        native_job = cap.job_object
        assert isinstance(native_job, NATIVE_JOB)
        cap.register_owned_resource('subprocess', ResourceOwnership.PREEXISTING,
            str(survivor.pid), {'pid': survivor.pid, 'creation_time': survivor_created,
                                'task_id': cap.task_id, 'command_class': 'p10_survivor'})
        cap.register_owned_resource('temp_file', ResourceOwnership.PREEXISTING,
                                    str(survivor_file))
        # Identity mismatch means the old identity is absent, never permission
        # to terminate the live replacement. This does not emulate a reboot.
        assert subprocess_absent(survivor.pid, survivor_created + 1)
        assert not subprocess_absent(survivor.pid, survivor_created)
        assert survivor.poll() is None

        def move(args):
            source.rename(moved)
            return ToolResult.success('p10_move', factual_message='Owned file moved.')

        def capture(args):
            assert source.read_text(encoding='utf-8') == 'owned original' and not moved.exists()
            return {'action': 'move_file', 'source': str(source), 'destination': str(moved)}

        def verify(result):
            return VerifyResult(ok=moved.read_text(encoding='utf-8') == 'owned original'
                and not source.exists(), method='filesystem', detail='Owned file read back.')

        runtime.tool_registry.register(ToolSpec(name='p10_move', description='Owned file move',
            args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=3,
            executor=move, verifier=verify, undo_builder=capture))
        runtime.tool_registry.register(ToolSpec(name='worker_probe', description='Owned blocked worker',
            args_schema=EmptyArgs, risk_class=RiskClass.HIGH, timeout_s=10,
            executor=OwnedProbe(str(tmp_path), descendant=True),
            verifier=lambda res: VerifyResult(ok=False, method='filesystem', detail='No late effect permitted.')))
        next_calls = []

        def next_step(args):
            next_calls.append(True)
            return ToolResult.success('p10_next')

        runtime.tool_registry.register(ToolSpec(name='p10_next', description='Forbidden next fixture step',
            args_schema=EmptyArgs, risk_class=RiskClass.READ, timeout_s=1,
            executor=next_step, verifier=lambda res: VerifyResult(ok=True, method='state', detail='Fixture only.')))
        plan = Plan(route=route, mode=PlanMode.MULTI_STEP, steps=[ToolCall(tool=name, arguments={}, purpose='Owned fixture')
                    for name in ['p10_move', 'worker_probe', 'p10_next']])
        runtime.orchestrator._router = SimpleNamespace(route=lambda req: RouteResult(
            route=route, reason='Owned fixture', plan=plan))
        planning_calls, replans = [], []

        def initial_plan(**kwargs):
            assert kwargs['cancellation_token'] is cap.cancellation_token
            planning_calls.append(True)
            return plan

        def forbidden_replan(**kwargs):
            replans.append(True)
            raise AssertionError('No replan is permitted after STOP')

        runtime.orchestrator._llm_manager = SimpleNamespace(plan=initial_plan)
        runtime.orchestrator._multi_step.planner = SimpleNamespace(plan=forbidden_replan)
        cleanup_entered = threading.Event()
        cleanup = runtime.supervisor._cleanup_stopped_task

        def held_cleanup(value, *args, **kwargs):
            assert value.stop_latch_set
            cleanup_entered.set()
            assert release.wait(3)
            return cleanup(value, *args, **kwargs)

        monkeypatch.setattr(runtime.supervisor, '_cleanup_stopped_task', held_cleanup)
        latched = []
        cancel = cap.cancellation_token.cancel

        def observed_cancel(*args, **kwargs):
            cancel(*args, **kwargs)
            if not latched:
                latched.append(time.perf_counter())

        monkeypatch.setattr(cap.cancellation_token, 'cancel', observed_cancel)
        core = runtime.resident_core
        core.ipc.start()  # owned authenticated pipe only

        def stop():
            data = IpcClient(address=core.ipc.address, require_auth=True).send_command(
                {'command': 'stop_task', 'task_id': cap.task_id})
            return StopReply.model_validate_json(json.dumps(data))

        with ThreadPoolExecutor(1) as pool:
            executing = pool.submit(runtime.orchestrator.execute, req, cap)
            try:
                await_file(tmp_path / 'entered', executing)
                assert moved.read_text(encoding='utf-8') == 'owned original'
                if conflict:
                    source.write_text('newer fixture content', encoding='utf-8')
                controller = cap.worker_controller
                root = controller._proc
                identity = dict(controller.worker_identity)
                assert identity['task_id'] == cap.task_id and identity['pid'] == root.pid
                assert identity['creation_time'] == get_process_creation_time(root.pid)
                assert identity['ownership'] == 'PLUMA_CREATED' and identity['command_class'] == 'tool_worker'
                child = int((tmp_path / 'child').read_text())
                child_created = get_process_creation_time(child)
                assert child_created is not None
                child_handle = _winapi.OpenProcess(0x100000 | 0x1000, False, child)
                assert _winapi.WaitForSingleObject(child_handle, 0) == _winapi.WAIT_TIMEOUT
                assert native_job.active_process_count() >= 2
                started = time.perf_counter()
                first = stop()
                acknowledged = time.perf_counter()
                assert cleanup_entered.is_set() and latched
                assert first.tasks[0].outcome == StopOutcome.PENDING and first.stopped_count == 0
                assert first.latch_acknowledged_count == 1 and cap.stop_latch_set
                assert not cap.terminal_ready.is_set()
            finally:
                release.set()
                # Failure before STOP must also drain before the pool joins.
                if not cap.stop_latch_set:
                    runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = executing.result(3)
        assert runtime.supervisor.join_stop_operations(3)
        terminal = time.perf_counter()
        final = stop()
        item = final.tasks[0]
        expected = 'STOPPED_WITH_RESIDUAL' if conflict else 'STOPPED'
        assert result.final_state == item.final_state == cap.state.value == expected
        assert result.success is False and result.rollback_performed and item.rollback_performed
        assert result.rollback_success is item.rollback_success is (not conflict)
        assert result.has_residual is item.has_residual is conflict
        assert result.completion_verified and item.completion_verified and cap.terminal_ready.is_set()
        assert result.terminal_persisted is item.terminal_persisted is cap.terminal_persisted is True
        assert final.stopped_count == (0 if conflict else 1)
        assert item.outcome == (StopOutcome.RESIDUAL if conflict else StopOutcome.STOPPED)
        entries = [entry.model_dump() for entry in item.cleanup_evidence]
        query = ActivityQuery(runtime.db)
        report = json.loads(query.cleanup_report_for_task(cap.task_id)['metadata_json'])
        assert query.task_by_id(cap.task_id)['final_state'] == expected
        assert result.cleanup_evidence == entries == cap.outcome_details()['cleanup_evidence'] == report['entries']
        mirror = next(row for row in query.resources_for_task(cap.task_id) if row['resource_type'] == 'cleanup_report')
        assert json.loads(mirror['metadata_json'])['entries'] == entries
        actions = query.actions_for_task(cap.task_id)
        assert [row['tool'] for row in actions] == ['p10_move', 'worker_probe']
        assert actions[0]['verified'] and not actions[1]['verified']
        assert not replans and len(planning_calls) == int(route == RouteMode.SMART)
        assert not next_calls and len(result.steps) == 2 and not (tmp_path / 'late').exists()
        assert source.read_text(encoding='utf-8') == ('newer fixture content' if conflict else 'owned original')
        assert moved.exists() is conflict
        if conflict:
            assert moved.read_text(encoding='utf-8') == 'owned original'
        rollback = next(entry for entry in entries if entry['kind'] == 'rollback')
        assert rollback['identity']['attempted'] == 1
        assert rollback['identity']['failed'] == int(conflict)
        assert rollback['identity']['succeeded'] == int(not conflict)
        assert len(query.available_undo_records_for_task(cap.task_id)) == int(conflict)
        assert len(cap.undo_stack) == int(conflict)
        assert _winapi.WaitForSingleObject(child_handle, 1000) == _winapi.WAIT_OBJECT_0
        assert subprocess_absent(child, child_created) and not root.is_alive()
        assert controller.verify_cleanup() is True and native_job.is_closed is True
        assert cap.worker_controller is cap.job_object is None
        record_property('request_to_latch_seconds', latched[0] - started)
        record_property('stop_reply_seconds', acknowledged - started)
        record_property('terminal_cleanup_seconds', terminal - started)
        assert latched[0] <= acknowledged < terminal  # separate observations, no hardware p95 claim
        assert runtime.close(3).complete
        assert runtime._shutdown_session.worker is None and not runtime.db._writer_thread.is_alive()
        assert runtime.tool_registry.work_gate.wait_idle(0) and runtime.supervisor.execution_gate.wait_idle(0)
        reopened(runtime, cap)
        assert survivor.poll() is None and get_process_creation_time(survivor.pid) == survivor_created
        assert survivor_file.read_text(encoding='utf-8') == 'preexisting fixture'
    finally:
        release.set()
        if cap is not None and not cap.stop_latch_set:
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
        if child_handle is not None:
            _winapi.CloseHandle(child_handle)
        # Only this test's original Popen handle; never a PID/name lookup kill.
        if survivor.poll() is None:
            survivor.kill()
        survivor.wait(timeout=3)
