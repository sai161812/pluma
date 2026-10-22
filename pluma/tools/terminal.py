"""Typed closed diagnostics and explicitly configured, confirmed project commands."""
from functools import partial
from typing import Literal

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult


class OpenTerminalArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}


def capture_terminal(args, context=None):
    from pluma.adapters.terminal_window import capture
    return capture(args, context)


def execute_open_terminal(args, context=None):
    from pluma.adapters import app_launch
    try:
        context.cancellation_token.raise_if_cancelled()
        state = next(item['pre_state'] for item in reversed(context.undo_stack)
            if item.get('action') == 'pending_mutation' and item.get('tool') == 'open_terminal')
        if (state['action'] != 'app_launch' or state['tool'] != 'open_terminal'
                or state['app_name'] != 'windows_powershell'):
            raise ValueError('Terminal does not match its typed intent.')
        state = app_launch.launch(state, context)
        return ToolResult.success('open_terminal', data={key: state[key] for key in ('pid', 'creation_time')},
            verified=True, undo_record=state, adapter_used='native_owned_console',
            factual_message='PowerShell started in a new native console. Enter commands manually.').model_copy(
                update={'private_context': {'terminal_window': state}})
    except Exception:
        return ToolResult.failure('open_terminal', 'PowerShell launch ownership was refused or unverified.', 'TERMINAL_UNVERIFIED')


def verify_open_terminal(result):
    from pluma.adapters.app_launch import verify
    try:
        state = result.private_context['terminal_window']
        valid = (result.ok and result.tool == state['tool'] == 'open_terminal'
            and result.undo_record == state and result.adapter_used == 'native_owned_console'
            and result.data == {key: state[key] for key in ('pid', 'creation_time')}
            and verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_powershell_process_identity',
        detail='Owned PowerShell process identity independently verified.' if valid else 'Console state was not verified.')


class CommandArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    command_id: Literal['hostname', 'identity', 'network']


class PowerShellArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    command_id: Literal['os_version', 'process_count']


class ProjectCommandArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    project_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_-]*$')
    command_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-z][a-z0-9_-]*$')


class Output(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    stdout: str = Field(max_length=65536)
    stderr: str = Field(max_length=65536)


class CommandData(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    command_id: str
    pid: int = Field(gt=0)
    creation_time: int = Field(gt=0)
    exit_code: int
    output_encoding: Literal['utf-8', 'oem']
    command_output: Output
    stdout_bytes: int = Field(ge=0, le=65536)
    stderr_bytes: int = Field(ge=0, le=65536)


def project_prestate(args, context):
    from pluma.adapters.commands import project_binding, output_digest
    binding = getattr(context, 'execution_binding', None)
    if not binding or any(binding.get(key) != args[key] for key in ('command_id', 'project_id')):
        raise ValueError('Exact approved command binding is unavailable.')
    if project_binding(binding['catalog_path'], args) != binding:
        raise ValueError('Configured command changed after approval.')
    return {'action': 'non_undoable_command', 'guard_version': 1, 'non_undoable': True,
            'project_id': args['project_id'], 'command_id': args['command_id'],
            'definition_digest': output_digest(binding)}


def execute_command(args, context, *, tool):
    from pluma.adapters import commands as native
    from pluma.core.cancellation import TaskCancelledError
    try:
        if tool == 'run_project_command':
            pending = next(item for item in reversed(context.undo_stack)
                if item.get('action') == 'pending_mutation' and item.get('tool') == tool)
            state = pending['pre_state']
            binding = context.execution_binding
            if (state.get('non_undoable') is not True or not binding
                    or state.get('definition_digest') != native.output_digest(binding)
                    or any(binding[key] != args[key] or state[key] != args[key] for key in ('command_id', 'project_id'))):
                raise ValueError('Configured command does not match its journal/approval.')
        else:
            binding = native.diagnostic(tool, args['command_id'])
        data, proof = native.run(binding, context)
        ok = data['exit_code'] == 0
        result = ToolResult(ok=ok, tool=tool, data=CommandData.model_validate(data).model_dump(),
            verified=False, factual_message='Command exited successfully.' if ok else 'Command exited with a failure code.',
            adapter_used='owned_native_process', error=None if ok else 'Command exited with a failure code.',
            error_code=None if ok else 'COMMAND_EXIT_NONZERO').model_copy(update={'private_context': {'command_receipt': proof}})
        checked = verify_command(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except TimeoutError:
        return ToolResult.failure(tool, 'Command exceeded its configured deadline. Effects remain tracked.', 'COMMAND_TIMEOUT')
    except native.OutputLimitError:
        return ToolResult.failure(tool, 'Command output exceeded the configured bound. Effects remain tracked.', 'COMMAND_OUTPUT_LIMIT')
    except UnicodeError:
        return ToolResult.failure(tool, 'Command output does not match its configured encoding.', 'COMMAND_OUTPUT_ENCODING')
    except TaskCancelledError:
        return ToolResult.failure(tool, 'Command was stopped. Effects remain tracked.', 'TASK_CANCELLED')
    except Exception:
        return ToolResult.failure(tool, 'Command was refused, cancelled or unverified. Owned effects remain tracked.', 'COMMAND_UNVERIFIED')


def verify_command(result):
    from pluma.adapters.commands import output_digest
    from pluma.core.ownership import subprocess_absent
    try:
        data = CommandData.model_validate(result.data).model_dump()
        proof = result.private_context['command_receipt']
        valid = (result.ok and data['exit_code'] == proof['exit_readback'] == 0
            and data['stdout_bytes'] + data['stderr_bytes'] <= 65536 and proof['tree_empty'] is True
            and output_digest(data['command_output']) == proof['digest']
            and subprocess_absent(data['pid'], data['creation_time']))
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method='native_exit_output_and_owned_tree',
        detail='Native exit/output and owned-tree absence verified.' if valid else 'Command outcome was not verified.')


TERMINAL_TOOL_SPECS = [
    ToolSpec(name='open_terminal', description='Open Windows PowerShell only; the user types commands. No arguments, directory control or elevation.',
        args_schema=OpenTerminalArgs, risk_class=RiskClass.LOW, timeout_s=14, execution_scope='task_service',
        executor=execute_open_terminal, verifier=verify_open_terminal, undo_builder=capture_terminal,
        adapter_priority=[AdapterPriority.NATIVE_API], creates_resources=True),
    ToolSpec(name='run_command', description='Run a fixed read-only Windows diagnostic ID; no command strings.',
        args_schema=CommandArgs, risk_class=RiskClass.READ, timeout_s=12, process_isolated=True,
        executor=partial(execute_command, tool='run_command'), verifier=verify_command,
        adapter_priority=[AdapterPriority.POWERSHELL], creates_resources=True),
    ToolSpec(name='run_powershell', description='Run a fixed read-only PowerShell diagnostic ID without profile or policy bypass.',
        args_schema=PowerShellArgs, risk_class=RiskClass.READ, timeout_s=12, process_isolated=True,
        executor=partial(execute_command, tool='run_powershell'), verifier=verify_command,
        adapter_priority=[AdapterPriority.POWERSHELL], creates_resources=True),
    ToolSpec(name='run_project_command', description='Run one explicitly owner-configured command after exact material confirmation; non-undoable.',
        args_schema=ProjectCommandArgs, risk_class=RiskClass.HIGH, timeout_s=20, process_isolated=True,
        executor=partial(execute_command, tool='run_project_command'), verifier=verify_command,
        undo_builder=project_prestate, non_undoable=True,
        adapter_priority=[AdapterPriority.POWERSHELL], creates_resources=True),
]
