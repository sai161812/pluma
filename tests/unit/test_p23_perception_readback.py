"""P23 metadata bridge; injected desktop data is never native acceptance."""
from pluma.perception.element_refs import BoundingBox
from tests.unit.test_screen_control_catalog import _screen_context
from tests.unit.test_ipc_request_contract import resident_fixture
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json,time
import pytest


def query(core,**extra):
    payload=dict(protocol_version=1,message_type='perception_query',request_id=str(uuid4()));payload.update(extra)
    return core.handle_ipc_command(payload)


def prepared(resident_fixture):
    from pluma.memory.activity import TaskRecord
    from pluma.perception.element_refs import ScreenSnapshot,ScreenElement,ElementSource
    from pluma.perception.feedback import title_hash
    core,ledger,supervisor=resident_fixture
    cap=supervisor.create_task(str(uuid4()))
    ledger.insert_task(TaskRecord(cap.task_id,cap.request_id,'TEXT','Owned metadata fixture'))
    supervisor.start_task(cap.task_id)
    now=datetime.now(timezone.utc)
    sid=str(uuid4())
    element=ScreenElement(snapshot_id=sid,source=ElementSource.OCR,label='PRIVATE_OCR_TEXT',
        bounds=BoundingBox(left=10,top=20,right=50,bottom=40),confidence=.97)
    snap=ScreenSnapshot(snapshot_id=sid,created_at=now,expires_at=now+timedelta(seconds=3),
        active_process='owned.exe',active_window_title='PRIVATE_WINDOW_TITLE',
        window_rect=BoundingBox(left=-100,top=20,right=100,bottom=120),dpi_scale=1.25,
        hwnd=100,pid=200,process_creation_time_ns=300,window_class='OwnedClass',ocr_words=[element])
    cap.snapshot_registry.register(snap)
    receipt=dict(observation_id=str(uuid4()),snapshot_id=sid,hwnd=100,pid=200,creation_time=400,
        window_class='OwnedClass',title_hash=title_hash(snap.active_window_title),window_bounds=snap.window_rect.model_dump(),
        dpi_scale=1.25,region=dict(left=0,top=0,right=200,bottom=100),observed_utc=now.isoformat(),
        expires_utc=(now+timedelta(seconds=3)).isoformat(),match_state='UNIQUE',
        match=dict(element_id=element.element_id,bounds=element.bounds.model_dump(),confidence=.97),requires_target_revalidation=True)
    return core,ledger,supervisor,cap,snap,receipt


def test_readback_is_bounded_metadata_not_capture_or_action_authority(resident_fixture,monkeypatch):
    core,_,supervisor,cap,snap,receipt=prepared(resident_fixture)
    monkeypatch.setattr('pluma.perception.capture.WindowCapture',lambda:pytest.fail('Readback must not capture.'))
    cap.perception_feedback.publish(receipt,cap)
    frame=query(core)
    assert frame['message_type']=='perception_snapshot' and len(frame['observations'])==1
    item=frame['observations'][0]
    assert item['task_id']==cap.task_id and item['match']['confidence']==.97 and item['window_bounds']['left']==-100
    assert item['requires_target_revalidation'] is True and 'verified' not in item and 'success' not in item
    assert 'PRIVATE_' not in json.dumps(frame) and 'image_ref' not in json.dumps(frame)
    assert query(core)['observations'][0]['expires_utc']==item['expires_utc']
    cap.perception_feedback._deadline=time.monotonic()-1
    assert query(core)['observations']==[]
    supervisor.stop_task(cap.task_id)


@pytest.mark.parametrize('extra',[{'capture':True},{'request_id':'bad'},{'task_id':str(uuid4())}])
def test_query_cannot_submit_targets_or_capture(resident_fixture,extra):
    core,_,_=resident_fixture
    assert query(core,**extra)['error_code']=='INVALID_REQUEST'


@pytest.mark.parametrize('fault',['bool_pid','outside','ambiguous','confidence','foreign_element','wrong_hwnd','revalidation','bytes'])
def test_invalid_or_cross_target_receipt_is_refused(resident_fixture,fault):
    _,_,supervisor,cap,_,receipt=prepared(resident_fixture)
    if fault=='bool_pid':receipt['pid']=True
    elif fault=='outside':receipt['match']['bounds']['right']=201
    elif fault=='ambiguous':receipt['match_state']='AMBIGUOUS'
    elif fault=='confidence':receipt['match']['confidence']=float('nan')
    elif fault=='foreign_element':receipt['match']['element_id']=str(uuid4())
    elif fault=='wrong_hwnd':receipt['hwnd']=101
    elif fault=='revalidation':receipt['requires_target_revalidation']=False
    else:receipt['image']=b'PRIVATE_IMAGE'
    with pytest.raises(Exception):cap.perception_feedback.publish(receipt,cap)
    assert cap.perception_feedback.snapshot(cap) is None
    supervisor.stop_task(cap.task_id)


from pydantic import BaseModel
class ReceiptArgs(BaseModel):
    snapshot_id:str
    receipt:dict
    fail:bool=False


def emit_fixture_receipt(args,context):
    from pluma.tools.base import ToolResult
    if args['fail']:return ToolResult.failure('capture_target_window','Explicit owned fixture failure.')
    return ToolResult.success('capture_target_window',data={'snapshot_id':args['snapshot_id'],'captured':True},
        factual_message='Fixture receipt, not native capture acceptance.',verified=True).model_copy(
            update={'private_context':{'perception_receipt':args['receipt']}})


def verify_fixture(result):
    from pluma.tools.base import VerifyResult
    return VerifyResult(ok=result.ok,method='fixture_receipt',detail='Transport fixture only.')


def test_real_worker_transport_publishes_only_verified_same_task_metadata(resident_fixture):
    from pluma.tools.registry import ToolRegistry
    from pluma.tools.base import ToolSpec,RiskClass
    core,ledger,supervisor,cap,_,receipt=prepared(resident_fixture)
    registry=ToolRegistry()
    registry.register(ToolSpec(name='capture_target_window',description='Owned receipt transport fixture.',args_schema=ReceiptArgs,
        risk_class=RiskClass.READ,executor=emit_fixture_receipt,verifier=verify_fixture,process_isolated=True,timeout_s=5))
    try:
        args=dict(snapshot_id=receipt['snapshot_id'],receipt=receipt)
        result=registry.execute('capture_target_window',args,cap,ledger)
        assert result.ok and 'perception_receipt' not in result.model_dump_json()
        assert query(core)['observations'][0]['task_id']==cap.task_id
        failed=registry.execute('capture_target_window',dict(args,fail=True),cap,ledger)
        assert not failed.ok and query(core)['observations']==[]
    finally:
        supervisor.stop_task(cap.task_id);registry.close()
    assert any(e.kind=='worker' and e.verified and e.code=='WORKER_ABSENCE_VERIFIED' for e in cap.cleanup_evidence)


def test_failed_history_does_not_publish_observation(resident_fixture):
    from pluma.tools.registry import ToolRegistry
    from pluma.tools.base import ToolSpec,RiskClass
    core,ledger,supervisor,cap,_,receipt=prepared(resident_fixture)
    class UnavailableLedger:
        _db=ledger._db
        def insert_action(self,*args,**kwargs):raise OSError('Owned fixture history fault')
    registry=ToolRegistry()
    registry.register(ToolSpec(name='capture_target_window',description='Owned receipt transport fixture.',args_schema=ReceiptArgs,
        risk_class=RiskClass.READ,executor=emit_fixture_receipt,verifier=verify_fixture,process_isolated=True,timeout_s=5))
    try:
        result=registry.execute('capture_target_window',dict(snapshot_id=receipt['snapshot_id'],receipt=receipt),cap,UnavailableLedger())
        assert not result.ok and query(core)['observations']==[]
    finally:supervisor.stop_task(cap.task_id);registry.close()


def test_registry_busy_does_not_block_priority_stop(resident_fixture):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    core,_,supervisor,cap,_,receipt=prepared(resident_fixture)
    cap.perception_feedback.publish(receipt,cap)
    entered=threading.Event();release=threading.Event()
    registry=cap.snapshot_registry
    def hold():
        with registry._lock:entered.set();assert release.wait(3)
    with ThreadPoolExecutor(1) as pool:
        held=pool.submit(hold)
        try:
            assert entered.wait(1)
            start=time.monotonic()
            assert query(core)['error_code']=='PERCEPTION_UNAVAILABLE' and time.monotonic()-start<.3
            ack=core.handle_ipc_command(dict(protocol_version=1,message_type='stop',request_id=str(uuid4()),task_id=cap.task_id))
            assert cap.stop_latch_set and ack['message_type']=='stop_ack'
        finally:release.set();held.result(2)
    assert supervisor.join_stop_operations(2)
    supervisor.stop_task(cap.task_id)


def test_stop_terminal_and_cleared_snapshot_revoke_feedback(resident_fixture):
    from pluma.core.task_supervisor import TaskState
    core,_,supervisor,cap,_,receipt=prepared(resident_fixture)
    cap.perception_feedback.publish(receipt,cap)
    cap.snapshot_registry.clear()
    assert query(core)['observations']==[]
    supervisor.finalize_task(cap.task_id,TaskState.SUCCEEDED)
    assert query(core)['observations']==[] and cap.perception_feedback._item is None
    core,_,supervisor,cap,_,receipt=prepared(resident_fixture)
    cap.perception_feedback.publish(receipt,cap);cap.cancellation_token.cancel()
    assert query(core)['observations']==[]
    supervisor.stop_task(cap.task_id)


def test_capture_movement_during_readback_is_not_reported_as_current(monkeypatch):
    from pluma.tools import screen_catalog
    context,snapshot,_,desktop=_screen_context()
    monkeypatch.setattr(screen_catalog,'ActiveWindowContext',lambda:desktop)
    class MovingCapture:
        def capture_window(self,hwnd):
            info=desktop.get_active_window()
            info.rect=BoundingBox(left=101,top=100,right=501,bottom=400)
            return b'BM'+b'owned fixture bytes'
    monkeypatch.setattr('pluma.perception.capture.WindowCapture',MovingCapture)
    result=screen_catalog.execute_capture_target_window({'snapshot_id':snapshot.snapshot_id},context)
    assert not result.ok and result.error_code=='CAPTURE_FAILED'


@pytest.mark.parametrize('count,state',[(0,'NONE'),(1,'UNIQUE'),(2,'AMBIGUOUS')])
def test_real_ocr_selection_publishes_only_unique_match_geometry(resident_fixture,monkeypatch,count,state):
    from pluma.tools import screen_catalog
    from pluma.perception.context import ActiveWindowInfo
    from pluma.perception.element_refs import ScreenElement
    from pluma.perception.ocr_adapter import OcrResult,OcrWord
    _,_,supervisor,cap,snap,_=prepared(resident_fixture)
    element=snap.ocr_words[0]
    elements=[element.model_copy(update={'element_id':str(uuid4())}) for _ in range(count)]
    updated=snap.model_copy(update={'snapshot_id':str(uuid4())})
    updated=updated.model_copy(update={'ocr_words':[e.model_copy(update={'snapshot_id':updated.snapshot_id}) for e in elements]})
    ocr=OcrResult(words=[OcrWord(e.label,e.confidence,e.bounds) for e in elements])
    info=ActiveWindowInfo(hwnd=snap.hwnd,pid=snap.pid,process_name=snap.active_process,
        window_title=snap.active_window_title,rect=snap.window_rect,dpi_scale=snap.dpi_scale,is_valid=True,class_name=snap.window_class)
    class Desktop:
        def get_active_window(self):return info
        def get_process_creation_time_ns(self,pid):return snap.process_creation_time_ns
    monkeypatch.setattr(screen_catalog,'ActiveWindowContext',Desktop)
    monkeypatch.setattr(screen_catalog,'_new_snapshot',lambda *a,**k:(updated,ocr))
    monkeypatch.setattr('pluma.core.ownership.get_process_creation_time',lambda pid:400)
    result=screen_catalog.execute_find_visible_text(dict(snapshot_id=snap.snapshot_id,
        visible_text_query=element.label,min_confidence=.5,exact_match=True),cap)
    assert result.ok
    receipt=result.private_context['perception_receipt']
    assert receipt['match_state']==state and (receipt['match'] is not None)==(count==1)
    assert 'PRIVATE_' not in json.dumps(receipt)
    supervisor.stop_task(cap.task_id)
