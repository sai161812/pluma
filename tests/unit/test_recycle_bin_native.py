"""Recycle-only Windows API evidence on explicitly owned temporary files."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import pytest

from pluma.adapters import recycle_bin as native
from pluma.brain.schemas import RouteMode
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core.cancellation import CancellationToken
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.files import execute_safe_delete, verify_safe_delete
from pluma.tools.registry import ToolArgumentError
from pluma.tools.base import ToolResult
from tests.unit.test_memory_tools import approved
from tests.unit.test_mutation_journal import contradict_fixture
from tests.unit.test_runtime_shutdown import runtime, task
from tests.unit.test_worker_cancellation import await_file


@pytest.mark.parametrize('content', [b'', b'owned native recycle fixture', 'owned Unicode: café'.encode()], ids=['empty', 'text', 'unicode'])
def test_native_recycle_preserves_exact_identity_and_original_restore_path(tmp_path, content):
    path = tmp_path / 'owned.txt'
    path.write_bytes(content)
    with open(str(path) + ':Zone.Identifier', 'wb') as stream:
        stream.write(b'owned alternate stream')
    state = native.capture(str(path))
    receipt = native.recycle(state)
    try:
        assert not path.exists() and native.verify(receipt)
        assert receipt['identity']['file_id'] == receipt['recycled_identity']['file_id']
        assert receipt['identity']['streams_digest'] == receipt['recycled_identity']['streams_digest']
        assert native._receipt_path(receipt).is_file()
    finally:
        native.restore(receipt)
    assert native.verify(receipt, restored=True) and path.read_bytes() == content
    with open(str(path) + ':Zone.Identifier', 'rb') as stream:
        assert stream.read() == b'owned alternate stream'


def test_owned_worker_durable_manual_recycle_undo(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    path = tmp_path / 'owned-worker.txt'
    path.write_text('owned worker fixture', encoding='utf-8')
    cap = task(runtime, 'owned-recycle')
    result = runtime.tool_registry.execute('safe_delete', {'path': str(path)}, cap, runtime.ledger)
    assert result.ok and result.verified, result
    state = cap.undo_stack[-1]
    try:
        rows = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        assert len(rows) == 1 and json.loads(rows[0]['undo_json']) == state
        assert state['action'] == 'safe_delete' and native.verify(state)
        assert result.private_context == {} and 'private_context' not in result.model_dump()
        runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
        inverse = runtime.tool_registry.execute('undo_last', {}, task(runtime, 'undo-owned-recycle'), runtime.ledger)
        assert inverse.ok and inverse.verified, inverse
        assert path.read_text(encoding='utf-8') == 'owned worker fixture'
        assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id) == []
    finally:
        if not path.exists():
            native.restore(state)


@pytest.mark.parametrize('change', ['content', 'replacement'])
def test_recycle_refuses_changed_source_after_capture(tmp_path, change):
    path = tmp_path / 'owned'
    path.write_bytes(b'before')
    state = native.capture(str(path))
    if change == 'replacement':
        path.rename(tmp_path / 'original')
    path.write_bytes(b'new owner data')
    with pytest.raises(ValueError):
        native.recycle(state)
    assert path.read_bytes() == b'new owner data'


def test_recycle_refuses_cancelled_and_locked_target(tmp_path):
    path = tmp_path / 'owned'
    path.write_bytes(b'owned')
    state = native.capture(str(path))
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception):
        native.recycle(state, token)
    with native.identity._open(path):
        with pytest.raises(Exception):
            native.recycle(state)
    assert path.read_bytes() == b'owned'


def test_recycle_refuses_unrecyclable_volume_before_transfer(tmp_path, monkeypatch):
    path = tmp_path / 'owned'
    path.write_bytes(b'owned')
    def unsupported(*args):
        raise ValueError('Unsupported volume fixture')
    monkeypatch.setattr(native, '_volume', unsupported)
    assert not execute_safe_delete({'path': str(path)}).ok
    assert path.read_bytes() == b'owned'


def test_recycle_refuses_missing_and_linked_files(tmp_path):
    assert not execute_safe_delete({'path': str(tmp_path / 'missing')}).ok
    source = tmp_path / 'owned'
    source.write_bytes(b'owned')
    link = tmp_path / 'hard-link'
    link.hardlink_to(source)
    assert not execute_safe_delete({'path': str(link)}).ok
    assert source.read_bytes() == link.read_bytes() == b'owned'


def test_recycle_inverse_preserves_occupied_original_path(tmp_path):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'original fixture')
    state = native.recycle(native.capture(str(path)))
    try:
        path.write_bytes(b'new owner data')
        assert not RollbackRecipes().apply('safe_delete', state).ok
        assert path.read_bytes() == b'new owner data'
        assert native._receipt_path(state).read_bytes() == b'original fixture'
    finally:
        path.rename(tmp_path / 'new-owner-preserved.txt')
        native.restore(state)
    assert path.read_bytes() == b'original fixture'


def test_recycle_inverse_preserves_changed_recycled_item(tmp_path):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'original fixture')
    state = native.recycle(native.capture(str(path)))
    recycled = native._receipt_path(state)
    try:
        recycled.write_bytes(b'changed fixture')
        assert not RollbackRecipes().apply('safe_delete', state).ok
        assert not path.exists() and recycled.read_bytes() == b'changed fixture'
    finally:
        # Explicit fixture recovery, not a production inverse: restore bytes and
        # update the expected identity solely to remove our own test residue.
        recycled.write_bytes(b'original fixture')
        state['recycled_identity'] = native._copy_snapshot(recycled)
        state['identity'] = state['recycled_identity']
        native.restore(state)


def test_recycle_native_automatic_inverse_and_forged_success(tmp_path):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    result = execute_safe_delete({'path': str(path)})
    assert result.ok and result.verified, result
    assert not verify_safe_delete(ToolResult.success('safe_delete', data={'path': str(path)}, verified=True)).ok
    assert RollbackRecipes().apply('safe_delete', result.undo_record).ok
    assert path.read_bytes() == b'owned'


def test_recycle_policy_denial_preserves_file(runtime, tmp_path):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    cap = task(runtime, 'denied-recycle')
    result = runtime.tool_registry.execute('safe_delete', {'path': str(path)}, cap, runtime.ledger)
    assert not result.ok and path.read_bytes() == b'owned' and not cap.undo_stack


@pytest.mark.parametrize('args', [{'path': 'relative'}, {'path': 'C:\\owned\\*.txt'},
    {'path': 'C:\\owned\\file', 'permanent': True}, {'path': 'C:\\owned\\..\\file'}])
def test_recycle_strict_arguments_precede_policy(runtime, monkeypatch, args):
    decisions = approved(runtime, monkeypatch)
    cap = task(runtime, 'invalid-recycle')
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('safe_delete', args, cap, runtime.ledger)
    assert not cap.undo_stack
    assert decisions == []


def test_recycle_is_selected_for_file_plans(runtime):
    names = ToolSubsetSelector(runtime.tool_registry).select_schemas(RouteMode.SMART, command='delete file')
    assert 'safe_delete' in [spec['name'] for spec in names]


def test_recycle_restore_os_refuses_collision_after_precheck(tmp_path, monkeypatch):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    state = native.recycle(native.capture(str(path)))
    original = native._transfer
    def race(*args, **kwargs):
        path.write_bytes(b'new owner data')
        return original(*args, **kwargs)
    try:
        monkeypatch.setattr(native, '_transfer', race)
        assert not RollbackRecipes().apply('safe_delete', state).ok
        assert path.read_bytes() == b'new owner data'
        assert native._receipt_path(state).read_bytes() == b'owned'
    finally:
        monkeypatch.setattr(native, '_transfer', original)
        path.rename(tmp_path / 'owner-data-preserved.txt')
        native.restore(state)


def test_recycle_restore_refuses_changed_parent_identity(tmp_path):
    folder = tmp_path / 'folder'
    folder.mkdir()
    path = folder / 'owned.txt'
    path.write_bytes(b'owned')
    state = native.recycle(native.capture(str(path)))
    preserved = tmp_path / 'original-folder'
    folder.rename(preserved)
    folder.mkdir()
    try:
        assert not RollbackRecipes().apply('safe_delete', state).ok
        assert not path.exists() and native._receipt_path(state).exists()
    finally:
        folder.rmdir()  # Explicit empty fixture only.
        preserved.rename(folder)
        native.restore(state)


def receipt_fixture(args, context, *, receipt_path):
    result = execute_safe_delete(args, context)
    if result.ok:
        Path(receipt_path).write_text(json.dumps(result.undo_record), encoding='utf-8')
    return result


def test_recycle_failed_independent_proof_keeps_pending_intent(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    path, receipt = tmp_path / 'owned.txt', tmp_path / 'fixture-receipt.json'
    path.write_bytes(b'owned')
    spec = runtime.tool_registry.lookup('safe_delete')
    runtime.tool_registry.register(spec.model_copy(update={
        'executor': partial(receipt_fixture, receipt_path=str(receipt)),
        'verifier': contradict_fixture}), overwrite=True)
    cap = task(runtime, 'contradicted-recycle')
    result = runtime.tool_registry.execute('safe_delete', {'path': str(path)}, cap, runtime.ledger)
    try:
        assert not result.ok and not result.verified and result.undo_record is None
        assert not path.exists() and receipt.exists()
        rows = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        assert len(rows) == 1
        pending = json.loads(rows[0]['undo_json'])
        assert pending['action'] == 'pending_mutation' and pending['pre_state']['action'] == 'safe_delete'
        from pluma.memory.undo import claim_latest
        with pytest.raises(ValueError, match='Original executor absence'):
            claim_latest(str(runtime.paths.db_path), 'manual-must-not-race-live-owner')
        assert not path.exists() and native._receipt_path(json.loads(receipt.read_text(encoding='utf-8'))).exists()
        runtime.supervisor.finalize_task(cap.task_id, TaskState.FAILED)
        undo = runtime.tool_registry.execute('undo_last', {}, task(runtime, 'recover-recycle-intent'), runtime.ledger)
        assert undo.ok and undo.verified, undo
        assert path.read_bytes() == b'owned'
        assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    finally:
        if receipt.exists() and not path.exists():
            native.restore(json.loads(receipt.read_text(encoding='utf-8')))


def test_recycle_pre_latched_stop_prevents_native_mutation(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    cap = task(runtime, 'cancelled-recycle')
    cap.cancellation_token.cancel()
    try:
        result = runtime.tool_registry.execute('safe_delete', {'path': str(path)}, cap, runtime.ledger)
        assert not result.ok
    except Exception as error:
        from pluma.core.cancellation import TaskCancelledError
        assert isinstance(error, TaskCancelledError)
    assert path.read_bytes() == b'owned' and not cap.undo_stack


@pytest.mark.parametrize('nested', [False, True])
def test_native_folder_recycle_and_exact_tree_restore(tmp_path, nested):
    folder = tmp_path / 'owned-folder'
    folder.mkdir()
    if nested:
        child = folder / 'nested'
        child.mkdir()
        (child / 'owned.txt').write_bytes(b'owned tree content')
        with open(str(child / 'owned.txt') + ':private-stream', 'wb') as stream:
            stream.write(b'owned stream content')
    captured = native.capture(str(folder))
    try:
        receipt = native.recycle(captured)
        assert not folder.exists() and native.verify(receipt)
        assert receipt['identity']['tree_entries'] == (2 if nested else 0)
        native.restore(receipt)
        assert native.verify(receipt, restored=True)
        if nested:
            assert (folder / 'nested' / 'owned.txt').read_bytes() == b'owned tree content'
            with open(str(folder / 'nested' / 'owned.txt') + ':private-stream', 'rb') as stream:
                assert stream.read() == b'owned stream content'
    finally:
        if not folder.exists():
            native.recover_pending(captured)


def test_folder_recycle_refuses_changed_child_stream_before_mutation(tmp_path):
    folder = tmp_path / 'owned-folder'
    folder.mkdir()
    child = folder / 'owned'
    child.write_bytes(b'owned')
    state = native.capture(str(folder))
    with open(str(child) + ':owner-stream', 'wb') as stream:
        stream.write(b'newer owner data')
    with pytest.raises(ValueError):
        native.recycle(state)
    assert child.read_bytes() == b'owned'
    with open(str(child) + ':owner-stream', 'rb') as stream:
        assert stream.read() == b'newer owner data'


def test_folder_recycle_refuses_directory_streams_and_entry_overflow(tmp_path):
    folder = tmp_path / 'owned-folder'
    folder.mkdir()
    with open(str(folder) + ':owner-stream', 'wb') as stream:
        stream.write(b'directory stream')
    with pytest.raises(ValueError):
        native.capture(str(folder))
    assert folder.is_dir()
    other = tmp_path / 'over-bound'
    other.mkdir()
    for index in range(native.identity.MAX_TREE_ENTRIES + 1):
        (other / f'{index}.txt').write_bytes(b'')
    with pytest.raises(ValueError):
        native.capture(str(other))
    assert len(list(other.iterdir())) == native.identity.MAX_TREE_ENTRIES + 1


@pytest.mark.parametrize('effect', ['not_started', 'recycled', 'conflict'])
def test_pending_recovery_uses_native_identity_and_preserves_conflict(tmp_path, effect):
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    state = native.capture(str(path))
    receipt = None
    if effect != 'not_started':
        receipt = native.recycle(state)
    try:
        if effect == 'conflict':
            path.write_bytes(b'new owner data')
            with pytest.raises(ValueError):
                native.recover_pending(state)
            assert path.read_bytes() == b'new owner data'
            assert native._receipt_path(receipt).read_bytes() == b'owned'
        else:
            proof = native.recover_pending(state)
            assert proof['restored'] == (effect == 'recycled')
            assert path.read_bytes() == b'owned'
    finally:
        if effect == 'conflict':
            path.rename(tmp_path / 'new-owner-preserved.txt')
            native.restore(receipt)


def interrupted_recycle(args, context, *, marker):
    from pluma.tools.files import _captured_state, undo_builder_safe_delete
    state = _captured_state('safe_delete', args, context, undo_builder_safe_delete)
    native.recycle(state, context.cancellation_token)
    Path(marker).touch()
    time.sleep(30)  # No receipt crosses IPC. STOP must drain this owned worker.
    return ToolResult.failure('safe_delete', 'Owned interruption fixture unexpectedly continued.')


@pytest.mark.parametrize('folder', [False, True])
def test_stop_after_recycle_before_receipt_recovers_exact_intent(runtime, monkeypatch, tmp_path, folder):
    approved(runtime, monkeypatch)
    path = tmp_path / 'owned-target'
    if folder:
        path.mkdir()
        (path / 'owned.txt').write_bytes(b'owned')
    else:
        path.write_bytes(b'owned')
    original = native.capture(str(path))
    marker = tmp_path / 'entered'
    spec = runtime.tool_registry.lookup('safe_delete')
    runtime.tool_registry.register(spec.model_copy(update={
        'executor': partial(interrupted_recycle, marker=str(marker))}), overwrite=True)
    cap = task(runtime, 'stop-interrupted-recycle')
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(runtime.tool_registry.execute, 'safe_delete', {'path': str(path)}, cap, runtime.ledger)
        try:
            await_file(marker, future)
            assert not path.exists()
            assert cap.undo_stack[0]['action'] == 'pending_mutation'
            initial = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
            assert json.loads(initial['undo_json']) == cap.undo_stack[0]
            runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            stopped = runtime.supervisor.get_task(cap.task_id)
            result = future.result(3)
            assert not result.ok
            assert stopped.state == TaskState.STOPPED, json.dumps([item.model_dump() for item in stopped.cleanup_evidence])
            assert native._content(native._snapshot(path)) == native._content(original['identity'])
            assert not cap.undo_stack and not cap.inverse_workers
            assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
            assert any(item.code == 'INVERSE_WORKER_EXITED' and item.verified for item in cap.cleanup_evidence)
        finally:
            if not future.done():
                runtime.supervisor.stop_task(cap.task_id, grace_s=0)
            if not path.exists():
                native.recover_pending(original)


def blocked_inverse(args, context):
    time.sleep(30)
    return ToolResult.failure('undo_last', 'Owned inverse fixture unexpectedly continued.')


def test_owned_inverse_timeout_is_bounded_and_drained(runtime, monkeypatch, tmp_path):
    from pluma.rollback import owned
    approved(runtime, monkeypatch)
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    cap = task(runtime, 'bounded-inverse')
    state = native.capture(str(path))
    monkeypatch.setattr(owned, 'execute_inverse', blocked_inverse)
    started = time.monotonic()
    result = owned.apply_owned('safe_delete', state, cap, timeout_s=.3)
    assert not result.ok and time.monotonic() - started < 3
    assert not cap.inverse_workers and path.read_bytes() == b'owned'
    assert any(item.code == 'INVERSE_WORKER_EXITED' and item.verified for item in cap.cleanup_evidence)


def test_owned_inverse_retains_failed_cleanup_owner(runtime, monkeypatch, tmp_path):
    from pluma.rollback import owned
    from pluma.tools.registry import TaskWorkerController
    approved(runtime, monkeypatch)
    path = tmp_path / 'owned.txt'
    path.write_bytes(b'owned')
    state = native.recycle(native.capture(str(path)))
    cap = task(runtime, 'retained-inverse')
    dispose = TaskWorkerController.dispose_owned_worker
    def refuse_disposal(controller):
        raise RuntimeError('Owned disposal failure fixture')
    monkeypatch.setattr(TaskWorkerController, 'dispose_owned_worker', refuse_disposal)
    try:
        result = owned.apply_owned('safe_delete', state, cap)
        assert not result.ok and cap.inverse_workers
        assert path.read_bytes() == b'owned'
        assert any(item.code == 'INVERSE_WORKER_PENDING' and not item.verified for item in cap.cleanup_evidence)
    finally:
        monkeypatch.setattr(TaskWorkerController, 'dispose_owned_worker', dispose)
        checks = cap.close_resources(stopping=True)
        cap.cleanup_evidence.extend(checks)
        assert not cap.inverse_workers
