"""Read-only C# native identity/geometry checks against an owned isolated window.

No foreground activation or personal window access. Presentation eligibility is
covered separately by deterministic C# task/clock/probe cases, not claimed here.
"""
import ctypes
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime,timedelta,timezone
from uuid import uuid4

from tests.windows.test_p12_uia_semantic_controls import owned_uia_window
from tests.fixtures.desktop_thread import desktop_thread


@desktop_thread
def test_native_presentation_probe_reads_owned_target_and_refuses_hidden(owned_uia_window):
    from pluma.core.ownership import get_process_creation_time
    from pluma.perception.context import ActiveWindowContext
    hwnd = owned_uia_window['hwnd']
    context = ActiveWindowContext()
    expected = context.get_window_info(hwnd)
    dll = Path('PLUMA.UI/CoreIpc.Tests/bin/Release/net8.0-windows/CoreIpc.Tests.dll').resolve()
    assert dll.is_file(), 'Build the declared CoreIpc.Tests Release target before native acceptance.'

    def probe():
        # Bounded foreground-less managed test child; no child processes are created.
        result = subprocess.run(['dotnet', str(dll), '--perception-probe', str(hwnd)],
            capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    actual = probe()
    assert actual is not None
    assert actual['Hwnd'] == hwnd and actual['Pid'] == owned_uia_window['pid']
    assert actual['CreationTime'] == get_process_creation_time(expected.pid)
    assert actual['WindowClass'] == expected.class_name and actual['DpiScale'] == expected.dpi_scale
    assert actual['Bounds'] == dict(Left=expected.rect.left, Top=expected.rect.top,
        Right=expected.rect.right, Bottom=expected.rect.bottom)
    assert actual['TitleHash'] == 'sha256:' + hashlib.sha256(expected.window_title.encode()).hexdigest()
    assert expected.window_title not in json.dumps(actual)
    now=datetime.now(timezone.utc)
    id=lambda:str(uuid4())
    observation=dict(task_id=id(),task_request_id=id(),sequence=1,observation_id=id(),snapshot_id=id(),
        hwnd=hwnd,pid=actual['Pid'],creation_time=actual['CreationTime'],window_class=actual['WindowClass'],
        title_hash=actual['TitleHash'],window_bounds={k.lower():v for k,v in actual['Bounds'].items()},
        dpi_scale=actual['DpiScale'],region=dict(left=10,top=20,right=200,bottom=120),
        observed_utc=now.isoformat(),expires_utc=(now+timedelta(seconds=3)).isoformat(),match_state='UNIQUE',
        match=dict(element_id=id(),bounds=dict(left=30,top=40,right=90,bottom=70),confidence=.97),requires_target_revalidation=True)
    frame=dict(protocol_version=1,message_type='perception_snapshot',request_id=id(),observations=[observation])
    mapped=subprocess.run(['dotnet',str(dll),'--perception-map'],input=json.dumps(frame),
        capture_output=True,text=True,timeout=15,creationflags=subprocess.CREATE_NO_WINDOW)
    assert mapped.returncode==0,mapped.stderr
    placement=json.loads(mapped.stdout)
    from ctypes import wintypes as w
    native=ctypes.WinDLL('user32',use_last_error=True)
    native.LogicalToPhysicalPointForPerMonitorDPI.argtypes=[w.HWND,ctypes.POINTER(w.POINT)]
    def physical(x,y):
        point=w.POINT(expected.rect.left+x,expected.rect.top+y)
        assert native.LogicalToPhysicalPointForPerMonitorDPI(hwnd,ctypes.byref(point))
        return point
    origin,end,start,finish=[physical(*p) for p in [(10,20),(200,120),(30,40),(90,70)]]
    assert placement['DesktopX']==origin.x and placement['DesktopY']==origin.y
    assert placement['Width']==end.x-origin.x and placement['Height']==end.y-origin.y
    assert placement['MatchX']==start.x-origin.x and placement['MatchY']==start.y-origin.y
    assert placement['MatchWidth']==finish.x-start.x and placement['MatchHeight']==finish.y-start.y
    assert placement['Confidence']==.97
    # Mutate only this positively identified owned fixture, in its own DPI space.
    from pluma.adapters.window_geometry import _window_coordinates
    with _window_coordinates(hwnd) as (c, w, api):
        assert api.SetWindowPos(w.HWND(hwnd), None, expected.rect.left + 17, expected.rect.top + 19,
            0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE | NOZORDER | NOACTIVATE
    moved = probe()
    assert moved['Bounds']['Left'] == expected.rect.left + 17
    assert moved['Bounds']['Top'] == expected.rect.top + 19
    assert moved['CreationTime'] == actual['CreationTime'] and moved['Bounds'] != actual['Bounds']
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.SetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    assert user.SetWindowTextW(hwnd, 'Owned P23 renamed target')
    renamed = probe()
    assert renamed['TitleHash'] == 'sha256:' + hashlib.sha256(b'Owned P23 renamed target').hexdigest()
    assert renamed['TitleHash'] != actual['TitleHash']
    user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user.ShowWindow(hwnd, 0)  # This exact fixture HWND only, never a user window.
    assert not user.IsWindowVisible(hwnd)
    assert probe() is None
