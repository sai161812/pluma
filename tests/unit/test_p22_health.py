"""Private graph/storage/IPC and explicit fixture probes; no personal device use."""
from pathlib import Path
import json,time,uuid
import pytest

from pluma.core.host import CoreHost
from pluma.config.paths import PlumaPaths
from pluma.core.resident import ResidentCore
from pluma.tools.base import ToolResult,VerifyResult
from pluma.ui.confirmations import CallbackConfirmationContract,ConfirmationResponse


def fixture_setup(args,context):
    return ToolResult.success('check_setup',data={'checks':[{'id':name,'state':'PASSED','code':'FIXTURE_ONLY','origin':'fixture'}
        for name in ('planner','speech','ocr','uia','microphone')],'fingerprint':context.execution_binding['fingerprint']},
        adapter_used='fixture_setup',factual_message='Fixture checks; not native readiness.')


def fixture_verify(result):return VerifyResult(ok=True,method='fixture_only',detail='Not native acceptance.')


@pytest.fixture
def host(tmp_path,monkeypatch):
    def inert_start(core):core._running=True
    monkeypatch.setattr(ResidentCore,'start',inert_start)
    paths=PlumaPaths(tmp_path/'local',tmp_path/'roaming');paths.ensure_directories()
    value=CoreHost(paths,address='\\\\.\\pipe\\p22-'+uuid.uuid4().hex)
    value.start()
    value.runtime.policy_engine.confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=True))
    yield value
    assert value.close()


def request(host,kind,**fields):
    return host.handle({'protocol_version':1,'message_type':kind,'request_id':str(uuid.uuid4()),**fields})


def terminal(host,ack):
    assert ack.get('accepted'),ack
    end=time.monotonic()+5
    while time.monotonic()<end:
        cap=host.runtime.supervisor.get_task(ack['task_id'])
        if cap.terminal_ready.is_set():return cap
        time.sleep(.01)
    pytest.fail('Owned health task did not reach terminal readback.')


def test_health_is_cold_and_setup_not_assumed(host):
    view=request(host,'health_query')
    assert view['state']=='READY' and view['checks']==[] and not view['setup_ready'] and not view['native_verified']
    assert view['pid']==host.pid and view['creation_time']==host.creation_time
    assert host.runtime.llm_lifecycle.state.value==host.runtime.voice_lifecycle.state=='COLD'
    assert not host.runtime.tool_registry._worker_controllers


@pytest.mark.parametrize('fields',[{'instance_id':str(uuid.uuid4()),'pid':1,'creation_time':1},
    {'instance_id':'bad','pid':1,'creation_time':1},{'instance_id':str(uuid.uuid4()),'pid':True,'creation_time':1}])
def test_wrong_or_malformed_target_cannot_restart(host,fields):
    before=host.instance_id
    assert request(host,'core_restart',**fields)['message_type']=='protocol_error'
    host.advance()
    assert host.instance_id==before and host._restart is None


def test_owned_graph_restart_requires_terminal_cleanup_and_new_health(host):
    before=request(host,'health_query')
    ack=request(host,'core_restart',**host.identity())
    cap=terminal(host,ack)
    assert cap.state.value=='SUCCEEDED'
    assert host.instance_id==before['instance_id']
    host.advance()
    after=request(host,'health_query')
    assert after['instance_id']!=before['instance_id'] and after['state']=='READY'
    assert (after['pid'],after['creation_time'])==(before['pid'],before['creation_time'])
    assert not after['setup_ready'] and after['checks']==[]
    assert not host.runtime.tool_registry._worker_controllers


def test_duplicate_host_refused_before_touching_stale_tasks(host):
    duplicate=CoreHost(host.paths,address='\\\\.\\pipe\\p22-duplicate-'+uuid.uuid4().hex)
    with pytest.raises(Exception):duplicate.start()
    assert duplicate.runtime is None
    assert duplicate.close()
    assert request(host,'health_query')['instance_id']==host.instance_id


def test_same_endpoint_cannot_be_owned_by_another_profile(host,tmp_path):
    other=PlumaPaths(tmp_path/'other-local',tmp_path/'other-roaming');other.ensure_directories()
    duplicate=CoreHost(other,address=host.server.address)
    with pytest.raises(Exception):duplicate.start()
    assert duplicate.runtime is None and duplicate.close()


def test_fixture_probe_cannot_grant_continue_or_renew_receipt(host):
    spec=host.runtime.tool_registry.lookup('check_setup')
    host.runtime.tool_registry.register(spec.model_copy(update={'executor':fixture_setup,'verifier':fixture_verify}),overwrite=True)
    payload={'protocol_version':1,'message_type':'setup_check','request_id':str(uuid.uuid4()),
             'instance_id':host.instance_id,'include_microphone':False}
    ack=host.handle(payload);terminal(host,ack)
    initial=host.setup_time
    read=request(host,'health_query')
    assert len(read['checks'])==5 and all(c['state']=='PASSED' for c in read['checks'])
    assert not read['native_verified'] and not read['setup_ready']
    assert host.handle(payload)['task_id']==ack['task_id'] and host.setup_time==initial


def test_restart_denial_and_stop_never_create_replacement(host):
    before=host.instance_id
    host.runtime.policy_engine.confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=False))
    cap=terminal(host,request(host,'core_restart',**host.identity()))
    assert cap.state.value=='FAILED'
    host.advance()
    assert host.instance_id==before and host._restart is None


def test_configuration_failure_is_control_only_and_repair_can_restart(tmp_path,monkeypatch):
    monkeypatch.setattr(ResidentCore,'start',lambda core:setattr(core,'_running',True))
    paths=PlumaPaths(tmp_path/'local',tmp_path/'roaming');paths.ensure_directories()
    paths.user_settings_path.write_bytes(b'{private broken config')
    value=CoreHost(paths,address='\\\\.\\pipe\\p22-'+uuid.uuid4().hex)
    try:
        value.start()
        view=request(value,'health_query')
        assert view['state']=='CONFIGURATION_ERROR' and not view['setup_ready'] and not view['hotkeys_registered']
        assert value.handle({'command':'text','text':'delete personal data'})['message_type']=='protocol_error'
        assert request(value,'setup_check',instance_id=value.instance_id,include_microphone=False)['message_type']=='protocol_error'
        paths.user_settings_path.write_text('{}',encoding='utf-8')
        value.runtime.policy_engine.confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=True))
        terminal(value,request(value,'core_restart',**value.identity()));value.advance()
        assert request(value,'health_query')['state']=='READY'
    finally:assert value.close()


def test_microphone_requires_consent_before_import(monkeypatch):
    import sys
    from pluma.adapters.capabilities import probe
    monkeypatch.setitem(sys.modules,'sounddevice',None)
    assert probe('microphone',{},False)==('UNVERIFIED','MICROPHONE_CONSENT_REQUIRED')


def test_probe_failures_are_factual_and_redacted(monkeypatch):
    from pluma.adapters import capabilities
    from pluma.core.cancellation import CancellationToken
    def denied(*_):raise PermissionError('private microphone device and model path')
    monkeypatch.setattr(capabilities,'probe',denied)
    checks=capabilities.check_setup({},True,CancellationToken())
    assert len(checks)==5 and all(c['state']=='FAILED' for c in checks)
    assert 'private' not in json.dumps(checks)


@pytest.mark.parametrize('tool,args',[('check_setup',{'include_microphone':True}),
    ('restart_core',{'instance_id':str(uuid.uuid4()),'pid':1,'creation_time':1})])
def test_planner_cannot_invent_setup_consent_or_restart(host,tool,args):
    from pluma.tools.registry import ToolArgumentError
    with pytest.raises(ToolArgumentError,match='explicit typed user request'):
        host.runtime.tool_registry.execute(tool,args)


def test_restart_drains_other_task_before_replacing_graph(host,tmp_path):
    from tests.unit.test_worker_cancellation import OwnedProbe
    from pluma.memory.activity import ActivityQuery
    registry=host.runtime.tool_registry
    spec=registry.lookup('check_setup')
    registry.register(spec.model_copy(update={'executor':OwnedProbe(str(tmp_path)),'timeout_s':15}),overwrite=True)
    setup=request(host,'setup_check',instance_id=host.instance_id,include_microphone=False)
    end=time.monotonic()+6
    while not (tmp_path/'entered').exists() and time.monotonic()<end:time.sleep(.01)
    assert (tmp_path/'entered').exists()
    cap=host.runtime.supervisor.get_task(setup['task_id'])
    old=host.instance_id
    terminal(host,request(host,'core_restart',**host.identity()))
    host.advance()
    assert host.instance_id!=old and cap.terminal_ready.is_set() and cap.state.value=='STOPPED'
    assert not registry._worker_controllers and not (tmp_path/'late').exists()
    assert ActivityQuery(host.runtime.db).task_by_id(setup['task_id'])['final_state']=='STOPPED'


def test_stop_after_queued_restart_prevents_new_graph(host):
    before=host.instance_id
    cap=terminal(host,request(host,'core_restart',**host.identity()))
    assert host._restart is not None
    cap.cancellation_token.cancel()
    host.advance()
    assert host.instance_id==before and host._restart is None


def test_global_stop_withdraws_terminal_restart_intent(host):
    before=host.instance_id
    terminal(host,request(host,'core_restart',**host.identity()))
    reply=request(host,'stop')
    assert reply['message_type']=='stop_ack'
    host.advance()
    assert host.instance_id==before and host._restart is None


def test_stale_task_reconciled_before_host_ready(host):
    from pluma.memory.activity import TaskRecord,ActivityQuery
    paths=host.paths
    host.runtime.ledger.insert_task(TaskRecord(task_id='owned-stale',request_id='owned-stale-request',
        input_mode='TEXT',command_text='Owned interrupted fixture',route='FAST',final_state='RUNNING'))
    assert host.close()
    replacement=CoreHost(paths,address=host.server.address)
    try:
        replacement.start()
        view=request(replacement,'health_query')
        assert view['state']=='READY' and view['stale_tasks_recovered']==1
        assert ActivityQuery(replacement.runtime.db).task_by_id('owned-stale')['final_state']=='ABORTED_BY_CRASH'
    finally:assert replacement.close()


def test_lost_hotkey_thread_drains_into_control_only_graph(host):
    class DeadThread:
        def is_alive(self):return False
        def join(self,*_):pass
    host.runtime.resident_core._hotkey_thread=DeadThread()
    view=request(host,'health_query')
    assert view['state']=='RECOVERY_ERROR' and not view['can_restart'] and not view['setup_ready']
    host.advance()
    assert host.state=='HOTKEY_ERROR' and request(host,'health_query')['can_restart']
    assert request(host,'setup_check',instance_id=host.instance_id,include_microphone=False)['message_type']=='protocol_error'


def test_incomplete_failed_startup_drain_resumes_into_control_graph(tmp_path,monkeypatch):
    from pluma.app import PlumaApplicationRuntime
    def rejected_start(core):raise RuntimeError('Owned startup fault')
    original_close=PlumaApplicationRuntime.close
    first=True
    def delayed_close(runtime,timeout_s=5):
        nonlocal first
        if first:
            first=False
            return original_close(runtime,0)
        return original_close(runtime,timeout_s)
    monkeypatch.setattr(ResidentCore,'start',rejected_start)
    monkeypatch.setattr(PlumaApplicationRuntime,'close',delayed_close)
    paths=PlumaPaths(tmp_path/'local',tmp_path/'roaming');paths.ensure_directories()
    value=CoreHost(paths,address='\\\\.\\pipe\\p22-start-'+uuid.uuid4().hex)
    try:
        value.start()
        old=value.runtime;identity=value.instance_id
        assert value.state=='RECOVERY_ERROR' and old.db.is_open
        value.advance()
        assert value.state=='HOTKEY_ERROR' and value.runtime is not old and not old.db.is_open
        assert value.instance_id!=identity and request(value,'health_query')['can_restart']
    finally:assert value.close()


def test_voice_owner_loss_revokes_core_readiness(host):
    class ThreadState:
        def __init__(self,alive):self.alive=alive
        def is_alive(self):return self.alive
    core=host.runtime.resident_core
    core._hotkey_thread=ThreadState(True)
    core.voice_activation._running=False
    core.voice_activation._thread=ThreadState(False)
    try:
        view=request(host,'health_query')
    finally:core._hotkey_thread=None
    assert view['state']=='RECOVERY_ERROR' and not view['hotkeys_registered'] and not view['setup_ready']
    host.advance()
    assert host.state=='HOTKEY_ERROR' and request(host,'health_query')['can_restart']


def test_hotkey_loss_cancels_old_queued_restart_before_control_replacement(host):
    class DeadThread:
        def is_alive(self):return False
        def join(self,*_):pass
    before=host.instance_id
    terminal(host,request(host,'core_restart',**host.identity()))
    host.runtime.resident_core._hotkey_thread=DeadThread()
    host.advance()
    view=request(host,'health_query')
    assert host._restart is None and view['can_restart'] and view['instance_id']!=before
    host.advance()  # No lookup of an old task in the replacement supervisor.


def test_health_handler_is_drained_before_graph_storage_closes(host,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    entered=threading.Event();release=threading.Event()
    original=host.health
    def held(request_id):
        entered.set()
        assert release.wait(3)
        return original(request_id)
    monkeypatch.setattr(host,'health',held)
    with ThreadPoolExecutor(1) as pool:
        pending=pool.submit(request,host,'health_query')
        try:
            assert entered.wait(1)
            report=host.runtime.close(.05)
            assert not report.complete and host.runtime.db.is_open
        finally:release.set();pending.result(2)
    assert host.close()


@pytest.mark.parametrize('stop',[True,False])
def test_setup_worker_stop_and_timeout_leave_no_worker(host,tmp_path,stop):
    from tests.unit.test_worker_cancellation import OwnedProbe
    spec=host.runtime.tool_registry.lookup('check_setup')
    host.runtime.tool_registry.register(spec.model_copy(update={'executor':OwnedProbe(str(tmp_path)),
        'timeout_s':3 if not stop else 15}),overwrite=True)
    ack=request(host,'setup_check',instance_id=host.instance_id,include_microphone=False)
    end=time.monotonic()+6
    while not (tmp_path/'entered').exists() and time.monotonic()<end:time.sleep(.01)
    assert (tmp_path/'entered').exists()
    if stop:host.runtime.supervisor.request_stop(ack['task_id'])
    cap=terminal(host,ack)
    assert cap.state.value in ('STOPPED','FAILED') and not request(host,'health_query')['setup_ready']
    assert not host.runtime.tool_registry._worker_controllers and not (tmp_path/'late').exists()
    assert any(e.kind=='worker' and e.verified and e.code=='WORKER_ABSENCE_VERIFIED' for e in cap.cleanup_evidence)
