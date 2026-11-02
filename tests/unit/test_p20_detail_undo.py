"""Owned saved evidence, native SQLite inverse and the actual admission pipeline."""
import json
import time
from uuid import uuid4

import pytest

from pluma.core.task_supervisor import TaskState
from pluma.memory import tool_store
from pluma.tools.registry import ToolArgumentError
from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_memory_tools import approved


def saved(runtime, monkeypatch, count=1):
    approved(runtime, monkeypatch)
    cap = task(runtime, 'p20-saved')
    for index in range(count):
        result = runtime.tool_registry.execute('save_preference', {'key': f'p20.key{index}', 'value': 'owned'}, cap, runtime.ledger)
        assert result.ok and result.verified
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    return cap


def detail(runtime, cap, **fields):
    payload = dict(protocol_version=1, message_type='task_detail_query', request_id=str(uuid4()), task_id=cap.task_id, **fields)
    from pluma.memory.history_detail import read_detail
    from pluma.core.ipc_contracts import TaskDetailQueryV1
    read_detail(runtime.resident_core, TaskDetailQueryV1.model_validate(payload))
    return runtime.resident_core.handle_ipc_command(payload)


def test_detail_agrees_with_sqlite_and_pages_without_private_recipes(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch, 3)
    reply = detail(runtime, cap, limit=2)
    assert reply['message_type'] == 'task_detail', reply
    assert reply['cleanup_complete'] is True and reply['has_more']
    rows = runtime.db.execute_read('SELECT * FROM actions WHERE task_id=? ORDER BY id', (cap.task_id,))
    assert [a['action_id'] for a in reply['actions']] == [r['id'] for r in rows[:2]]
    assert all(a['selection'] is None for a in reply['actions'])
    last = detail(runtime, cap, after_action_id=reply['next_action_id'])
    assert last['actions'][0]['selection']['action_id'] == rows[-1]['id']
    assert not last['has_more'] and last['actions'][0]['verified']
    assert 'undo_json' not in json.dumps(last) and 'after_json' not in json.dumps(last)


def test_selected_inverse_is_scoped_reverse_order_and_consumed_once(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch, 2)
    actions = detail(runtime, cap)['actions']
    selected = actions[-1]['selection']
    wrong = dict(selected, action_id=actions[0]['action_id'])
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('undo_last', {'selection': wrong}, task(runtime), runtime.ledger)
    result = runtime.tool_registry.execute('undo_last', {'selection': selected}, task(runtime), runtime.ledger)
    assert result.ok and result.verified
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'p20.key1') == (None, None)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('undo_last', {'selection': selected}, task(runtime), runtime.ledger)
    assert detail(runtime, cap)['actions'][0]['selection'] is not None


def test_material_or_revision_change_refuses_before_policy(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime, cap)['actions'][0]['selection']
    decisions = []
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(
        lambda request: decisions.append(request) or ConfirmationResponse(approved=True))
    for altered in (dict(selected, revision='0'*64), dict(selected, material='Different target')):
        with pytest.raises(ToolArgumentError):
            runtime.tool_registry.execute('undo_last', {'selection': altered}, task(runtime), runtime.ledger)
    assert not decisions


def test_selected_undo_denial_and_conflict_preserve_newer_edit(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime, cap)['actions'][0]['selection']
    runtime.policy_engine.confirmation_contract = CallbackConfirmationContract(lambda request: ConfirmationResponse(approved=False))
    denied = runtime.tool_registry.execute('undo_last', {'selection': selected}, task(runtime), runtime.ledger)
    assert not denied.ok and runtime.db.execute_read('SELECT * FROM undo_claims') == []
    approved(runtime, monkeypatch)
    tool_store.write(tool_store.capture(str(runtime.paths.db_path), 'preference', 'p20.key0', 'owner-edit'))
    failed = runtime.tool_registry.execute('undo_last', {'selection': selected}, task(runtime), runtime.ledger)
    assert not failed.ok and failed.error_code == 'UNDO_UNVERIFIED'
    action = detail(runtime, cap)['actions'][0]
    assert action['claim_state'] == 'unverified' and action['rollback_ok'] is False and action['selection'] is None
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'p20.key0')[0] == 'owner-edit'


def test_actual_typed_ipc_admission_deduplicates_and_reads_saved_inverse(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime, cap)['actions'][0]['selection']
    request = dict(protocol_version=1, message_type='undo_submit', request_id=str(uuid4()), selection=selected)
    core = runtime.resident_core
    first = core.handle_ipc_command(request)
    second = core.handle_ipc_command(request)
    assert first['accepted'] and second['task_id'] == first['task_id']
    deadline = time.monotonic()+8
    while time.monotonic() < deadline:
        read = core.handle_ipc_command(dict(protocol_version=1, message_type='terminal_readback',
            request_id=request['request_id'], task_id=first['task_id']))
        if read.get('terminal'): break
        time.sleep(.02)
    assert read['completion_verified'] and read['terminal_persisted'], read
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'p20.key0') == (None, None)
    assert len(runtime.db.execute_read('SELECT * FROM undo_claims')) == 1


def test_native_owned_file_selected_undo_and_conflict_readback(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    original = tmp_path / 'original_\u9884\u7b97.txt'; moved = tmp_path / 'moved_\u9884\u7b97.txt'
    original.write_text('Owned original', encoding='utf-8')
    cap = task(runtime, 'p20-file-move')
    result = runtime.tool_registry.execute('move_file', {'source': str(original), 'destination': str(moved)}, cap, runtime.ledger)
    assert result.ok and result.verified and moved.read_text(encoding='utf-8') == 'Owned original'
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    selected = detail(runtime, cap)['actions'][0]['selection']
    original.write_text('New owner edit', encoding='utf-8')
    inverse = runtime.tool_registry.execute('undo_last', {'selection': selected}, task(runtime), runtime.ledger)
    assert not inverse.ok and original.read_text(encoding='utf-8') == 'New owner edit'
    assert moved.read_text(encoding='utf-8') == 'Owned original'
    conflict = detail(runtime, cap)['actions'][0]
    assert conflict['conflict_current'] == str(moved) and conflict['conflict_target'] == str(original)
    from pluma.memory.history_detail import conflict_folder
    assert conflict_folder(runtime.db, cap.task_id, conflict['action_id'], 'current') == str(tmp_path)


def test_actual_selected_undo_stop_during_material_confirmation_never_claims(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime, cap)['actions'][0]['selection']
    from pluma.ui.ipc_confirmations import IpcConfirmationBroker
    broker = IpcConfirmationBroker(runtime.supervisor.get_task, timeout_s=3)
    runtime.resident_core.confirmation_broker = broker
    runtime.policy_engine.confirmation_contract = broker
    core = runtime.resident_core
    owner = str(uuid4())
    query = lambda: core.handle_ipc_command(dict(protocol_version=1,message_type='confirmation_query',request_id=str(uuid4()),client_id=owner))
    query()
    request = dict(protocol_version=1,message_type='undo_submit',request_id=str(uuid4()),selection=selected)
    ack = core.handle_ipc_command(request)
    deadline = time.monotonic()+5
    pending = None
    while time.monotonic()<deadline:
        pending = query()
        if pending.get('confirmations'): break
        time.sleep(.02)
    assert pending.get('confirmations'), pending
    response = core.handle_ipc_command(dict(protocol_version=1,message_type='stop',request_id=str(uuid4()),task_id=ack['task_id']))
    assert response['message_type'] == 'stop_ack' and response['latch_acknowledged_count'] == 1, response
    assert runtime.db.execute_read('SELECT * FROM undo_claims') == []
    assert tool_store.read(str(runtime.paths.db_path),'preference','p20.key0')[0] == 'owned'
    broker.close()


def test_legacy_clipboard_evidence_never_exposes_raw_spoken_value(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    secret = 'P20_PRIVATE_CLIPBOARD_PAYLOAD'
    runtime.db.execute_write('UPDATE tasks SET command_text=?,original_transcript=? WHERE task_id=?', (secret,secret,cap.task_id))
    runtime.db.execute_write('UPDATE actions SET tool=?,args_json_sanitized=?,verification_json=? WHERE task_id=?',
        ('clipboard_set',json.dumps({'text':secret}),json.dumps({'ok':True,'method':'clipboard_readback','detail':secret}),cap.task_id))
    result = detail(runtime,cap)
    assert secret not in json.dumps(result)
    page = runtime.resident_core.handle_ipc_command(dict(protocol_version=1,message_type='history_page_query',request_id=str(uuid4()),search=secret))
    assert page['tasks'] == []


def test_selected_native_workers_compete_for_one_durable_claim(runtime, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime, cap)['actions'][0]['selection']
    caps = [task(runtime),task(runtime)]
    def inverse(owner):
        try: return runtime.tool_registry.execute('undo_last',{'selection':selected},owner,runtime.ledger)
        except ToolArgumentError: return None
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(inverse,caps))
    assert sum(result is not None and result.ok and result.verified for result in results) == 1
    assert [row['state'] for row in runtime.db.execute_read('SELECT state FROM undo_claims')] == ['verified']


def test_corrupt_cleanup_blocks_selected_admission_and_detail(runtime, monkeypatch):
    cap = saved(runtime, monkeypatch)
    selected = detail(runtime,cap)['actions'][0]['selection']
    runtime.db.execute_write('UPDATE cleanup_reports SET metadata_json=? WHERE task_id=?',
        (json.dumps({'version':99,'complete':True,'entries':[]}),cap.task_id))
    response = runtime.resident_core.handle_ipc_command(dict(protocol_version=1,message_type='task_detail_query',request_id=str(uuid4()),task_id=cap.task_id))
    assert response['error_code'] == 'TASK_DETAIL_UNAVAILABLE'
    with pytest.raises(ToolArgumentError): runtime.tool_registry.execute('undo_last',{'selection':selected},task(runtime),runtime.ledger)


def test_priority_stop_fences_unacknowledged_typed_inverse(runtime, monkeypatch):
    cap = saved(runtime,monkeypatch)
    selected = detail(runtime,cap)['actions'][0]['selection']
    core = runtime.resident_core
    request = str(uuid4())
    core.handle_ipc_command(dict(protocol_version=1,message_type='stop',request_id=str(uuid4()),task_id=None,submission_request_id=request))
    refused = core.handle_ipc_command(dict(protocol_version=1,message_type='undo_submit',request_id=request,selection=selected))
    assert refused['accepted'] is False and refused['error_code'] == 'SUBMISSION_STOPPED'
    assert runtime.db.execute_read('SELECT * FROM undo_claims') == []
    assert tool_store.read(str(runtime.paths.db_path),'preference','p20.key0')[0] == 'owned'


def test_changed_selected_material_cannot_reuse_admitted_request(runtime,monkeypatch):
    cap = saved(runtime,monkeypatch)
    selected = detail(runtime,cap)['actions'][0]['selection']
    core = runtime.resident_core
    request = dict(protocol_version=1,message_type='undo_submit',request_id=str(uuid4()),selection=selected)
    first = core.handle_ipc_command(request)
    assert first['accepted']
    changed = dict(request,selection=dict(selected,material='Different material'))
    refused = core.handle_ipc_command(changed)
    assert refused['accepted'] is False and refused['error_code'] == 'REQUEST_ID_REUSED'


@pytest.mark.parametrize("interruption", ["stop", "timeout"])
def test_stop_after_real_claim_preserves_uncertain_intent_and_owned_absence(runtime,monkeypatch,interruption):
    from concurrent.futures import ThreadPoolExecutor
    from tests.fixtures.p20_inverse import claim_and_wait
    cap = saved(runtime,monkeypatch)
    selected = detail(runtime,cap)['actions'][0]['selection']
    inverse_owner = task(runtime,'p20-interrupted-inverse')
    spec = runtime.tool_registry.lookup('undo_last')
    runtime.tool_registry.register(spec.model_copy(update={'executor':claim_and_wait, 'timeout_s':3 if interruption=='timeout' else 10}),overwrite=True)
    marker = runtime.paths.db_path.parent / ('p20-claimed-'+inverse_owner.task_id+'.marker')
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(runtime.tool_registry.execute,'undo_last',{'selection':selected},inverse_owner,runtime.ledger)
        deadline=time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline: time.sleep(.01)
        assert marker.read_text(encoding='ascii') == inverse_owner.task_id
        if interruption == 'stop': runtime.supervisor.stop_task(inverse_owner.task_id)
        try:
            result = pending.result(timeout=6)
            assert not result.ok
        except Exception as error:
            from pluma.core.cancellation import TaskCancelledError
            assert isinstance(error,TaskCancelledError),error
    if interruption == 'timeout': runtime.supervisor.fail_task_with_rollback(inverse_owner.task_id)
    assert inverse_owner.stop_latch_set and inverse_owner.cleanup_pending
    assert inverse_owner.state in (TaskState.STOPPED_WITH_RESIDUAL, TaskState.FAILED)
    unknown = detail(runtime,inverse_owner)['actions'][-1]
    assert unknown['effect_state'] == 'unknown' and unknown['selection'] is None
    assert runtime.db.execute_read_one('SELECT state FROM undo_claims')['state']=='claimed'
    assert tool_store.read(str(runtime.paths.db_path),'preference','p20.key0')[0]=='owned'
    assert inverse_owner.worker_controller is None or inverse_owner.worker_controller.verify_cleanup()
    marker.unlink()
