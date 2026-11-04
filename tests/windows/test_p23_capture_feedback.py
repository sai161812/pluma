"""Real owned window capture/worker/readback, with target-bound foreground seam."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json

from tests.windows.test_p12_uia_semantic_controls import owned_uia_window
from tests.fixtures.desktop_thread import desktop_thread
from tests.unit.test_ipc_request_contract import resident_fixture


@desktop_thread
def test_native_owned_capture_reaches_typed_readback(owned_uia_window,resident_fixture,tmp_path):
    from pluma.core.ownership import get_process_creation_time
    from pluma.memory.activity import TaskRecord,ActivityQuery
    from pluma.perception.context import ActiveWindowContext
    from pluma.perception.element_refs import ScreenSnapshot
    from pluma.tools.registry import ToolRegistry
    from pluma.tools.screen_catalog import CAPTURE_TARGET_WINDOW_SPEC
    from tests.fixtures.perception_feedback_capture import native_capture
    core,ledger,supervisor=resident_fixture
    hwnd=owned_uia_window['hwnd'];desktop=ActiveWindowContext();info=desktop.get_window_info(hwnd)
    assert info.is_valid and info.pid==owned_uia_window['pid']
    now=datetime.now(timezone.utc)
    snap=ScreenSnapshot(created_at=now,expires_at=now+timedelta(seconds=3),active_process=info.process_name,
        active_window_title=info.window_title,window_rect=info.rect,dpi_scale=info.dpi_scale,
        hwnd=hwnd,pid=info.pid,window_class=info.class_name,process_creation_time_ns=desktop.get_process_creation_time_ns(info.pid))
    cap=supervisor.create_task(str(uuid4()));ledger.insert_task(TaskRecord(cap.task_id,cap.request_id,'TEXT','Owned native feedback fixture'))
    supervisor.start_task(cap.task_id);cap.snapshot_registry.register(snap)
    registry=ToolRegistry();registry.register(CAPTURE_TARGET_WINDOW_SPEC.model_copy(update={'executor':native_capture}))
    try:
        result=registry.execute('capture_target_window',{'snapshot_id':snap.snapshot_id},cap,ledger)
        assert result.ok and result.verified and result.data['byte_count']>54,result
        frame=core.handle_ipc_command(dict(protocol_version=1,message_type='perception_query',request_id=str(uuid4())))
        assert len(frame['observations'])==1,frame
        observed=frame['observations'][0]
        assert observed['hwnd']==hwnd and observed['pid']==info.pid and observed['creation_time']==get_process_creation_time(info.pid)
        assert observed['window_bounds']==info.rect.model_dump() and observed['requires_target_revalidation']
        rows=ActivityQuery(ledger._db).actions_for_task(cap.task_id)
        assert len(rows)==1 and rows[0]['verified'] and 'perception_receipt' not in rows[0]['result_json']
        assert 'image_ref' not in json.dumps(frame) and info.window_title not in json.dumps(frame)
        assert not list(tmp_path.rglob('*.bmp')) and not list(tmp_path.rglob('*.png'))
    finally:supervisor.stop_task(cap.task_id);registry.close()
    assert any(e.kind=='worker' and e.verified and e.code=='WORKER_ABSENCE_VERIFIED' for e in cap.cleanup_evidence)
