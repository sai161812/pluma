"""Actual target-only capture and PaddleOCR/ONNX worker observation.

Foreground selection alone is bound to the owned HWND; no personal focus changes.
Combined real foreground/native rendering acceptance runs on the disposable host.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import time
from uuid import uuid4

from tests.fixtures.desktop_thread import desktop_thread
from tests.windows.test_p12_uia_semantic_controls import owned_uia_window
from tests.unit.test_ipc_request_contract import resident_fixture


@desktop_thread
def test_owned_native_ocr_emits_actual_match_without_persisting_image(owned_uia_window,resident_fixture,tmp_path):
    from pluma.perception.context import ActiveWindowContext
    from pluma.perception.element_refs import ScreenSnapshot
    from pluma.memory.activity import TaskRecord,ActivityQuery
    from pluma.tools.registry import ToolRegistry
    from pluma.tools.screen_catalog import FIND_VISIBLE_TEXT_SPEC
    from tests.fixtures.perception_feedback_capture import native_find
    core,ledger,supervisor=resident_fixture
    context=ActiveWindowContext(); info=context.get_window_info(owned_uia_window['hwnd']); now=datetime.now(timezone.utc)
    snap=ScreenSnapshot(created_at=now,expires_at=now+timedelta(seconds=3),hwnd=info.hwnd,pid=info.pid,
        active_process=info.process_name,active_window_title=info.window_title,window_rect=info.rect,dpi_scale=info.dpi_scale,
        window_class=info.class_name,process_creation_time_ns=context.get_process_creation_time_ns(info.pid))
    cap=supervisor.create_task(str(uuid4()));ledger.insert_task(TaskRecord(cap.task_id,cap.request_id,'TEXT','Owned native OCR feedback'))
    supervisor.start_task(cap.task_id);cap.snapshot_registry.register(snap)
    registry=ToolRegistry();registry.register(FIND_VISIBLE_TEXT_SPEC.model_copy(update={'executor':native_find}))
    frames=[]
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending=pool.submit(registry.execute,'find_visible_text',dict(snapshot_id=snap.snapshot_id,
                visible_text_query='Submit',min_confidence=.6,exact_match=True),cap,ledger)
            end=time.monotonic()+15
            while not pending.done() and time.monotonic()<end:
                frame=core.handle_ipc_command(dict(protocol_version=1,message_type='perception_query',request_id=str(uuid4())))
                frames.extend(frame.get('observations',[]));time.sleep(.02)
            result=pending.result(timeout=1)
        assert result.ok and result.verified,result
        final=core.handle_ipc_command(dict(protocol_version=1,message_type='perception_query',request_id=str(uuid4())))
        frames.extend(final['observations'])
        matches=[frame for frame in frames if frame['match_state']=='UNIQUE']
        assert matches and matches[-1]['match']['confidence']>=.6,(result,frames)
        assert matches[-1]['hwnd']==info.hwnd and result.data['match_count']==1
        assert any(frame['match_state']=='NOT_REQUESTED' for frame in frames)
        assert ActivityQuery(ledger._db).actions_for_task(cap.task_id)[0]['verified']
        assert not list(tmp_path.rglob('*.bmp')) and not list(tmp_path.rglob('*.png'))
    finally:
        supervisor.stop_task(cap.task_id);assert supervisor.join_stop_operations(2);registry.close()
    assert any(e.kind=='worker' and e.verified and e.code=='WORKER_ABSENCE_VERIFIED' for e in cap.cleanup_evidence)
