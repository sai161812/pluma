"""Opening-only PowerShell scope: no commands or terminal input."""
from dataclasses import dataclass

import pytest

from pluma.adapters import app_launch as native
from pluma.core.task_supervisor import TaskState
from pluma.tools import terminal
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_app_launch_native import private_desktop
from tests.unit.test_window_state_native import desktop
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@dataclass
class InDesktop:
    name: str
    operation: str
    def __call__(self, args, context=None):
        with desktop(self.name):
            if self.operation == 'execute': return terminal.execute_open_terminal(args, context)
            return terminal.verify_open_terminal(args)


@pytest.mark.parametrize('completion', ['success', 'stop'])
def test_real_powershell_open_only(runtime, monkeypatch, completion):
    import win32process
    import _winapi
    from pluma.adapters.process_control import _target, _api
    approved(runtime, monkeypatch)
    with private_desktop() as name:
        def startup():
            info = win32process.STARTUPINFO(); info.lpDesktop = name; return info
        monkeypatch.setattr(native, 'startup_info', startup)
        spec = runtime.tool_registry.lookup('open_terminal')
        monkeypatch.setattr(spec, 'executor', InDesktop(name, 'execute'))
        monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'verify'))
        cap = task(runtime)
        state = None
        try:
            result = runtime.tool_registry.execute('open_terminal', {}, cap, runtime.ledger)
            assert result.ok and result.verified, result
            state = cap.undo_stack[-1]
            assert state['argv'][0].lower().endswith('windowspowershell\\v1.0\\powershell.exe')
            assert state['argv'][1:] == ['-NoLogo', '-NoProfile']
            assert result.private_context == {} and native.verify(state)
            if completion == 'success':
                runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
                assert cap.state == TaskState.SUCCEEDED
                assert native.verify(state)
                assert all(r.released_at is not None for r in cap.owned_resources if r.resource_type == 'subprocess')
            else:
                runtime.supervisor.request_stop(cap.task_id)
                assert cap.terminal_ready.wait(8)
                assert cap.state == TaskState.STOPPED, cap.stop_error
                assert native.verify(state, restored=True)
        finally:
            if state and not native.verify(state, restored=True):
                # Exact newly created fixture only; production never force-undoes
                # a terminal that may contain manually entered user commands.
                with _target(state['pid'], state['creation_time'], force=True) as (handle, check):
                    check(); c, w, kernel = _api(); assert kernel.TerminateProcess(handle, 1)
                    assert _winapi.WaitForSingleObject(handle, 1000) == _winapi.WAIT_OBJECT_0
            elif state is None and cap.state == TaskState.RUNNING:
                runtime.supervisor.request_stop(cap.task_id)
                assert cap.terminal_ready.wait(8)


@pytest.mark.parametrize('args', [{'working_dir': 'C:\\'}, {'working_dir': True}, {'command': 'arbitrary'},
    {'arguments': ['-Command', 'arbitrary']}, {'run_as_admin': True}])
def test_terminal_schema_precedes_policy(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('open_terminal', args, task(runtime), runtime.ledger)
    assert not decisions and not runtime.tool_registry._worker_controllers
