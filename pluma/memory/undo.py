"""Durable, at-most-once manual undo. Unknown claims never auto-repeat effects."""
from datetime import datetime, timezone
import json
import uuid

from pluma.memory.tool_store import connect, row

SUPPORTED_ACTIONS = {'memory_write', 'move_file', 'rename_file', 'copy_file', 'create_folder', 'window_geometry', 'safe_delete', 'pending_mutation', 'set_volume', 'mute', 'unmute', 'set_default_audio_device'}


def claim_latest(path, task_id):
    with connect(path, write=True) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            record = db.execute('SELECT action_id, undo_json FROM undo_records WHERE available=1 ORDER BY action_id DESC LIMIT 1').fetchone()
            if record is None:
                raise ValueError('No undo record is available.')
            state = json.loads(record['undo_json'])
            if state.get('action') not in SUPPORTED_ACTIONS:
                raise ValueError('Undo record lacks a supported conflict-safe inverse.')
            pending_recycle = (state['action'] == 'pending_mutation' and state.get('tool') == 'safe_delete'
                and state.get('pre_state', {}).get('guard_version') == 1)
            if state['action'] == 'pending_mutation' and not pending_recycle:
                raise ValueError('Unknown partial effect has no supported inverse.')
            if pending_recycle:
                # A manual inverse must never consume intent while the original
                # executor could still commit it. Automatic STOP recovery has
                # its own prior drain and claim; manual recovery needs durable
                # terminal worker/job absence evidence from the original task.
                owner = db.execute('SELECT t.final_state,c.metadata_json FROM actions a '
                    'JOIN tasks t ON t.task_id=a.task_id LEFT JOIN cleanup_reports c ON c.task_id=t.task_id '
                    'WHERE a.id=?', (record['action_id'],)).fetchone()
                if owner is None or owner['final_state'] not in (
                        'SUCCEEDED', 'FAILED', 'STOPPED', 'STOPPED_WITH_RESIDUAL', 'ABORTED_BY_CRASH') or not owner['metadata_json']:
                    raise ValueError('Original executor absence has not been verified.')
                from pluma.core.cleanup import CleanupEvidence, latest_unresolved
                checks = [CleanupEvidence.model_validate(item) for item in json.loads(owner['metadata_json'])['entries']
                          if item.get('kind') in ('worker', 'job')]
                if not checks or latest_unresolved(checks):
                    raise ValueError('Original executor cleanup is unresolved.')
            if state['action'] != 'memory_write' and not pending_recycle and state.get('guard_version') != 1:
                raise ValueError('Legacy file undo lacks captured identity.')
            if state['action'] == 'copy_file' and 'created_identity' not in state:
                raise ValueError('Copy lacks a verified creation receipt.')
            if state['action'] == 'create_folder' and 'created' not in state:
                raise ValueError('Folder lacks a verified creation receipt.')
            if state['action'] == 'safe_delete' and not {'recycled_path', 'recycled_identity'} <= state.keys():
                raise ValueError('Recycle lacks an exact verified item receipt.')
            if state['action'] in ('set_volume', 'mute', 'unmute', 'set_default_audio_device') and not {'before', 'after', 'target'} <= state.keys():
                raise ValueError('Audio undo lacks a verified endpoint/state receipt.')
            operation = str(uuid.uuid4())
            db.execute('INSERT INTO undo_claims(action_id,operation_id,task_id,state,created_at) VALUES(?,?,?,\'claimed\',?)',
                (record['action_id'], operation, task_id, datetime.now(timezone.utc).isoformat()))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
    return {'storage_path': path, 'action_id': record['action_id'], 'operation_id': operation, 'undo_data': state}


def finish(receipt, ok):
    with connect(receipt['storage_path'], write=True) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            owned = db.execute("SELECT state FROM undo_claims WHERE action_id=? AND operation_id=?",
                (receipt['action_id'], receipt['operation_id'])).fetchone()
            if owned is None or owned['state'] != 'claimed':
                raise ValueError('Undo claim does not belong to this operation.')
            db.execute('UPDATE undo_records SET available=?,rollback_attempted=1,rollback_ok=?,rollback_result_json=? WHERE action_id=?',
                (0 if ok else 1, int(ok), json.dumps({'verified': ok}), receipt['action_id']))
            db.execute('UPDATE undo_claims SET state=? WHERE action_id=?',
                ('verified' if ok else 'unverified', receipt['action_id']))
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise


def verify(receipt):
    with connect(receipt['storage_path']) as db:
        observed = db.execute('SELECT ur.available,ur.rollback_ok,uc.state FROM undo_records ur JOIN undo_claims uc USING(action_id) '
            'WHERE ur.action_id=? AND uc.operation_id=?', (receipt['action_id'], receipt['operation_id'])).fetchone()
        if observed is None or list(observed) != [0, 1, 'verified']:
            return False
        state = receipt['undo_data']
        if state['action'] in ('set_volume', 'mute', 'unmute', 'set_default_audio_device'):
            from pluma.tools.audio import verify_audio_restored
            return verify_audio_restored(state)
        if state['action'] == 'pending_mutation' and state.get('tool') == 'safe_delete':
            from pluma.adapters.recycle_bin import _snapshot, _content, identity
            pending = state['pre_state']
            from pathlib import Path
            with identity._open(Path(pending['path']).parent, parent=True) as parent:
                return (identity._parent_identity(parent) == pending['source_parent']
                    and _content(_snapshot(pending['path'])) == _content(pending['identity']))
        if state['action'] == 'safe_delete':
            from pluma.adapters.recycle_bin import verify
            return verify(state, restored=True)
        if state['action'] == 'window_geometry':
            from pluma.adapters.window_geometry import verify
            return verify(state, restored=True)
        if state['action'] in ('copy_file', 'create_folder'):
            from pluma.adapters.file_operations import verify_restored
            return verify_restored(state)
        if state['action'] in ('move_file', 'rename_file') and state.get('guard_version') == 1:
            from pluma.adapters.file_identity import verify_restore
            return verify_restore(state)
        return state['action'] == 'memory_write' and row(db, state['kind'], state['key']) == state['before']
