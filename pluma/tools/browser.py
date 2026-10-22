"""Typed browser tools restricted to PLUMA-created Edge/Chrome sessions."""
from functools import partial
from pathlib import Path
from typing import Literal
import json
import time
import uuid

from pydantic import BaseModel, Field, field_validator
from pluma.tools.base import ToolSpec, ToolResult, VerifyResult, RiskClass, AdapterPriority


class SessionArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    session_id: str = Field(pattern=r'^[a-f0-9-]{36}$')


class OpenURLArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    url: str = Field(min_length=1, max_length=4096)
    browser: Literal['edge', 'chrome'] = 'edge'
    session_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')

    @field_validator('url')
    @classmethod
    def allowed_url(cls, value):
        from urllib.parse import urlsplit
        parsed = urlsplit(value)
        if (any(ord(ch) < 32 for ch in value) or '\\' in value
                or value != 'about:blank' and (parsed.scheme not in ('http', 'https') or not parsed.hostname)
                or parsed.username is not None or parsed.password is not None):
            raise ValueError('Use an explicit HTTP/HTTPS URL without credentials.')
        return value


class OpenFileArgs(BaseModel):
    model_config = {'extra': 'forbid', 'strict': True}
    path: str = Field(min_length=1, max_length=32767)
    browser: Literal['edge', 'chrome'] = 'edge'
    session_id: str | None = Field(default=None, pattern=r'^[a-f0-9-]{36}$')

    @field_validator('path')
    @classmethod
    def literal_file(cls, value):
        from pluma.tools.files import FileInfoArgs
        return FileInfoArgs.explicit_filesystem_path(value)


class TabArgs(SessionArgs):
    tab_id: str = Field(pattern=r'^tab:[A-Fa-f0-9]{32}$')


class CloseTabArgs(TabArgs):
    expected_url: str = Field(min_length=1, max_length=4096)


class DownloadArgs(SessionArgs):
    limit: int = Field(default=20, ge=1, le=100)


def session(args, context):
    registry = context.tool_services['registry']
    with registry._lock:
        sessions = getattr(registry, '_browser_sessions', {})
        result = dict(sessions[args['session_id']])
    if args.get('browser', result['browser']) != result['browser']:
        raise ValueError('Session browser does not match.')
    return result


def capture(args, context, *, tool):
    from pluma.adapters import browser as native
    context.cancellation_token.raise_if_cancelled()
    if tool in ('open_url', 'open_file'):
        source = None
        if tool == 'open_file':
            from pluma.adapters.file_identity import snapshot
            path = Path(args['path'])
            if path.suffix.lower() not in ('.pdf', '.txt', '.html', '.htm', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
                raise ValueError('This file type has no registered viewer binding.')
            source = snapshot(str(path), context.cancellation_token)
            if source['kind'] != 'file': raise ValueError('A regular viewable file is required.')
        ident = str(uuid.uuid4())
        if args.get('session_id'):
            state = session(args, context)
            with native.connect(state, context.cancellation_token): pass
            return dict(state, action='browser_tab', operation=ident, tool=tool,
                source_path=args.get('path'), source_identity=source)
        from pluma.config.paths import get_paths
        profile = get_paths().cache_dir / ('browser-' + ident)
        if not profile.parent.is_dir() or profile.exists(): raise ValueError('New private profile path is unavailable.')
        launch = native.launch_intent(args['browser'], profile)
        launch['tool'] = tool
        return {'action': 'browser_tab', 'guard_version': 1, 'tool': tool,
            'operation': ident, 'session_id': ident, 'browser': args['browser'], 'profile': str(profile),
            'launch': launch, 'source_path': args.get('path'), 'source_identity': source}
    state = session(args, context)
    with native.connect(state, context.cancellation_token) as connection:
        current = native.observation(connection, args['tab_id'])
        if tool == 'close_tab':
            if current['url'] != args['expected_url']: raise ValueError('Exact tab URL changed.')
            return dict(state, action='browser_close', tool=tool, tab_id=args['tab_id'],
                url_digest=current['url_digest'], non_undoable=True)
        previous = native.selected(connection)
        before = native.observation(connection, previous)
        return dict(state, action='browser_focus', tool=tool, tab_id=args['tab_id'],
            navigation=current['navigation'], previous_tab=previous, previous_navigation=before['navigation'])


def pending(context, tool):
    return next(item['pre_state'] for item in reversed(context.undo_stack)
        if item.get('action') == 'pending_mutation' and item.get('tool') == tool)


def execute(args, context, *, tool):
    from pluma.adapters import browser as native
    from pluma.core.task_supervisor import ResourceOwnership
    token = context.cancellation_token
    try:
        token.raise_if_cancelled()
        if tool in ('list_tabs', 'download_status'):
            state = session(args, context)
            if tool == 'list_tabs':
                with native.connect(state, token) as connection: data = {'session_id': state['session_id'], 'tabs': native.tabs(connection)}
            else:
                data = {'session_id': state['session_id'], 'downloads': native.download_status(state, args.get('limit', 20)),
                    'availability': 'flushed_history' if native.subprocess_absent(state['pid'], state['creation_time']) else 'live_history_incomplete'}
            record = None
        else:
            state = dict(pending(context, tool))
            if state.get('tool') != tool: raise ValueError('Browser intent mismatch.')
            if tool in ('open_url', 'open_file'):
                new_session = 'launch' in state
                if 'launch' in state:
                    token.raise_if_cancelled()
                    profile_resource = native.create_profile(state['profile'], lambda:
                        context.register_owned_resource('temp_dir', ResourceOwnership.PLUMA_CREATED,
                            state['profile'], {'browser_launch_id': state['launch']['launch_id']}))
                    launch = native.app_launch.launch(state['launch'], context)
                    state.update(pid=launch['pid'], creation_time=launch['creation_time'], image=launch['argv'][0],
                        profile_identity=native.profile_identity(state['profile']))
                    profile_resource.metadata['browser_launch_id'] = launch['launch_id']
                    deadline = time.monotonic() + 2
                    while not (Path(state['profile']) / 'DevToolsActivePort').exists():
                        token.raise_if_cancelled()
                        if time.monotonic() >= deadline: raise TimeoutError('Browser endpoint did not appear.')
                        time.sleep(.02)
                    registry = context.tool_services['registry']
                    with registry._lock:
                        if not hasattr(registry, '_browser_sessions'): registry._browser_sessions = {}
                        registry._browser_sessions[state['session_id']] = {key: state[key] for key in
                            ('guard_version', 'session_id', 'browser', 'profile', 'profile_identity', 'pid', 'creation_time', 'image')}
                token.raise_if_cancelled()
                with native.connect(state, token) as connection:
                    # Causal returned ID, never claim an unrelated pre-existing tab.
                    if new_session:
                        seed = native.tabs(connection)
                        if len(seed) != 1 or seed[0]['url'] != 'about:blank':
                            raise ValueError('New private profile has no unique blank seed tab.')
                        target = seed[0]['tab_id'].removeprefix('tab:')
                        connection.call('Browser.setDownloadBehavior', {'behavior': 'allow',
                            'downloadPath': str(Path(state['profile']) / 'Downloads')})
                    else:
                        target = connection.call('Target.createTarget', {'url': 'about:blank'})['targetId']
                    tab = 'tab:' + target
                    record = dict(state, action='browser_tab', tab_id=tab)
                    resource = context.register_owned_resource('browser_tab', ResourceOwnership.PLUMA_CREATED, tab,
                        {'browser_state': record, 'task_id': context.task_id})
                    # A bounded private receipt supports interrupted-intent recovery.
                    receipt_path = Path(state['profile']) / ('operation-' + state['operation'] + '.json')
                    with receipt_path.open('x', encoding='utf-8') as handle:
                        json.dump({'tab_id': tab}, handle); handle.flush(); __import__('os').fsync(handle.fileno())
                    token.raise_if_cancelled()
                    url = args['url'] if tool == 'open_url' else Path(args['path']).as_uri()
                    from contextlib import ExitStack
                    with ExitStack() as held:
                        if tool == 'open_file':
                            path = Path(args['path'])
                            for parent in reversed(path.parents): held.enter_context(native.files._open(parent, parent=True))
                            held.enter_context(native.files._open(path))
                            if native.files.snapshot(path, token) != state['source_identity']: raise ValueError('File changed before open.')
                        with native.page(connection, tab) as call:
                            navigation = call('Page.navigate', {'url': url})
                            if navigation.get('errorText'): raise ValueError('Browser navigation failed.')
                        deadline = time.monotonic() + 2
                        while True:
                            token.raise_if_cancelled()
                            try:
                                current = native.observation(connection, tab)
                                if current['url'] == url or current['requested_url'] == url: break
                            except ValueError:
                                if time.monotonic() >= deadline: raise
                            if time.monotonic() >= deadline: raise TimeoutError('Requested page did not read back.')
                            time.sleep(.03)
                        if tool == 'open_file' and native.files.snapshot(args['path'], token) != state['source_identity']:
                            raise ValueError('File changed during open.')
                        if tool == 'open_file' and Path(args['path']).suffix.lower() == '.pdf' and current['mime_type'] != 'application/pdf':
                            raise ValueError('PDF viewer MIME readback failed.')
                    record['navigation'] = current['navigation']
                    record['url_digest'] = current['url_digest']
                    resource.metadata['browser_state'] = record
                    data = {'session_id': state['session_id'], 'tab_id': tab, 'url': current['url']}
            elif tool == 'focus_tab':
                with native.connect(state, token) as connection:
                    if native.selected(connection) != state['previous_tab']: raise ValueError('Prior selected tab changed.')
                    if native.observation(connection, state['tab_id'])['navigation'] != state['navigation']:
                        raise ValueError('Target navigation changed.')
                    connection.call('Target.activateTarget', {'targetId': state['tab_id'].removeprefix('tab:')})
                    native.wait_selected(connection, state['tab_id'])
                record = state
                data = {'session_id': state['session_id'], 'tab_id': state['tab_id']}
            else:
                with native.connect(state, token) as connection:
                    if native.observation(connection, state['tab_id'])['url_digest'] != state['url_digest']:
                        raise ValueError('Exact tab URL changed after confirmation.')
                    native.close(connection, state['tab_id'], state)
                record = None
                data = {'session_id': state['session_id'], 'tab_id': state['tab_id']}
        return ToolResult.success(tool, data=data, verified=True, undo_record=record,
            adapter_used='owned_browser_cdp', factual_message={
                'open_url': 'Opened and verified an owned browser tab.', 'open_file': 'Opened and verified the file in an owned browser tab.',
                'list_tabs': 'Read owned browser tabs.', 'focus_tab': 'Selected owned browser tab verified.',
                'close_tab': 'Owned browser tab closure verified.', 'download_status': 'Read owned browser download status.'}[tool]).model_copy(
                    update={'private_context': {'browser_state': record or state, 'browser_args': args}})
    except Exception:
        if tool == 'download_status':
            return ToolResult.failure(tool, 'Owned download history is locked or unavailable. No download completion is claimed.', 'DOWNLOAD_STATUS_UNAVAILABLE')
        return ToolResult.failure(tool, 'Owned browser operation was refused or could not be verified. Effects remain tracked.', 'BROWSER_UNVERIFIED')


def verify(result):
    from pluma.adapters import browser as native
    try:
        state = result.private_context['browser_state']
        args = result.private_context['browser_args']
        if result.tool == 'download_status':
            availability = 'flushed_history' if native.subprocess_absent(state['pid'], state['creation_time']) else 'live_history_incomplete'
            valid = (result.data['downloads'] == native.download_status(state, args.get('limit', 20))
                and result.data['availability'] == availability and result.adapter_used == 'owned_browser_cdp')
            return VerifyResult(ok=bool(valid and result.ok), method='owned_history_and_file_readback',
                detail='Owned download history and completed file sizes independently verified.')
        if result.tool == 'close_tab':
            return VerifyResult(ok=bool(result.ok and native.tab_absent(state)), method='owned_tab_or_original_process_absence',
                detail='Exact owned tab absence independently verified.')
        with native.connect(state) as connection:
            if result.tool == 'list_tabs': valid = result.data['tabs'] == native.tabs(connection)
            elif result.tool == 'download_status': valid = result.data['downloads'] == native.download_status(state, args.get('limit', 20))
            elif result.tool == 'close_tab': valid = not any(item['tab_id'] == args['tab_id'] for item in native.tabs(connection))
            else:
                current = native.observation(connection, result.data['tab_id'])
                valid = current['navigation'] == state['navigation'] and (result.tool != 'focus_tab' or native.selected(connection) == args['tab_id'])
                if result.tool == 'open_file': valid = valid and native.files.snapshot(args['path']) == state['source_identity']
        valid = valid and result.ok and result.adapter_used == 'owned_browser_cdp'
    except Exception: valid = False
    return VerifyResult(ok=bool(valid), method='owned_browser_protocol_readback',
        detail='Owned browser state independently read back.' if valid else 'Browser postcondition is unverified.')


BROWSER_TOOL_SPECS = [ToolSpec(name=name, description=description, args_schema=schema, risk_class=risk,
    timeout_s=20 if name in ('open_url', 'open_file') else 10, execution_scope='task_service',
    executor=partial(execute, tool=name), verifier=verify,
    undo_builder=partial(capture, tool=name) if name not in ('list_tabs', 'download_status') else None,
    non_undoable=name == 'close_tab', creates_resources=name in ('open_url', 'open_file'),
    adapter_priority=[AdapterPriority.NATIVE_API]) for name, schema, risk, description in [
        ('open_url', OpenURLArgs, RiskClass.LOW, 'Open an HTTP/HTTPS URL in a PLUMA-owned Edge or Chrome tab.'),
        ('open_file', OpenFileArgs, RiskClass.LOW, 'View a literal PDF, text, HTML or image file in an owned browser tab.'),
        ('list_tabs', SessionArgs, RiskClass.READ, 'List tabs only in a PLUMA-created browser session.'),
        ('focus_tab', TabArgs, RiskClass.LOW, 'Select an exact owned browser tab, retaining safe prior selection.'),
        ('close_tab', CloseTabArgs, RiskClass.MEDIUM, 'Gracefully close the exact confirmed owned tab; form/session state is not undoable.'),
        ('download_status', DownloadArgs, RiskClass.READ, 'Read bounded downloads from the owned profile and verify completed local files.')]]
