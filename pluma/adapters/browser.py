"""On-demand CDP for explicitly owned Edge/Chrome profiles. No public RPC API."""
from contextlib import contextmanager, ExitStack, closing
from pathlib import Path
import hashlib
import json
import os
import socket
import sqlite3
import time
import uuid

from pluma.adapters import app_launch, file_identity as files
from pluma.adapters.processes import _process
from pluma.core.ownership import subprocess_absent


def digest(value):
    return list(hashlib.sha256(json.dumps(value, sort_keys=True).encode()).digest())


def executable(browser):
    # Native known folders, not PATH or caller-supplied executable names.
    import win32com.shell.shell as shell
    import win32com.shell.shellcon as folders
    folder = folders.CSIDL_PROGRAM_FILESX86 if browser == 'edge' else folders.CSIDL_PROGRAM_FILES
    root = Path(shell.SHGetFolderPath(0, folder, 0, 0))
    return root / ('Microsoft/Edge/Application/msedge.exe' if browser == 'edge' else 'Google/Chrome/Application/chrome.exe')


def launch_intent(browser, profile):
    image = executable(browser)
    with files._open(image.parent, parent=True) as handle:
        directory = files._parent_identity(handle)
    return {'action': 'app_launch', 'guard_version': 1, 'tool': 'open_url', 'launch_id': str(uuid.uuid4()),
        'app_name': browser, 'argv': [str(image), '--user-data-dir=' + str(profile),
            '--remote-debugging-port=0', '--remote-debugging-address=127.0.0.1',
            '--no-first-run', '--no-default-browser-check', '--disable-background-networking',
            '--disable-sync', 'about:blank'], 'cwd': str(image.parent),
        'image_identity': files.snapshot(image), 'directory_identity': directory}


def profile_identity(path):
    with files._open(Path(path), parent=True) as handle:
        return files._parent_identity(handle)


def create_profile(path, on_created):
    import win32api, win32security, ntsecuritycon
    import win32file
    path = Path(path)
    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    try: sid = win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    finally: token.Close()
    acl = win32security.ACL()
    for principal in (sid, win32security.CreateWellKnownSid(win32security.WinLocalSystemSid, None)):
        acl.AddAccessAllowedAceEx(win32security.ACL_REVISION, 3, ntsecuritycon.FILE_ALL_ACCESS, principal)
    sd = win32security.SECURITY_DESCRIPTOR()
    sd.SetSecurityDescriptorDacl(1, acl, 0)
    sd.SetSecurityDescriptorControl(win32security.SE_DACL_PROTECTED, win32security.SE_DACL_PROTECTED)
    import pywintypes
    attributes = pywintypes.SECURITY_ATTRIBUTES(); attributes.SECURITY_DESCRIPTOR = sd
    win32file.CreateDirectory(str(path), attributes)
    resource = on_created()
    (path / 'Default').mkdir(); (path / 'Downloads').mkdir()
    (path / 'Default/Preferences').write_text(json.dumps({'download': {
        'default_directory': str(path / 'Downloads'), 'prompt_for_download': False},
        'background_mode': {'enabled': False}}), encoding='utf-8')
    return resource


class Connection:
    def __init__(self, ws, token=None): self.ws, self.token, self.serial = ws, token, 0
    def call(self, method, params=None, session=None):
        self.serial += 1
        request = {'id': self.serial, 'method': method, 'params': params or {}}
        if session: request['sessionId'] = session
        if self.token: self.token.raise_if_cancelled()
        self.ws.send(json.dumps(request))
        deadline = time.monotonic() + 2
        for _ in range(512):
            if self.token: self.token.raise_if_cancelled()
            if time.monotonic() >= deadline: raise TimeoutError('Browser readback timed out.')
            try: response = json.loads(self.ws.recv(timeout=.05))
            except TimeoutError: continue
            if response.get('id') == self.serial:
                # CDP error text may contain the current page URL or other
                # private page data; retain only its protocol status code.
                if 'error' in response: raise ValueError('Browser refused ' + method + ': ' + str(response['error'].get('code')))
                return response['result']
        raise ValueError('Browser event count exceeds the bound.')


@contextmanager
def connect(state, token=None):
    from websockets.sync.client import connect as websocket
    profile = Path(state['profile'])
    with ExitStack() as held:
        for parent in reversed(profile.parents): held.enter_context(files._open(parent, parent=True))
        held.enter_context(files._open(profile, parent=True))
        if profile_identity(profile) != state['profile_identity']: raise ValueError('Owned profile changed.')
        process, created = held.enter_context(_process(state['pid'], state['creation_time']))
        if os.path.normcase(process.exe()) != os.path.normcase(state['image']): raise ValueError('Browser image changed.')
        endpoint = profile / 'DevToolsActivePort'
        with files._open(endpoint):
            if endpoint.stat().st_size > 256: raise ValueError('Browser endpoint exceeds the bound.')
            port, route = endpoint.read_text(encoding='ascii').splitlines()
        port = int(port)
        import re
        if not 1 <= port <= 65535 or not re.fullmatch(r'/devtools/browser/[a-fA-F0-9-]{36}', route):
            raise ValueError('Invalid private browser endpoint.')
        sock = socket.create_connection(('127.0.0.1', port), timeout=1)
        held.callback(sock.close)
        peer, local = sock.getpeername(), sock.getsockname()
        # Verify the accepted server socket belongs to the exact launched root.
        if not any(row.status == 'ESTABLISHED' and tuple(row.laddr) == peer and tuple(row.raddr) == local
                for row in process.net_connections(kind='tcp4')):
            raise ValueError('Browser socket peer is not the owned process.')
        ws = held.enter_context(websocket('ws://127.0.0.1:' + str(port) + route,
            sock=sock, proxy=None, compression=None, ping_interval=None,
            open_timeout=1, close_timeout=.2, max_size=1048576, max_queue=2))
        yield Connection(ws, token)


def tabs(connection):
    targets = connection.call('Target.getTargets')['targetInfos']
    if len(targets) > 256: raise ValueError('Browser target count exceeds the bound.')
    return [{'tab_id': 'tab:' + item['targetId'], 'url': item['url']}
        for item in targets if item['type'] == 'page']


@contextmanager
def page(connection, tab):
    session = connection.call('Target.attachToTarget', {'targetId': tab.removeprefix('tab:'), 'flatten': True})['sessionId']
    try: yield lambda method, params=None: connection.call(method, params, session)
    finally:
        # Detach is connection cleanup, permitted even after STOP. Socket closure
        # also releases the non-mutating inspector attachment if detach fails.
        try:
            old, connection.token = connection.token, None
            connection.call('Target.detachFromTarget', {'sessionId': session})
        except Exception:
            pass  # a closed target has already destroyed this attachment
        finally: connection.token = old


_DIRTY = """(() => { if (!globalThis.__plumaGuard) {globalThis.__plumaGuard={dirty:false};
for (const n of ['input','change','keydown','pointerdown']) addEventListener(n,e=>{
if(e.isTrusted)globalThis.__plumaGuard.dirty=true;},true);} return globalThis.__plumaGuard.dirty;})()"""


def observation(connection, tab):
    with page(connection, tab) as call:
        history = call('Page.getNavigationHistory')
        entry = history['entries'][history['currentIndex']]
        tree = call('Page.getFrameTree')['frameTree']
        # Avoid claiming safe inverse for an unobserved child-frame input state.
        frame = tree['frame']
        world = call('Page.createIsolatedWorld', {'frameId': frame['id'], 'worldName': 'pluma-owned-undo'})['executionContextId']
        dirty = call('Runtime.evaluate', {'expression': _DIRTY, 'contextId': world, 'returnByValue': True})
        visible = call('Runtime.evaluate', {'expression': 'document.visibilityState', 'contextId': world, 'returnByValue': True})
        return {'navigation': digest([entry['id'], entry['url'], frame['loaderId']]),
            'url_digest': digest(entry['url']), 'dirty': bool(tree.get('childFrames')) or dirty['result'].get('value') is not False,
            'visible': visible['result'].get('value') == 'visible', 'url': entry['url'],
            'requested_url': entry.get('userTypedURL', entry['url']), 'mime_type': frame.get('mimeType')}


def selected(connection):
    found = [item['tab_id'] for item in tabs(connection) if observation(connection, item['tab_id'])['visible']]
    if len(found) != 1: raise ValueError('Selected owned tab is ambiguous or unavailable.')
    return found[0]


def wait_selected(connection, expected):
    deadline = time.monotonic() + 2
    while True:
        try:
            if selected(connection) == expected: return
        except ValueError:
            pass  # activation can temporarily detach the former renderer
        if time.monotonic() >= deadline: raise TimeoutError('Selected tab did not read back.')
        time.sleep(.03)


def close(connection, tab, state=None):
    deadline = time.monotonic() + 1
    try:
        with page(connection, tab) as call: call('Page.close')
        while any(item['tab_id'] == tab for item in tabs(connection)):
            if time.monotonic() >= deadline: raise TimeoutError('Owned tab refused graceful close.')
            time.sleep(.02)
    except Exception:
        if not state or not subprocess_absent(state['pid'], state['creation_time'], wait_s=.3): raise


def tab_absent(state):
    if subprocess_absent(state['pid'], state['creation_time']): return True
    try:
        with connect(state) as connection:
            return not any(item['tab_id'] == state['tab_id'] for item in tabs(connection))
    except Exception:
        if subprocess_absent(state['pid'], state['creation_time'], wait_s=.3): return True
        raise


def restore(state):
    if tab_absent(state): return
    with connect(state) as connection:
        current = observation(connection, state['tab_id'])
        if current['dirty'] or current['navigation'] != state['navigation']:
            raise ValueError('Owned tab has newer input/navigation; preserve it.')
        if state['action'] == 'browser_tab': close(connection, state['tab_id'], state)
        elif state['action'] == 'browser_focus':
            if selected(connection) != state['tab_id']: raise ValueError('Selected tab changed.')
            before = observation(connection, state['previous_tab'])
            if before['navigation'] != state['previous_navigation'] or before['dirty']:
                raise ValueError('Prior tab changed.')
            connection.call('Target.activateTarget', {'targetId': state['previous_tab'].removeprefix('tab:')})
            wait_selected(connection, state['previous_tab'])
        else: raise ValueError('Unsupported browser inverse.')


def recover_pending(state):
    if type(state.get('pid')) is int and subprocess_absent(state['pid'], state['creation_time']):
        return
    path = Path(state['profile']) / ('operation-' + state['operation'] + '.json')
    with files._open(path):
        if path.stat().st_size > 512: raise ValueError('Interrupted tab receipt exceeds the bound.')
        receipt = json.loads(path.read_text(encoding='utf-8'))
    from pluma.tools.browser import TabArgs
    TabArgs(session_id=state['session_id'], tab_id=receipt['tab_id'])
    with connect(state) as connection:
        if not any(item['tab_id'] == receipt['tab_id'] for item in tabs(connection)): return
        current = observation(connection, receipt['tab_id'])
        if current['url'] != 'about:blank' or current['dirty']:
            raise ValueError('Interrupted navigation has no verified final inverse guard.')
        close(connection, receipt['tab_id'], state)


def restored(state):
    if state['action'] == 'browser_tab': return tab_absent(state)
    if subprocess_absent(state['pid'], state['creation_time']): return False
    with connect(state) as connection:
        return selected(connection) == state['previous_tab']


def download_status(state, limit):
    # Chromium records download state in its own profile database. A filename
    # without .crdownload is not sufficient evidence of completion.
    path = Path(state['profile']) / 'Default/History'
    with ExitStack() as held:
        # Original session ownership persists after its browser exits. Chromium
        # can keep History locked/unflushed while live; do not claim an empty
        # database is an authoritative live download inventory.
        if not subprocess_absent(state['pid'], state['creation_time']):
            held.enter_context(connect(state))
        else:
            for parent in reversed(Path(state['profile']).parents): held.enter_context(files._open(parent, parent=True))
            held.enter_context(files._open(Path(state['profile']), parent=True))
            if profile_identity(state['profile']) != state['profile_identity']: raise ValueError('Owned profile changed.')
        held.enter_context(files._open(path.parent, parent=True))
        c, w, kernel = files._api()
        handle = kernel.CreateFileW(str(path), 0x80, 3, None, 3, 0x02200000, None)
        if handle == c.c_void_p(-1).value: raise c.WinError()
        held.callback(kernel.CloseHandle, handle)
        if files._metadata(handle)['kind'] != 'file': raise ValueError('A regular private History database is required.')
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
            deadline = time.monotonic() + .3
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 100)
            rows = db.execute('SELECT id,state,received_bytes,total_bytes,target_path FROM downloads ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    result = []
    for ident, state_code, received, total, target in rows:
        confirmed = False
        if state_code == 1:
            candidate = Path(target)
            # Only PLUMA's configured download directory can be inspected.
            if candidate.parent == Path(state['profile']) / 'Downloads':
                with files._open(candidate) as handle:
                    info = files._metadata(handle)
                    confirmed = info['kind'] == 'file' and info['size_bytes'] == received == total
        result.append({'download_id': ident, 'state': 'complete' if confirmed else
            'unverified' if state_code == 1 else 'in_progress' if state_code == 0 else 'interrupted',
            'received_bytes': received, 'total_bytes': total})
    return result
