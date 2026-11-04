"""Private owned-worker streaming, not native capture/OCR acceptance."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time

import pytest
from tests.unit.test_ipc_request_contract import resident_fixture
from tests.unit.test_p23_perception_readback import prepared, query, ReceiptArgs, verify_fixture


class LiveArgs(ReceiptArgs):
    release_file: str


def publish_and_wait(args, context):
    from pluma.tools.base import ToolResult
    snapshot = context.snapshot_registry.resolve(args['snapshot_id'])
    context.publish_perception(args['receipt'], snapshot.model_dump(mode='json', exclude={'image_ref','is_expired'}))
    while not Path(args['release_file']).exists():
        context.cancellation_token.raise_if_cancelled()
        time.sleep(.01)
    return ToolResult.success('capture_target_window', data={'snapshot_id':snapshot.snapshot_id},
        factual_message='Owned streaming fixture only.', verified=True)


def test_live_worker_observation_arrives_before_result_and_stop_clears_it(resident_fixture, tmp_path):
    from pluma.tools.registry import ToolRegistry
    from pluma.tools.base import ToolSpec, RiskClass
    from pluma.memory.activity import ActivityQuery
    core, ledger, supervisor, cap, snap, receipt = prepared(resident_fixture)
    registry = ToolRegistry()
    registry.register(ToolSpec(name='capture_target_window', description='Owned live transport fixture.',
        args_schema=LiveArgs, risk_class=RiskClass.READ, executor=publish_and_wait,
        verifier=verify_fixture, process_isolated=True, timeout_s=5))
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            work = pool.submit(registry.execute, 'capture_target_window', dict(snapshot_id=snap.snapshot_id,
                receipt=receipt, release_file=str(tmp_path/'release')), cap, ledger)
            deadline = time.monotonic()+3
            frame = query(core)
            while not frame['observations'] and time.monotonic()<deadline and not work.done():
                time.sleep(.01); frame=query(core)
            assert frame['observations'], work.result() if work.done() else 'No live observation'
            assert not work.done() and ActivityQuery(ledger._db).actions_for_task(cap.task_id)==[]
            assert 'PRIVATE_' not in str(frame) and 'verified' not in frame['observations'][0]
            supervisor.stop_task(cap.task_id)
            assert query(core)['observations']==[]
            result=work.result(timeout=3)
            assert not result.ok
    finally:
        supervisor.stop_task(cap.task_id); assert supervisor.join_stop_operations(2); registry.close()
    assert any(e.kind=='worker' and e.verified and e.code=='WORKER_ABSENCE_VERIFIED' for e in cap.cleanup_evidence)


@pytest.mark.parametrize('fault',['hwnd','identity','element','snapshot','image'])
def test_live_receipts_remain_bound_to_admitted_target(resident_fixture,fault):
    _,_,supervisor,cap,snap,receipt=prepared(resident_fixture)
    raw=snap.model_dump(mode='json',exclude={'image_ref','is_expired'})
    if fault=='hwnd':raw['hwnd']+=1
    elif fault=='identity':raw['process_creation_time_ns']+=1
    elif fault=='element':raw['ocr_words']=[]
    elif fault=='snapshot':receipt['snapshot_id']='e79d37c5-be55-4c35-a32b-49bd6d6f852d'
    else:raw['image_ref']='never-retain-an-image'
    try:
        with pytest.raises(ValueError):cap.perception_feedback.publish_live(receipt,raw,cap,snap.model_dump())
        assert cap.perception_feedback.snapshot(cap) is None
    finally:supervisor.stop_task(cap.task_id)


def test_streamed_and_final_receipt_cannot_renew_original_observation(resident_fixture):
    _,_,supervisor,cap,snap,receipt=prepared(resident_fixture)
    try:
        cap.perception_feedback.publish_live(receipt,snap.model_dump(),cap,snap.model_dump())
        before=cap.perception_feedback.snapshot(cap); deadline=cap.perception_feedback._deadline
        cap.perception_feedback.publish(receipt,cap)
        assert cap.perception_feedback.snapshot(cap)==before and cap.perception_feedback._deadline==deadline
        supervisor.stop_task(cap.task_id)
        cap.perception_feedback.publish_live(receipt,snap.model_dump(),cap,None)
        assert cap.perception_feedback.snapshot(cap) is None
    finally:supervisor.stop_task(cap.task_id)


def test_fresh_reobservation_does_not_revive_an_expired_action_reference(resident_fixture):
    from datetime import datetime,timedelta,timezone
    from uuid import uuid4
    from pluma.perception.snapshot_registry import StaleSnapshotError
    _,_,supervisor,cap,snap,receipt=prepared(resident_fixture)
    old=snap.model_copy(update={'expires_at':datetime.now(timezone.utc)-timedelta(seconds=1)})
    cap.snapshot_registry._snapshots[snap.snapshot_id]=old
    new_id=str(uuid4())
    fresh=snap.model_copy(update={'snapshot_id':new_id,'ocr_words':[]})
    receipt.update(snapshot_id=new_id,match_state='NOT_REQUESTED',match=None)
    try:
        cap.perception_feedback.publish_live(receipt,fresh.model_dump(),cap,old.model_dump())
        assert cap.perception_feedback.snapshot(cap).snapshot_id==new_id
        with pytest.raises(StaleSnapshotError):cap.snapshot_registry.resolve(old.snapshot_id)
        cap.snapshot_registry.clear()
        assert cap.perception_feedback.snapshot(cap) is None
    finally:supervisor.stop_task(cap.task_id)


def test_model_preparation_precedes_fresh_snapshot_and_pixel_capture(resident_fixture,monkeypatch):
    from types import SimpleNamespace
    from pluma.tools import screen_catalog as tools
    from pluma.perception.ocr_adapter import OcrResult
    _,_,supervisor,cap,snap,_=prepared(resident_fixture)
    phases=[]
    def prepare(cancellation_token=None):phases.append('ready')
    def snapshot(**kwargs):
        assert phases==['ready'];phases.append('snapshot');return snap
    def capture(hwnd):
        assert phases==['ready','snapshot'];phases.append('pixels');return b'Owned ephemeral image fixture'
    def recognize(image,cancellation_token=None):
        assert phases==['ready','snapshot','pixels'];phases.append('recognize');return OcrResult(words=[])
    monkeypatch.setattr('pluma.perception.ocr_lifecycle.get_default_ocr_lifecycle_manager',lambda:
        SimpleNamespace(prepare=prepare,run_ocr=recognize))
    monkeypatch.setattr(tools,'UiaSnapshotBuilder',lambda **kwargs:SimpleNamespace(capture=snapshot))
    monkeypatch.setattr('pluma.perception.capture.WindowCapture',lambda:SimpleNamespace(capture_window=capture))
    monkeypatch.setattr(tools,'_check_window',lambda *args,**kwargs:None)
    try:
        tools._new_snapshot(snap.hwnd,include_ocr=True,region=None,task_context=cap)
        assert phases==['ready','snapshot','pixels','recognize']
    finally:supervisor.stop_task(cap.task_id)
