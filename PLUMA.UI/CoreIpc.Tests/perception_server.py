"""Owned disposable-host target and real screen tools for P23 native acceptance.

Routing and readiness are fixture controls, not health/planner acceptance.
Capture, OCR, worker/Job, typed IPC, verification and cleanup are production.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import ctypes as c
from ctypes import wintypes as w
import json
import threading
import time
from types import SimpleNamespace


class PerceptionFixture:
    def __init__(self, core, registry, supervisor, ledger, root):
        from pluma.tools.screen_catalog import CAPTURE_TARGET_WINDOW_SPEC, FIND_VISIBLE_TEXT_SPEC
        from tests.fixtures.uia_semantic_target import main
        self.core=core; self.registry=registry; self.supervisor=supervisor; self.ledger=ledger; self.root=root
        self.release=threading.Event(); self.ready=root/'perception-target.json'; self.errors=[]
        self.disconnected=False
        def target():
            try:main(self.ready)
            except BaseException as error:self.errors.append(type(error).__name__)
        self.thread=threading.Thread(target=target,name='OwnedP23Target');self.thread.start()
        deadline=time.monotonic()+5
        while not self.ready.exists() and not self.errors and time.monotonic()<deadline:time.sleep(.01)
        if not self.ready.exists():raise RuntimeError('Owned P23 target failed to start.')
        self.identity=json.loads(self.ready.read_text())
        self.hwnd=self.identity['hwnd']
        for spec in (CAPTURE_TARGET_WINDOW_SPEC,FIND_VISIBLE_TEXT_SPEC):registry.register(spec)
        self.calls=[]

    def execute(self, request, capsule):
        from pluma.core.task_supervisor import TaskState
        from pluma.perception.context import ActiveWindowContext
        from pluma.perception.element_refs import ScreenSnapshot
        from pluma.memory.activity import ActivityQuery
        self.supervisor.start_task(capsule.task_id)
        if request.text not in ('fixture:capture','fixture:capture_short','fixture:region','fixture:match'):
            raise ValueError('Only exact owned P23 fixture requests are accepted.')
        context=ActiveWindowContext(); info=context.get_window_info(self.hwnd)
        if not info.is_valid or context.get_active_window().hwnd!=self.hwnd:raise RuntimeError('Owned target is not foreground.')
        now=datetime.now(timezone.utc)
        snapshot=ScreenSnapshot(created_at=now,expires_at=now+timedelta(seconds=3),hwnd=self.hwnd,pid=info.pid,
            active_process=info.process_name,active_window_title=info.window_title,window_rect=info.rect,
            dpi_scale=info.dpi_scale,window_class=info.class_name,process_creation_time_ns=context.get_process_creation_time_ns(info.pid))
        capsule.snapshot_registry.register(snapshot)
        args={'snapshot_id':snapshot.snapshot_id}
        tool='capture_target_window'
        if request.text=='fixture:region':args['region']=dict(left=20,top=40,right=260,bottom=220)
        if request.text=='fixture:match':
            tool='find_visible_text';args.update(visible_text_query='Submit',min_confidence=.6,exact_match=True)
        self.release.clear()
        result=self.registry.execute(tool,args,capsule,self.ledger)
        self.calls.append((capsule.task_id,result.ok,result.verified))
        rows=ActivityQuery(self.ledger._db).actions_for_task(capsule.task_id)
        if not result.ok or not result.verified or len(rows)!=1 or not rows[0]['verified']:
            raise RuntimeError('Native P23 screen tool/ledger verification failed: '+str(result.error_code))
        if tool=='find_visible_text' and result.data.get('match_count')!=1:
            raise RuntimeError('Actual OCR did not produce a unique Submit match.')
        # An explicit owned waiting step permits observing feedback and priority
        # STOP; it is not a production sleep or an extended observation lifetime.
        deadline=time.monotonic()+5
        while request.text!='fixture:capture_short' and not self.release.is_set() and time.monotonic()<deadline:
            capsule.cancellation_token.raise_if_cancelled();time.sleep(.01)
        capsule.cancellation_token.raise_if_cancelled()
        self.supervisor.finalize_task(capsule.task_id,TaskState.SUCCEEDED)
        return SimpleNamespace(final_state=TaskState.SUCCEEDED,completion_verified=True,
            terminal_persisted=True,has_residual=False,route=SimpleNamespace(value='FAST'),
            user_message='Owned native perception fixture verified.',duration_ms=0)

    def control(self,command):
        user=c.WinDLL('user32',use_last_error=True)
        user.SetWindowPos.argtypes=[w.HWND,w.HWND,c.c_int,c.c_int,c.c_int,c.c_int,w.UINT]
        user.ShowWindow.argtypes=[w.HWND,c.c_int]
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        if command=='perception_release':self.release.set()
        elif command=='perception_move':
            from pluma.adapters.window_geometry import _window_coordinates
            with _window_coordinates(self.hwnd) as (ct,wt,api):
                rect=wt.RECT();assert api.GetWindowRect(wt.HWND(self.hwnd),ct.byref(rect))
                assert api.SetWindowPos(wt.HWND(self.hwnd),None,rect.left+17,rect.top+19,0,0,0x15)
        elif command=='perception_hide':user.ShowWindow(self.hwnd,0)
        elif command=='perception_show':user.ShowWindow(self.hwnd,4)
        elif command=='perception_disconnect':self.disconnected=True
        elif command=='perception_reconnect':self.disconnected=False
        elif command=='perception_close':user.PostMessageW(self.hwnd,0x10,0,0)
        elif command=='perception_assert_cleanup':
            from pluma.core.ownership import subprocess_absent
            for cap in self.supervisor._tasks.values():
                worker=getattr(cap,'worker_controller',None)
                if worker is not None and not worker.verify_cleanup():raise RuntimeError('Owned worker remains.')
                proofs=[item for item in cap.cleanup_evidence if item.kind=='worker' and item.code=='WORKER_ABSENCE_VERIFIED' and item.verified]
                if not cap.terminal_ready.is_set() or cap.terminal_persisted is not True or not proofs:
                    raise RuntimeError('Owned task cleanup/persistence proof is missing.')
                for proof in proofs:
                    if not subprocess_absent(proof.identity['pid'],proof.identity['creation_time']):
                        raise RuntimeError('Native readback found an owned worker still present.')
            if self.errors:raise RuntimeError('Owned target pump failed.')
        else:raise ValueError('Unsupported P23 fixture control.')

    def close(self):
        self.release.set()
        user=c.WinDLL('user32',use_last_error=True)
        user.GetWindowThreadProcessId.argtypes=[w.HWND,c.POINTER(w.DWORD)]
        user.PostMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        for key in ('hwnd','duplicate_hwnd','textless_hwnd'):
            hwnd=self.identity[key];pid=w.DWORD()
            if user.GetWindowThreadProcessId(hwnd,c.byref(pid)) and pid.value==self.identity['pid']:
                user.PostMessageW(hwnd,0x10,0,0)
        self.thread.join(3)
        if self.thread.is_alive() or self.errors:raise RuntimeError('Owned target/window cleanup failed.')
        self.ready.unlink()
