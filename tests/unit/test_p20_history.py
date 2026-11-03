"""Owned SQLite snapshots and read-only IPC; no desktop, undo or tool mutation."""
import json
import sqlite3
from contextlib import closing
from uuid import uuid4

import pytest

from pluma.core.resident import ResidentCore
from pluma.memory.activity import ActivityLedger, TaskRecord
from pluma.memory.db import DbConnection


@pytest.fixture
def history(tmp_path):
    db = DbConnection(str(tmp_path / 'history.db')); db.open()
    core = ResidentCore.__new__(ResidentCore); core.ledger = ActivityLedger(db)
    yield core, core.ledger, db
    db.close()


def saved(ledger, text='Open file_预算.md', created='2026-11-02T08:00:00+00:00', **fields):
    task, request = str(uuid4()), str(uuid4())
    ledger.insert_task(TaskRecord(task, request, 'voice', text, created_at=created, **fields))
    return task


def page(core, **fields):
    return core.handle_ipc_command(dict(protocol_version=1, message_type='history_page_query', request_id=str(uuid4()), **fields))


def test_order_paging_and_new_insert_do_not_repeat_or_omit_existing_rows(history):
    core, ledger, db = history
    ids = [saved(ledger, text=f'Owned file_{index}.md', final_state='STOPPED', route='FAST', stop_reason='user_stop') for index in range(83)]
    expected = sorted(ids, reverse=True)
    result = page(core); all_ids = [t['task_id'] for t in result['tasks']]
    assert len(all_ids) == 20 and all_ids == expected[:20] and result['has_more']
    newer = saved(ledger, created='2026-11-02T09:00:00+00:00')
    while result['has_more']:
        result = page(core, before_task_id=result['next_before_task_id'])
        all_ids += [t['task_id'] for t in result['tasks']]
    assert all_ids == expected and len(set(all_ids)) == 83 and newer not in all_ids
    assert page(core)['tasks'][0]['task_id'] == newer
    assert result['next_before_task_id'] is None
    with closing(sqlite3.connect(db._db_path)) as reader:
        assert reader.execute('SELECT COUNT(*) FROM tasks').fetchone()[0] == 84


@pytest.mark.parametrize('search', ['FILE_预算', 'straße', '%_', "' OR 1=1 --"])
def test_unicode_and_metacharacter_search_is_literal(history, search):
    core, ledger, _ = history
    wanted = saved(ledger, text='Open file_预算.md Straße %_ and '+"' OR 1=1 --")
    saved(ledger, text='Other file')
    assert [t['task_id'] for t in page(core, search=search)['tasks']] == [wanted]
    assert [t['task_id'] for t in page(core, search='STRASSE')['tasks']] == [wanted]


def test_legacy_clipboard_payload_is_redacted_before_search_and_readback(history, caplog):
    core, ledger, db = history
    task = saved(ledger)
    payload = 'HISTORY_PRIVATE_PAYLOAD ' + 'x '*150 + 'put this in the clipboard'
    db.execute_write('UPDATE tasks SET command_text=?, original_transcript=? WHERE task_id=?', (payload, payload, task))
    result = page(core)
    assert result['tasks'][0]['command_text'] == '[REDACTED CLIPBOARD COMMAND]'
    assert page(core, search='HISTORY_PRIVATE_PAYLOAD')['tasks'] == []
    assert page(core, search='clipboard')['tasks'][0]['task_id'] == task
    assert 'HISTORY_PRIVATE_PAYLOAD' not in json.dumps(result) + caplog.text
    assert not ({'original_transcript','active_process','active_window','args_json','undo_json'} & result['tasks'][0].keys())


def test_oversized_legacy_command_is_withheld_without_exposing_a_prefix(history):
    core, ledger, db = history
    task = saved(ledger)
    raw = 'HISTORY_PRIVATE_OVERSIZE ' + 'x'*9000 + ' clipboard'
    db.execute_write('UPDATE tasks SET command_text=? WHERE task_id=?', (raw,task))
    result = page(core)
    assert result['tasks'][0]['command_text'] is None and 'HISTORY_PRIVATE' not in json.dumps(result)
    assert page(core, search='HISTORY_PRIVATE')['tasks'] == []


@pytest.mark.parametrize('fields', [dict(limit=0),dict(limit=21),dict(limit=True),dict(search='x'*257),
    dict(before_task_id='not-an-id'),dict(action='undo'),dict(search={'text':'private'})])
def test_invalid_query_is_rejected_before_storage(history, monkeypatch, fields):
    core, _, db = history
    monkeypatch.setattr(db,'read_snapshot',lambda **kw: (_ for _ in ()).throw(AssertionError('Invalid query reached storage')))
    assert page(core, **fields)['error_code'] == 'INVALID_REQUEST'


def test_deleted_cursor_is_unavailable_not_a_fake_end(history):
    core, ledger, db = history
    ids = [saved(ledger) for _ in range(3)]
    cursor = page(core, limit=1)['next_before_task_id']
    db.execute_write('DELETE FROM tasks WHERE task_id=?',(cursor,))
    result = page(core, before_task_id=cursor)
    assert result['error_code'] == 'HISTORY_CURSOR_UNAVAILABLE' and 'tasks' not in result


def test_empty_storage_restart_and_unavailable_are_distinct(history):
    core, ledger, db = history
    empty = page(core)
    assert empty['tasks'] == [] and not empty['has_more']
    task = saved(ledger, final_state='STOPPED_WITH_RESIDUAL', stop_reason='user_stop', error_code='CONFLICT')
    original = page(core)['tasks'][0]
    path = db._db_path; db.close()
    assert page(core)['error_code'] == 'HISTORY_UNAVAILABLE'
    with DbConnection(path) as reopened:
        new_core = ResidentCore.__new__(ResidentCore); new_core.ledger = ActivityLedger(reopened)
        assert page(new_core)['tasks'] == [original] and original['task_id'] == task


def test_private_identifier_and_unknown_historical_flags_are_withheld(history):
    core, ledger, _ = history
    saved(ledger, error_code='A'*36, route='NOT_A_ROUTE', final_state='NOT_A_STATE')
    task = page(core)['tasks'][0]
    assert task['error_code'] is None and task['route'] is None and task['final_state'] is None


def test_every_presented_field_matches_independent_sqlite_readback(history):
    core, ledger, db = history
    task = saved(ledger, final_state='STOPPED_WITH_RESIDUAL', route='SMART',
        started_at='2026-11-02T08:00:10+00:00', completed_at='2026-11-02T08:01:00+00:00',
        stop_reason='user_stop', error_code='OWNED_CONFLICT')
    with closing(sqlite3.connect(db._db_path)) as reader:
        reader.row_factory = sqlite3.Row
        expected = dict(reader.execute('SELECT task_id, request_id, input_mode, command_text, created_at, started_at, completed_at, final_state, route, stop_reason, error_code FROM tasks WHERE task_id=?', (task,)).fetchone())
    assert page(core)['tasks'] == [expected]


def test_malformed_dates_fail_closed(history):
    core, ledger, _ = history
    saved(ledger, created='not-a-timestamp')
    assert page(core)['error_code'] == 'HISTORY_UNAVAILABLE'


def test_snapshot_is_read_only_and_sql_work_is_bounded(history):
    _, ledger, db = history
    saved(ledger)
    with db.read_snapshot() as connection:
        with pytest.raises(sqlite3.OperationalError): connection.execute('DELETE FROM tasks')
    with pytest.raises(sqlite3.OperationalError):
        with db.read_snapshot(budget_s=.000001) as connection:
            connection.execute('WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<1000000) SELECT sum(x) FROM n').fetchall()
    assert len(db.execute_read('SELECT task_id FROM tasks')) == 1


def test_history_order_index_upgrades_without_rewriting_saved_tasks(history):
    core, ledger, db = history
    task = saved(ledger)
    original = page(core)['tasks']
    db.execute_write('DROP INDEX idx_tasks_history_order')
    db.execute_write("DELETE FROM _schema_migrations WHERE version='0007_history_order'")
    db.close(); db.open()
    assert page(core)['tasks'] == original and original[0]['task_id'] == task
    assert db.execute_read_one("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tasks_history_order'")
