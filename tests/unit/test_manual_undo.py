"""Real owned workers compete for durable undo, never pop unknown pre-state."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace
import uuid

import pytest

from pluma.core.task_supervisor import TaskState
from pluma.memory import tool_store, undo
from pluma.memory.activity import ActionRecord, ActivityQuery, UndoRecord
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


def saved(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    cap = task(runtime, 'owned-save-before-undo')
    result = runtime.tool_registry.execute('save_preference', {'key': 'editor.theme', 'value': 'dark'}, cap, runtime.ledger)
    assert result.ok and result.verified
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    return cap


def test_concurrent_native_undo_consumes_exactly_one_record(runtime, monkeypatch):
    original = saved(runtime, monkeypatch)
    caps = [task(runtime, 'undo-one'), task(runtime, 'undo-two')]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda cap: runtime.tool_registry.execute('undo_last', {}, cap, runtime.ledger), caps))
    assert sum(result.ok and result.verified for result in results) == 1
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)
    claims = runtime.db.execute_read('SELECT state FROM undo_claims')
    assert [row['state'] for row in claims] == ['verified']
    assert ActivityQuery(runtime.db).available_undo_records_for_task(original.task_id) == []
    all_rows = runtime.db.execute_read('SELECT rollback_ok, available FROM undo_records')
    assert len(all_rows) == 1 and list(all_rows[0]) == [1, 0]
    workers = [cap.worker_controller for cap in caps]
    assert runtime.close(3).complete and all(worker.verify_cleanup() for worker in workers)


def test_conflict_keeps_durable_prestate_and_claim_without_repeating_inverse(runtime, monkeypatch):
    original = saved(runtime, monkeypatch)
    path = str(runtime.paths.db_path)
    changed = tool_store.capture(path, 'preference', 'editor.theme', 'new-owner-value')
    tool_store.write(changed)
    cap = task(runtime, 'owned-conflict-undo')
    result = runtime.tool_registry.execute('undo_last', {}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_UNVERIFIED'
    assert tool_store.read(path, 'preference', 'editor.theme')[0] == 'new-owner-value'
    record = ActivityQuery(runtime.db).available_undo_records_for_task(original.task_id)[0]
    assert json.loads(record['undo_json']) == original.undo_stack[-1]
    assert runtime.db.execute_read_one('SELECT state FROM undo_claims')['state'] == 'unverified'
    again = task(runtime, 'owned-second-conflict-undo')
    refused = runtime.tool_registry.execute('undo_last', {}, again, runtime.ledger)
    assert not refused.ok and refused.error_code == 'UNDO_UNAVAILABLE'
    # Automatic rollback also respects the outstanding durable claim.
    automatic = runtime.rollback_engine.rollback_task(original.task_id)
    assert not automatic.all_ok
    assert tool_store.read(path, 'preference', 'editor.theme')[0] == 'new-owner-value'


def test_undo_in_same_task_pops_parent_prestate_only_after_verified_consumption(runtime, monkeypatch):
    approved(runtime, monkeypatch)
    cap = task(runtime)
    result = runtime.tool_registry.execute('save_preference', {'key': 'editor.theme', 'value': 'dark'}, cap, runtime.ledger)
    assert result.ok and len(cap.undo_stack) == 1
    result = runtime.tool_registry.execute('undo_last', {}, cap, runtime.ledger)
    assert result.ok and result.verified and not cap.undo_stack
    assert len(ActivityQuery(runtime.db).actions_for_task(cap.task_id)) == 2


def test_manual_undo_skips_legacy_unguarded_record_without_claiming_it(runtime, monkeypatch):
    original = saved(runtime, monkeypatch)
    legacy_action = ActionRecord(task_id=original.task_id, step_index=99, tool='move_file',
        args_raw={'source': 'C:/legacy/source.txt', 'destination': 'C:/legacy/destination.txt'},
        risk='LOW', verified=True)
    legacy_action_id = runtime.ledger.insert_action(legacy_action)
    runtime.ledger.insert_undo_record(UndoRecord(legacy_action_id, {
        'action': 'move_file', 'source': 'C:/legacy/source.txt', 'destination': 'C:/legacy/destination.txt'}))

    cap = task(runtime, 'undo-past-legacy-record')
    result = runtime.tool_registry.execute('undo_last', {}, cap, runtime.ledger)

    assert result.ok and result.verified
    assert tool_store.read(str(runtime.paths.db_path), 'preference', 'editor.theme') == (None, None)
    legacy = runtime.db.execute_read_one(
        'SELECT available,rollback_attempted FROM undo_records WHERE action_id=?', (legacy_action_id,))
    assert list(legacy) == [1, 0]
    assert runtime.db.execute_read_one(
        'SELECT action_id FROM undo_claims WHERE action_id=?', (legacy_action_id,)) is None
    claim = runtime.db.execute_read_one('SELECT action_id,state FROM undo_claims')
    restored_action_id = runtime.db.execute_read_one(
        "SELECT ur.action_id FROM undo_records ur JOIN actions a ON a.id=ur.action_id "
        "WHERE a.task_id=? AND a.tool='save_preference'", (original.task_id,))['action_id']
    restored = runtime.db.execute_read_one(
        'SELECT available,rollback_ok FROM undo_records WHERE action_id=?',
        (restored_action_id,))
    assert list(claim) == [restored_action_id, 'verified']
    assert list(restored) == [0, 1]


def test_clipboard_lookup_and_claim_select_past_same_legacy_record(runtime):
    cap = task(runtime, 'clipboard-undo-lookup')
    clipboard_ref = str(uuid.uuid4())
    clipboard_action = ActionRecord(task_id=cap.task_id, step_index=0, tool='clipboard_set',
        args_raw={}, risk='LOW', verified=True)
    clipboard_action_id = runtime.ledger.insert_action(clipboard_action)
    runtime.ledger.insert_undo_record(UndoRecord(clipboard_action_id, {
        'action': 'clipboard_restore', 'guard_version': 1, 'volatile': True, 'undo_ref': clipboard_ref}))
    legacy_action = ActionRecord(task_id=cap.task_id, step_index=1, tool='move_file',
        args_raw={'source': 'C:/legacy/source.txt', 'destination': 'C:/legacy/destination.txt'},
        risk='LOW', verified=True)
    legacy_action_id = runtime.ledger.insert_action(legacy_action)
    runtime.ledger.insert_undo_record(UndoRecord(legacy_action_id, {
        'action': 'move_file', 'source': 'C:/legacy/source.txt', 'destination': 'C:/legacy/destination.txt'}))

    lookup = undo.peek_clipboard_ref({}, SimpleNamespace(storage_path=str(runtime.paths.db_path)))
    assert lookup['undo_ref'] == clipboard_ref
    with pytest.raises(ValueError, match='Private clipboard undo expired'):
        undo.claim_latest(str(runtime.paths.db_path), cap.task_id)
    assert runtime.db.execute_read('SELECT * FROM undo_claims') == []
