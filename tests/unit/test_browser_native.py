"""Real owned browser profiles, never-switched desktop and local HTTP fixtures."""
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import threading
import time

import pytest

from pluma.adapters import app_launch, browser as native
from pluma.core.task_supervisor import TaskState
from pluma.core.ownership import subprocess_absent
from pluma.tools import browser, system
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_app_launch_native import private_desktop
from tests.unit.test_window_state_native import desktop
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@dataclass
class InDesktop:
    name: str
    tool: str
    operation: str
    error_path: str = ''
    def __call__(self, args, context=None):
        try:
            if self.operation == 'execute': return browser.execute(args, context, tool=self.tool)
            if self.operation == 'verify': return browser.verify(args)
            if self.operation == 'undo': return system.execute_undo_last(args, context)
            return system.verify_undo_last(args)
        except Exception as error:
            if self.error_path:
                import traceback
                Path(self.error_path).write_text(traceback.format_exc())
            raise


def bind(runtime, monkeypatch, name):
    import win32process
    import win32gui
    import win32com.shell.shell
    approved(runtime, monkeypatch)
    def startup():
        result = win32process.STARTUPINFO(); result.lpDesktop = name; return result
    monkeypatch.setattr(app_launch, 'startup_info', startup)
    intent = native.launch_intent
    def fixture_intent(product, profile):
        state = intent(product, profile)
        state['argv'][1:1] = ['--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
            '--disable-features=CalculateNativeWinOcclusion']
        return state
    monkeypatch.setattr(native, 'launch_intent', fixture_intent)
    # Keep exact failure evidence local, without exposing URL/private protocol data.
    original = app_launch.launch
    def launch(state, context):
        try:
            with desktop(name): return original(state, context)
        except Exception as error:
            Path(runtime.paths.db_path).with_suffix('.browser-error.txt').write_text(type(error).__name__ + ': ' + str(error))
            raise
    monkeypatch.setattr(app_launch, 'launch', launch)
    for method in ('create_profile', 'observation', 'selected', 'wait_selected'):
        original_method = getattr(native, method)
        def diagnostic(*args, original_method=original_method, **kwargs):
            try: return original_method(*args, **kwargs)
            except Exception:
                import traceback
                Path(runtime.paths.db_path).with_suffix('.browser-error.txt').write_text(traceback.format_exc())
                raise
        monkeypatch.setattr(native, method, diagnostic)
    for tool in ('open_url', 'open_file', 'list_tabs', 'focus_tab', 'close_tab', 'download_status'):
        spec = runtime.tool_registry.lookup(tool)
        monkeypatch.setattr(spec, 'executor', InDesktop(name, tool, 'execute', str(Path(runtime.paths.db_path).with_suffix('.browser-error.txt'))))
        monkeypatch.setattr(spec, 'verifier', InDesktop(name, tool, 'verify'))
    spec = runtime.tool_registry.lookup('undo_last')
    monkeypatch.setattr(spec, 'executor', InDesktop(name, 'undo_last', 'undo'))
    monkeypatch.setattr(spec, 'verifier', InDesktop(name, 'undo_last', 'verify_undo'))


@contextmanager
def local_site():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/download':
                payload = b'PLUMA owned fixture download\n' * 20
                self.send_response(200); self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Disposition', 'attachment; filename=owned.txt')
            else:
                payload = ('<!doctype html><title>Owned fixture</title><input id="input"><p>' + self.path + '</p>').encode()
                self.send_response(200); self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(payload))); self.end_headers(); self.wfile.write(payload)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try: yield 'http://127.0.0.1:' + str(server.server_port)
    finally:
        server.shutdown(); server.server_close(); thread.join(2); assert not thread.is_alive()


def execute(runtime, tool, args, *, finalize=True):
    cap = task(runtime, tool)
    result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
    error = Path(runtime.paths.db_path).with_suffix('.browser-error.txt')
    assert result.ok and result.verified, (result, error.read_text() if error.exists() else '')
    assert result.private_context == {}
    if finalize: runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    return result, cap


def fixture_cleanup(runtime, name):
    # Production success transfers profiles/windows to the user. This fixture
    # retains original handles/Jobs solely to drain its own private test sessions.
    sessions = list(getattr(runtime.tool_registry, '_browser_sessions', {}).values())
    for state in sessions:
        if subprocess_absent(state['pid'], state['creation_time']): continue
        try:
            with native.connect(state) as connection:
                try: connection.call('Browser.close')
                except Exception: pass  # native exit can precede its reply
        except Exception:
            pass  # final tab close can precede process exit/socket shutdown
        deadline = time.monotonic() + 3
        while not subprocess_absent(state['pid'], state['creation_time'], wait_s=.3):
            assert time.monotonic() < deadline, 'Owned fixture browser did not exit.'


@pytest.mark.parametrize('product', ['edge', 'chrome'])
def test_native_tabs_selection_confirmation_inverse_and_stop(runtime, monkeypatch, product):
    with private_desktop() as name, local_site() as site:
        bind(runtime, monkeypatch, name)
        try:
            first, cap = execute(runtime, 'open_url', {'url': site + '/one', 'browser': product})
            session = {'session_id': first.data['session_id']}
            listed, _ = execute(runtime, 'list_tabs', session)
            assert first.data['tab_id'] in [row['tab_id'] for row in listed.data['tabs']]
            second, _ = execute(runtime, 'open_url', dict(session, browser=product, url=site + '/two'))
            focused, _ = execute(runtime, 'focus_tab', dict(session, tab_id=first.data['tab_id']))
            undone, _ = execute(runtime, 'undo_last', {})
            assert undone.data['action'] == 'browser_focus'
            undone, _ = execute(runtime, 'undo_last', {})
            assert undone.data['action'] == 'browser_tab'
            fresh, stopped = execute(runtime, 'open_url', dict(session, browser=product, url=site + '/stop'), finalize=False)
            runtime.supervisor.request_stop(stopped.task_id)
            assert stopped.terminal_ready.wait(8)
            assert stopped.state == TaskState.STOPPED, stopped.stop_error
            state = runtime.tool_registry._browser_sessions[session['session_id']]
            with native.connect(state) as connection:
                assert fresh.data['tab_id'] not in [row['tab_id'] for row in native.tabs(connection)]
            execute(runtime, 'close_tab', dict(session, tab_id=first.data['tab_id'], expected_url=site + '/one'))
        finally: fixture_cleanup(runtime, name)


def pdf_bytes():
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 4 0 R >>',
        b'<< /Length 0 >>\nstream\n\nendstream']
    data, offsets = b'%PDF-1.4\n', [0]
    for index, body in enumerate(objects, 1):
        offsets.append(len(data)); data += str(index).encode() + b' 0 obj\n' + body + b'\nendobj\n'
    xref = len(data)
    data += b'xref\n0 5\n0000000000 65535 f \n'
    data += b''.join(('%010d 00000 n \n' % offset).encode() for offset in offsets[1:])
    return data + ('trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % xref).encode()


@pytest.mark.parametrize('product', ['edge', 'chrome'])
def test_native_pdf_file_and_download_readback(runtime, monkeypatch, tmp_path, product):
    # Minimal valid one-page PDF generated from fixture data, no external assets.
    path = tmp_path / 'owned.txt'; path.write_text('PLUMA local file fixture', encoding='utf-8')
    pdf = tmp_path / 'owned.pdf'; pdf.write_bytes(pdf_bytes())
    with private_desktop() as name, local_site() as site:
        bind(runtime, monkeypatch, name)
        try:
            opened, _ = execute(runtime, 'open_file', {'path': str(path), 'browser': product})
            session = {'session_id': opened.data['session_id']}
            state = runtime.tool_registry._browser_sessions[session['session_id']]
            viewed, _ = execute(runtime, 'open_file', dict(session, browser=product, path=str(pdf)))
            assert viewed.data['url'] == pdf.as_uri() and pdf.read_bytes() == pdf_bytes()
            page, _ = execute(runtime, 'open_url', dict(session, browser=product, url=site + '/download-page'))
            with native.connect(state) as connection, native.page(connection, page.data['tab_id']) as call:
                call('Page.navigate', {'url': site + '/download'})
            deadline = time.monotonic() + 3
            while not (Path(state['profile']) / 'Downloads/owned.txt').exists():
                assert time.monotonic() < deadline
                time.sleep(.03)
            while (Path(state['profile']) / 'Downloads/owned.txt').stat().st_size != 580:
                assert time.monotonic() < deadline
                time.sleep(.03)
            time.sleep(.5)
            fixture_cleanup(runtime, name)
            # Chromium flushes its authoritative History on graceful shutdown.
            # Do not bypass its live SQLite lock or fabricate completion from a
            # filename. This fixture verifies the flushed complete record.
            deadline = time.monotonic() + 2
            while True:
                try: rows = native.download_status(state, 20)
                except __import__('sqlite3').OperationalError: rows = []
                if rows and rows[0]['state'] == 'complete': break
                assert time.monotonic() < deadline, rows
                time.sleep(.05)
            download, _ = execute(runtime, 'download_status', session)
            assert download.data['downloads'][0]['state'] == 'complete'
        finally: fixture_cleanup(runtime, name)


@pytest.mark.parametrize('tool,args', [
    ('open_url', {'url': 'javascript:alert(1)'}), ('open_url', {'url': 'https://user:pass@example.test'}),
    ('open_url', {'url': 'https://example.test', 'arguments': ['--no-sandbox']}),
    ('open_file', {'path': 'relative.pdf'}), ('focus_tab', {'session_id': 'unknown', 'tab_id': 'tab:0'}),
    ('download_status', {'session_id': '00000000-0000-0000-0000-000000000000', 'limit': 101}),
])
def test_browser_schema_before_policy(runtime, monkeypatch, tool, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute(tool, args, task(runtime), runtime.ledger)
    assert not decisions and not getattr(runtime.tool_registry, '_browser_sessions', {})


def test_unknown_session_and_missing_journal_never_launch(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    unknown = '00000000-0000-0000-0000-000000000000'
    result = runtime.tool_registry.execute('list_tabs', {'session_id': unknown}, task(runtime), runtime.ledger)
    assert not result.ok
    result = runtime.tool_registry.execute('open_url', {'url': 'https://example.test'})
    assert not result.ok and result.error_code == 'WINDOW_JOURNAL_REQUIRED'
    assert not getattr(runtime.tool_registry, '_browser_sessions', {})


def test_browser_denial_precedes_private_profile_creation(runtime, monkeypatch):
    from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: ConfirmationResponse(approved=False))
    before = set(runtime.paths.cache_dir.iterdir())
    result = runtime.tool_registry.execute('close_tab', {'session_id': '00000000-0000-0000-0000-000000000000',
        'tab_id': 'tab:' + 'A' * 32, 'expected_url': 'https://example.test'}, task(runtime), runtime.ledger)
    assert not result.ok and set(runtime.paths.cache_dir.iterdir()) == before
    assert not getattr(runtime.tool_registry, '_browser_sessions', {})
