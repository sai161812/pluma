"""Scoped saved evidence. Private inverse recipes never cross the UI boundary."""
import hashlib
import json
from datetime import datetime

from pluma.memory.history import _command, _identifier
from pluma.memory.redaction import sanitise_args_for_ledger

TERMINAL = {'SUCCEEDED', 'FAILED', 'STOPPED', 'STOPPED_WITH_RESIDUAL', 'ABORTED_BY_CRASH'}


def text(value, bound=2048):
    if value is None:
        return None
    if not isinstance(value, str) or len(value.encode('utf-8')) > bound:
        return None
    return _command(value)


def validate_cleanup(saved):
    if (not isinstance(saved, dict) or type(saved.get('version')) is not int or saved['version'] != 1
            or type(saved.get('complete')) is not bool or not isinstance(saved.get('entries'), list)
            or len(saved['entries']) > 512):
        raise ValueError('Malformed saved cleanup envelope.')


def selection(connection, task_id, action_id):
    """Same projection at preview, pre-policy admission and atomic claim."""
    from pluma.memory.undo import SUPPORTED_ACTIONS, _is_legacy_without_guard
    row = connection.execute('''SELECT a.id,a.task_id,u.undo_json,u.available,c.state AS claim_state,
        t.final_state FROM actions a JOIN tasks t ON t.task_id=a.task_id
        JOIN undo_records u ON u.action_id=a.id LEFT JOIN undo_claims c ON c.action_id=a.id
        WHERE a.task_id=? AND a.id=? AND length(CAST(u.undo_json AS BLOB))<=65536''',
        (task_id, action_id)).fetchone()
    if row is None or row['available'] != 1 or row['claim_state'] is not None or row['final_state'] not in TERMINAL:
        raise ValueError('Selected undo is unavailable.')
    later = connection.execute('''SELECT 1 FROM actions a JOIN undo_records u ON u.action_id=a.id
        WHERE a.task_id=? AND u.available=1 AND a.id>? LIMIT 1''', (task_id, action_id)).fetchone()
    if later is not None:
        raise ValueError('Later actions must be undone first.')
    from pluma.core.cleanup import CleanupEvidence, latest_unresolved
    cleanup = connection.execute('SELECT metadata_json FROM cleanup_reports WHERE task_id=? '
        'AND length(CAST(metadata_json AS BLOB))<=65536', (task_id,)).fetchone()
    if cleanup is None:
        raise ValueError('Original executor cleanup is unavailable.')
    saved = json.loads(cleanup['metadata_json'])
    validate_cleanup(saved)
    checks = [CleanupEvidence.model_validate(item, strict=True) for item in saved['entries']]
    if saved.get('complete') is not True or latest_unresolved(checks):
        raise ValueError('Original executor cleanup is unresolved.')
    state = json.loads(row['undo_json'])
    if (not isinstance(state, dict) or state.get('action') not in SUPPORTED_ACTIONS
            or _is_legacy_without_guard(state) or state.get('action') == 'pending_mutation'):
        raise ValueError('No supported verified inverse is available.')
    # Paths/key identify the material effect. Never include before/after values,
    # browser profiles, private text or process handles from an inverse recipe.
    descriptions = {
        'copy_file': 'Remove only the captured unchanged copy.',
        'create_folder': 'Remove only the captured unchanged empty folder.',
        'safe_delete': 'Restore the exact captured Recycle Bin item to its original path.',
        'app_launch': 'Close only the captured PLUMA-created application. Unsaved work may be lost.',
        'browser_tab': 'Close only the captured PLUMA-owned tab.',
        'clipboard_restore': 'Restore private clipboard text from its captured volatile receipt. Content is hidden.',
        'screen_control_text': 'Restore captured private control text from its volatile receipt. Content is hidden.'}
    material = descriptions.get(state['action'], 'Restore captured ' + state['action'].replace('_', ' ') + '.')
    for name in ('source', 'destination', 'original_path', 'new_path', 'current_path', 'path', 'key', 'app_name'):
        value = text(state.get(name), 2048)
        if state.get(name) is not None and value != state[name]:
            raise ValueError('Selected material cannot be displayed safely.')
        if value:
            material += '\n' + name.replace('_', ' ').capitalize() + ': ' + value
    if state['action'] == 'memory_write':
        from pluma.memory.tool_store import canonical
        before = state.get('before')
        if before is None:
            material += '\nRemove this recorded entry only if its current value is unchanged.'
        else:
            previous = canonical(json.loads(before[0]))
            if len(previous.encode('utf-8')) > 2048:
                raise ValueError('Previous entry cannot be displayed within the safe material bound.')
            material += '\nRestore previous entry: ' + previous
    for name in ('hwnd', 'pid', 'creation_time'):
        if type(state.get(name)) is int:
            material += '\n' + name.upper() + ': ' + str(state[name])
    if state['action'] in ('set_volume', 'mute', 'unmute', 'set_default_audio_device', 'window_geometry', 'window_state'):
        from pluma.memory.redaction import redact_sensitive_data
        before = state.get('before')
        encoded = json.dumps(redact_sensitive_data(before), ensure_ascii=False)
        if len(encoded.encode('utf-8')) > 2048:
            raise ValueError('Captured restoration effect exceeds its safe display bound.')
        material += '\nCaptured state to restore: ' + encoded
    if len(material.encode('utf-8')) > 4096:
        raise ValueError('Material effect exceeds the safe display bound.')
    revision = hashlib.sha256((task_id + ':' + str(action_id) + ':' + row['undo_json']).encode()).hexdigest()
    return {'target_task_id': task_id, 'action_id': action_id, 'revision': revision, 'material': material}


def read_detail(core, request):
    from pluma.core.ipc_contracts import TaskDetailV1, SavedActionV1
    from pluma.core.cleanup import CleanupEvidence, latest_unresolved
    from pluma.memory.action_presentation import decode_presentation, presentation
    db = core.ledger._db
    with db.read_snapshot() as connection:
        raw = connection.execute('''SELECT task_id, request_id, final_state,
            EXISTS(SELECT 1 FROM actions a WHERE a.task_id=tasks.task_id AND (a.tool LIKE '%clipboard%' OR a.tool IN ('paste','paste_text'))) AS private_input,
            CASE WHEN length(CAST(original_transcript AS BLOB))<=8192 THEN original_transcript END AS original_transcript,
            CASE WHEN length(CAST(active_process AS BLOB))<=2048 THEN active_process END AS active_process,
            CASE WHEN length(CAST(active_window AS BLOB))<=2048 THEN active_window END AS active_window
            FROM tasks WHERE task_id=?''', (request.task_id,)).fetchone()
        if raw is None:
            raise ValueError('Task not found.')
        cleanup_row = connection.execute('SELECT metadata_json FROM cleanup_reports WHERE task_id=? AND length(CAST(metadata_json AS BLOB))<=65536', (request.task_id,)).fetchone()
        complete = None
        unresolved = None
        residual = []
        if cleanup_row is not None:
            saved = json.loads(cleanup_row['metadata_json'])
            validate_cleanup(saved)
            checks = [CleanupEvidence.model_validate(item, strict=True) for item in saved['entries']]
            unresolved = len(latest_unresolved(checks))
            residual = [_identifier(item.code) or "UNAVAILABLE" for item in latest_unresolved(checks)]
            complete = unresolved == 0
            if saved.get('complete') is not complete:
                raise ValueError('Contradictory cleanup evidence.')
        rows = connection.execute('''SELECT a.id,a.step_index,a.tool,a.adapter,a.risk,a.approval_state,a.started_at,a.ended_at,a.duration_ms,a.verified,
            CASE WHEN length(CAST(a.result_json AS BLOB))<=65536 THEN a.result_json END AS result_json,
            CASE WHEN length(CAST(a.args_json_sanitized AS BLOB))<=65536 THEN a.args_json_sanitized END AS args_json,
            CASE WHEN length(CAST(a.verification_json AS BLOB))<=16000 THEN a.verification_json END AS verification_json,
            CASE WHEN length(CAST(a.presentation_json AS BLOB))<=14000 THEN a.presentation_json END AS presentation_json,
            (length(CAST(a.args_json_sanitized AS BLOB))>65536 OR length(CAST(a.verification_json AS BLOB))>16000
             OR length(CAST(a.presentation_json AS BLOB))>14000) AS oversized,
            u.available,u.rollback_attempted,u.rollback_ok,c.state AS claim_state,
            CASE WHEN length(CAST(u.rollback_result_json AS BLOB))<=16000 THEN u.rollback_result_json END AS rollback_result_json,
            CASE WHEN length(CAST(u.undo_json AS BLOB))<=65536 THEN u.undo_json END AS undo_json FROM actions a
            LEFT JOIN undo_records u ON u.action_id=a.id LEFT JOIN undo_claims c ON c.action_id=a.id
            WHERE a.task_id=? AND a.id>? ORDER BY a.id LIMIT ?''',
            (request.task_id, request.after_action_id, request.limit + 1)).fetchall()
        actions = []
        for row in rows[:request.limit]:
            if row['oversized']:
                raise ValueError('Oversized saved evidence.')
            for field in ('started_at', 'ended_at'):
                if row[field] is not None and (len(row[field]) > 64 or datetime.fromisoformat(row[field].replace('Z','+00:00')).tzinfo is None):
                    raise ValueError('Invalid saved action timestamp.')
            view = decode_presentation(row['tool'], row['presentation_json'])
            proof = json.loads(row['verification_json']) if row['verification_json'] else None
            if proof is not None and (type(proof.get('ok')) is not bool or int(proof['ok']) != row['verified']):
                raise ValueError('Contradictory verifier evidence.')
            selected = None
            if complete is True:
                try:
                    selected = selection(connection, request.task_id, row['id'])
                except ValueError:
                    pass
            current = target = None
            if (row['claim_state'] == 'claimed' or row['rollback_attempted'] and row['rollback_ok'] == 0) and row['undo_json']:
                inverse = json.loads(row['undo_json'])
                if inverse.get('action') in ('move_file', 'rename_file'):
                    current = text(inverse.get('destination', inverse.get('new_path')))
                    target = text(inverse.get('source', inverse.get('original_path')))
            rollback_result = json.loads(row['rollback_result_json']) if row['rollback_result_json'] else {}
            rollback_code = _identifier(rollback_result.get('error_code', rollback_result.get('error')))
            result_data = json.loads(row['result_json']) if row['result_json'] else {}
            effect = result_data.get('effect_state') if result_data.get('non_undoable') is True else None
            if effect is None and row['undo_json']:
                intent = json.loads(row['undo_json'])
                if intent.get('non_undoable') is True:
                    effect = intent.get('effect_state', 'unknown')
            actions.append(SavedActionV1(action_id=row['id'], step_index=row['step_index'], tool=row['tool'],
                arguments=sanitise_args_for_ledger(row['tool'], json.loads(row['args_json'])),
                adapter=_identifier(row['adapter']), risk=row['risk'], approval=_identifier(row['approval_state']),
                started_at=text(row['started_at'], 64), ended_at=text(row['ended_at'], 64), duration_ms=row['duration_ms'],
                factual_message=view['factual_message'], policy_reason=view['policy_reason'], error_code=view['error_code'],
                verified=bool(row['verified']), verification_method=_identifier(proof.get('method')) if proof else None,
                verification_detail=presentation(row['tool'], proof.get('detail'))['factual_message'] if proof else None,
                undo_available=bool(row['available']), rollback_attempted=bool(row['rollback_attempted']),
                rollback_ok=None if row['rollback_ok'] is None else bool(row['rollback_ok']),
                rollback_code=rollback_code, claim_state=row['claim_state'], effect_state=effect, conflict_current=current, conflict_target=target, selection=selected))
        return TaskDetailV1(request_id=request.request_id, task_id=raw['task_id'], task_request_id=raw['request_id'],
            original_transcript=('[REDACTED CLIPBOARD COMMAND]' if raw['private_input'] and raw['original_transcript'] is not None else text(raw['original_transcript'], 8192)), active_process=text(raw['active_process']),
            active_window=text(raw['active_window']), cleanup_complete=complete, cleanup_unresolved=unresolved, residual_codes=residual,
            actions=actions, has_more=len(rows)>request.limit,
            next_action_id=actions[-1].action_id if actions else request.after_action_id)


def conflict_folder(db, task_id, action_id, location):
    from pathlib import Path
    with db.read_snapshot() as connection:
        row = connection.execute('SELECT u.undo_json FROM actions a JOIN undo_records u ON u.action_id=a.id '
            'LEFT JOIN undo_claims c ON c.action_id=a.id '
            'WHERE a.task_id=? AND a.id=? AND ((u.rollback_attempted=1 AND u.rollback_ok=0) OR c.state=\'claimed\') '
            'AND length(CAST(u.undo_json AS BLOB))<=65536', (task_id, action_id)).fetchone()
        if row is None:
            raise ValueError('No saved conflict.')
        state = json.loads(row['undo_json'])
        if state.get('action') not in ('move_file', 'rename_file'):
            raise ValueError('No recorded file conflict.')
        value = (state.get('destination', state.get('new_path')) if location == 'current'
                 else state.get('source', state.get('original_path')))
        if not isinstance(value, str) or text(value) != value or not Path(value).is_absolute():
            raise ValueError('The recorded folder cannot be exposed safely.')
        return str(Path(value).parent)
