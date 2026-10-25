"""Executor-selected SQLite memory, compare-and-swap writes and safe inverses."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from pluma.memory.redaction import redact_sensitive_data

TABLES = {'preference': ('preferences', 'key', 'value_json'),
          'routine': ('routines', 'name', 'definition_json')}


def canonical(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    if len(encoded.encode('utf-8')) > 16384 or redact_sensitive_data(value) != value:
        raise ValueError('Memory value is private or exceeds the storage bound.')
    return encoded


@contextmanager
def connect(path, *, write=False):
    if not path or path == ':memory:':
        raise ValueError('Executor-owned persistent storage is required.')
    uri = Path(path).resolve().as_uri() + ('?mode=rw' if write else '?mode=ro')
    with closing(sqlite3.connect(uri, uri=True, timeout=1, isolation_level=None)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        if not write:
            db.execute('PRAGMA query_only=ON')
        yield db


def row(db, kind, key):
    table, column, value = TABLES[kind]
    result = db.execute(f'SELECT {value}, updated_at FROM {table} WHERE {column}=?', (key,)).fetchone()
    return list(result) if result is not None else None


def capture(path, kind, key, value):
    with connect(path) as db:
        before = row(db, kind, key)
        if before is not None:
            canonical(json.loads(before[0]))  # Never journal an old private value.
    return {'action': 'memory_write', 'storage_path': path, 'kind': kind, 'key': key,
            'before': before, 'after_json': canonical(value),
            'revision': datetime.now(timezone.utc).isoformat()}


def write(state):
    table, column, value_column = TABLES[state['kind']]
    with connect(state['storage_path'], write=True) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if row(db, state['kind'], state['key']) != state['before']:
                raise ValueError('Memory changed after capture.')
            if state['kind'] == 'preference':
                db.execute('INSERT OR REPLACE INTO preferences(key,value_json,updated_at) VALUES(?,?,?)',
                    (state['key'], state['after_json'], state['revision']))
            else:
                # Keep the routine identity stable across edits.
                import uuid
                old = db.execute('SELECT id FROM routines WHERE name=?', (state['key'],)).fetchone()
                db.execute('INSERT OR REPLACE INTO routines(id,name,definition_json,updated_at) VALUES(?,?,?,?)',
                    (old[0] if old else str(uuid.uuid4()), state['key'], state['after_json'], state['revision']))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
    if not verify(state):
        raise ValueError('Memory postcondition changed.')


def verify(state):
    with connect(state['storage_path']) as db:
        return row(db, state['kind'], state['key']) == [state['after_json'], state['revision']]


def read(path, kind, key):
    with connect(path) as db:
        observed = row(db, kind, key)
    value = json.loads(observed[0]) if observed is not None else None
    canonical(value)
    return value, observed


def restore(state):
    table, key_column, value_column = TABLES[state['kind']]
    with connect(state['storage_path'], write=True) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            if row(db, state['kind'], state['key']) != [state['after_json'], state['revision']]:
                raise ValueError('Memory undo conflicts with a newer edit.')
            if state['before'] is None:
                db.execute(f'DELETE FROM {table} WHERE {key_column}=?', (state['key'],))
            else:
                db.execute(f'UPDATE {table} SET {value_column}=?, updated_at=? WHERE {key_column}=?',
                    (*state['before'], state['key']))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        if row(db, state['kind'], state['key']) != state['before']:
            raise ValueError('Memory undo was not verified.')
