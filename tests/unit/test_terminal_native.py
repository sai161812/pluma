"""Closed terminal command evidence using native owned processes and isolated data."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import socket
import sys
import time

import pytest

from pluma.adapters import commands as native
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.tools.registry import ToolArgumentError
from pluma.tools.terminal import verify_command
from pluma.tools.base import ToolResult
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import await_file


def configure(runtime, root, script, *, timeout=8, inputs=None):
    executable = str(Path(sys.base_prefix) / 'python.exe')
    command = {'argv': [executable, '-c', script], 'timeout_s': timeout, 'inputs': inputs or []}
    catalog = {'version': 1, 'projects': {'fixture': {'root': str(root), 'commands': {'check': command}}}}
    path = Path(runtime.policy_engine.command_catalog_path)
    path.write_text(json.dumps(catalog), encoding='utf-8')
    # Isolated fixture storage can inherit the harness's shared-temp ACL. Give
    # only this owned config file the production-required private write ACL.
    import win32api
    import win32con
    import win32security as security
    token = security.OpenProcessToken(win32api.GetCurrentProcess(), win32con.TOKEN_QUERY)
    try:
        sid = security.ConvertSidToStringSid(security.GetTokenInformation(token, security.TokenUser)[0])
    finally:
        token.Close()
    descriptor = security.ConvertStringSecurityDescriptorToSecurityDescriptor(
        f'D:P(A;;FA;;;{sid})(A;;FA;;;SY)(A;;FA;;;BA)', 1)
    security.SetFileSecurity(str(path), security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION, descriptor)
    return path, catalog


@pytest.mark.parametrize('tool,command_id', [('run_command', 'hostname'), ('run_command', 'identity'),
    ('run_command', 'network'), ('run_powershell', 'os_version'), ('run_powershell', 'process_count')])
def test_native_fixed_diagnostics_have_real_exit_output_and_history(runtime, monkeypatch, tool, command_id):
    decisions = approved(runtime, monkeypatch)
    cap = task(runtime, 'owned-diagnostic')
    result = runtime.tool_registry.execute(tool, {'command_id': command_id}, cap, runtime.ledger)
    assert result.ok and result.verified, result
    assert not decisions and result.data['exit_code'] == 0
    output = result.data['command_output']['stdout'].strip()
    assert output
    if command_id == 'hostname':
        assert output.casefold() == socket.gethostname().casefold()
    elif command_id == 'process_count':
        assert int(output) > 0
    elif command_id == 'os_version':
        assert len(output.split('.')) >= 3
    assert not cap.undo_stack and result.private_context == {}
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(rows) == 1 and rows[0]['verified']
    assert json.loads(rows[0]['result_json'])['command_output'] == '[REDACTED]'


def test_configured_project_command_is_exactly_approved_non_undoable_and_redacted(runtime, monkeypatch, tmp_path):
    decisions = approved(runtime, monkeypatch)
    marker = tmp_path / 'owned-result.txt'
    configure(runtime, tmp_path,
        f"from pathlib import Path; Path({str(marker)!r}).write_text('owned'); print('private command fixture output')")
    cap = task(runtime, 'configured-command')
    args = {'project_id': 'fixture', 'command_id': 'check'}
    result = runtime.tool_registry.execute('run_project_command', args, cap, runtime.ledger)
    assert result.ok and result.verified, result
    assert marker.read_text() == 'owned'
    assert 'private command fixture output' in result.data['command_output']['stdout']
    assert len(decisions) == 1 and 'Command:' in decisions[0].target_summary
    assert str(tmp_path) in decisions[0].target_summary and 'No automatic undo' in decisions[0].prompt_message
    assert result.data['non_undoable'] is True and result.data['effect_state'] == 'committed'
    assert result.undo_record is None and cap.undo_stack[-1]['non_undoable'] is True
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    history = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert 'private command fixture output' not in json.dumps(history)
    assert json.loads(history[0]['result_json'])['command_output'] == '[REDACTED]'
    all_undo = runtime.db.execute_read('SELECT undo_json FROM undo_records')
    assert 'private command fixture output' not in json.dumps([list(row) for row in all_undo])


@pytest.mark.parametrize('mode', ['denied', 'missing', 'secret', 'secret_switch', 'elevation'])
def test_project_command_denial_or_bad_configuration_has_no_effect(runtime, monkeypatch, tmp_path, mode):
    approved(runtime, monkeypatch)
    marker = tmp_path / 'must-not-exist'
    path, catalog = configure(runtime, tmp_path, f"from pathlib import Path; Path({str(marker)!r}).touch()")
    if mode == 'denied':
        runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(lambda request: ConfirmationResponse(False))
    elif mode == 'missing':
        path.unlink()
    elif mode == 'secret':
        catalog['projects']['fixture']['commands']['check']['argv'][-1] = 'password=private-fixture'
        path.write_text(json.dumps(catalog))
    elif mode == 'secret_switch':
        catalog['projects']['fixture']['commands']['check']['argv'].extend(['--password', 'private-fixture-value'])
        path.write_text(json.dumps(catalog))
    else:
        catalog['projects']['fixture']['commands']['check']['argv'].append('runas')
        path.write_text(json.dumps(catalog))
    cap = task(runtime, 'denied-project-command')
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED'
    assert not marker.exists() and not cap.undo_stack


def test_project_configuration_changed_during_confirmation_is_refused(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    marker = tmp_path / 'must-not-exist'
    path, catalog = configure(runtime, tmp_path, f"from pathlib import Path; Path({str(marker)!r}).touch()")
    def change(request):
        catalog['projects']['fixture']['commands']['check']['argv'][-1] = "print('changed owner definition')"
        path.write_text(json.dumps(catalog))
        return ConfirmationResponse(True)
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(change)
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, task(runtime), runtime.ledger)
    assert not result.ok and not marker.exists()


@pytest.mark.parametrize('script,timeout,code', [("import sys; sys.exit(7)", 8, 'COMMAND_EXIT_NONZERO'),
    ("print('x'*100000)", 8, 'COMMAND_OUTPUT_LIMIT'), ('import time; time.sleep(30)', 1, 'COMMAND_TIMEOUT'),
    ("import sys; sys.stdout.buffer.write(bytes([255]))", 8, 'COMMAND_OUTPUT_ENCODING')])
def test_native_project_failure_overflow_and_timeout_are_not_success(runtime, monkeypatch, tmp_path, script, timeout, code):
    approved(runtime, monkeypatch)
    configure(runtime, tmp_path, script, timeout=timeout)
    cap = task(runtime, 'bounded-command-failure')
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, cap, runtime.ledger)
    assert not result.ok and not result.verified and result.undo_record is None
    assert result.error_code == code
    assert result.data['effect_state'] == 'unknown'
    assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


def test_stop_kills_only_owned_configured_command_tree(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    marker, late = tmp_path / 'entered.json', tmp_path / 'late'
    child = "import time; time.sleep(30)"
    script = ("import subprocess,sys,time,json; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}],creationflags=subprocess.CREATE_NO_WINDOW); "
        f"m=Path({str(marker)!r}); t=m.with_suffix('.partial'); t.write_text(json.dumps({{'child':p.pid}})); t.replace(m); "
        f"time.sleep(30); Path({str(late)!r}).touch()")
    configure(runtime, tmp_path, script, timeout=15)
    cap = task(runtime, 'stop-project-command')
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runtime.tool_registry.execute, 'run_project_command',
            {'project_id': 'fixture', 'command_id': 'check'}, cap, runtime.ledger)
        try:
            await_file(marker, future)
            child_pid = json.loads(marker.read_text())['child']
            from pluma.core.ownership import get_process_creation_time, subprocess_absent
            created = get_process_creation_time(child_pid)
            assert created > 0
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            result = future.result(3)
            assert not result.ok and not late.exists()
            assert subprocess_absent(child_pid, created)
            assert cap.state == TaskState.STOPPED_WITH_RESIDUAL
            assert cap.undo_stack[-1]['non_undoable'] is True
        finally:
            if not future.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)


@pytest.mark.parametrize('tool,args', [('run_command', {'command_id': 'hostname & del'}),
    ('run_command', {'command_id': 'hostname', 'command': 'echo injection'}),
    ('run_powershell', {'command_id': 'os_version', 'script': 'Get-Process'}),
    ('run_project_command', {'project_id': '..', 'command_id': 'check'}),
    ('run_project_command', {'project_id': 'fixture', 'command_id': 'check', 'argv': ['cmd.exe']})])
def test_command_schema_rejects_shell_strings_before_policy(runtime, monkeypatch, tool, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(tool, args, task(runtime), runtime.ledger)
    assert not decisions


def test_command_verifier_rejects_forged_success():
    assert not verify_command(ToolResult.success('run_command', data={}, verified=True)).ok


def test_shared_writable_catalog_is_refused_before_execution(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    path, _ = configure(runtime, tmp_path, "print('must not run')")
    import win32security as security
    descriptor = security.ConvertStringSecurityDescriptorToSecurityDescriptor('D:P(A;;FA;;;WD)', 1)
    security.SetFileSecurity(str(path), security.DACL_SECURITY_INFORMATION | security.PROTECTED_DACL_SECURITY_INFORMATION, descriptor)
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, task(runtime), runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED'


def test_project_command_risk_cannot_be_downgraded(runtime, monkeypatch, tmp_path):
    from pluma.tools.base import RiskClass
    approved(runtime, monkeypatch)
    configure(runtime, tmp_path, "print('must not run')")
    runtime.policy_rules._overrides['run_project_command'] = RiskClass.LOW
    decisions = []
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: decisions.append(request) or ConfirmationResponse(False))
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, task(runtime), runtime.ledger)
    assert not result.ok and len(decisions) == 1 and decisions[0].risk_class == RiskClass.HIGH


def test_configured_input_changed_during_approval_is_refused(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    source = tmp_path / 'owned-input.txt'
    source.write_text('before')
    configure(runtime, tmp_path, "print('must not run')", inputs=[str(source)])
    def change(request):
        source.write_text('newer owner input')
        return ConfirmationResponse(True)
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(change)
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, task(runtime), runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
    assert source.read_text() == 'newer owner input'


def test_parent_adoption_requires_exact_identity_and_original_task_job(runtime, monkeypatch, tmp_path):
    import _winapi
    from pluma.core.ownership import adopt_contained_process
    from tests.unit.test_process_control_native import owned_target
    approved(runtime, monkeypatch)
    with owned_target(runtime, tmp_path / 'owned-unrelated', 'headless') as (target, handle, cap):
        with pytest.raises(ValueError, match='identity changed'):
            adopt_contained_process(target['pid'], target['creation_time'] + 1, cap.job_object)
        with pytest.raises(ValueError, match='original task Job'):
            adopt_contained_process(target['pid'], target['creation_time'], cap.job_object)
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT
        from types import SimpleNamespace
        cap.job_object.assign_process(SimpleNamespace(sentinel=handle))
        promoted = adopt_contained_process(target['pid'], target['creation_time'], cap.job_object)
        promoted.close()
        assert _winapi.WaitForSingleObject(handle, 0) == _winapi.WAIT_TIMEOUT


def test_project_material_paths_are_checked_before_confirmation(runtime, monkeypatch, tmp_path):
    decisions = approved(runtime, monkeypatch)
    path, catalog = configure(runtime, tmp_path, "print('must not run')")
    catalog['projects']['fixture']['root'] = str(native.windows_directory())
    path.write_text(json.dumps(catalog))
    result = runtime.tool_registry.execute('run_project_command', {'project_id': 'fixture', 'command_id': 'check'}, task(runtime), runtime.ledger)
    assert not result.ok and result.error_code == 'POLICY_DENIED' and not decisions
