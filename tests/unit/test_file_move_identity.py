"""Real owned file/folder moves and inverse conflicts, without user targets."""
import json
import os
from pathlib import Path

import pytest

from pluma.adapters import file_identity
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.tools.registry import ToolArgumentError
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@pytest.mark.parametrize('directory', [False, True])
@pytest.mark.parametrize('tool', ['move_file', 'rename_file'])
def test_native_move_or_rename_has_usable_durable_identity_guarded_undo(runtime, monkeypatch, tmp_path, directory, tool):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'before', tmp_path / 'after'
    if directory:
        source.mkdir()
        (source / 'child').mkdir()
        (source / 'child' / 'owned.txt').write_text('owned nested fixture', encoding='utf-8')
    else:
        source.write_text('owned file fixture', encoding='utf-8')
    before = file_identity.snapshot(str(source))
    original = task(runtime, 'owned-native-move')
    args = {'source': str(source), 'destination': str(destination)} if tool == 'move_file' else {
        'path': str(source), 'new_name': destination.name}
    result = runtime.tool_registry.execute(tool, args, original, runtime.ledger)
    assert result.ok and result.verified and not source.exists() and destination.exists()
    assert file_identity.snapshot(str(destination)) == before
    record = ActivityQuery(runtime.db).available_undo_records_for_task(original.task_id)[0]
    assert json.loads(record['undo_json'])['identity'] == before
    assert '[REDACTED]' not in record['undo_json']
    runtime.supervisor.finalize_task(original.task_id, TaskState.SUCCEEDED)
    undo = task(runtime, 'owned-native-undo')
    result = runtime.tool_registry.execute('undo_last', {}, undo, runtime.ledger)
    assert result.ok and result.verified and source.exists() and not destination.exists()
    assert file_identity.snapshot(str(source)) == before
    assert ActivityQuery(runtime.db).available_undo_records_for_task(original.task_id) == []


@pytest.mark.parametrize('change', ['content', 'identity', 'source_collision'])
def test_native_file_inverse_refuses_owner_changes_without_touching_either_target(runtime, monkeypatch, tmp_path, change):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'before', tmp_path / 'after'
    source.write_text('owned original', encoding='utf-8')
    cap = task(runtime)
    result = runtime.tool_registry.execute('move_file', {'source': str(source), 'destination': str(destination)}, cap, runtime.ledger)
    assert result.ok
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    if change == 'identity':
        destination.unlink()
        destination.write_text('owned original', encoding='utf-8')
    elif change == 'content':
        destination.write_text('owner edit', encoding='utf-8')
    else:
        source.write_text('new owner file', encoding='utf-8')
    observed_source = source.read_bytes() if source.exists() else None
    observed_destination = destination.read_bytes()
    undo = task(runtime, 'owned-conflicting-file-undo')
    refused = runtime.tool_registry.execute('undo_last', {}, undo, runtime.ledger)
    assert not refused.ok and not refused.verified
    assert (source.read_bytes() if source.exists() else None) == observed_source
    assert destination.read_bytes() == observed_destination
    assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)


def test_parent_replacement_between_capture_and_dispatch_is_refused(tmp_path):
    source = tmp_path / 'owned-source'
    source.write_text('owned', encoding='utf-8')
    parent = tmp_path / 'destination'
    parent.mkdir()
    destination = parent / 'target'
    captured = file_identity.capture(str(source), str(destination))
    parent.rename(tmp_path / 'original-destination')
    parent.mkdir()
    with pytest.raises(ValueError, match='parent directory was replaced'):
        file_identity.move(str(source), str(destination), captured['identity'],
            parents=(captured['source_parent'], captured['destination_parent']))
    assert source.read_text(encoding='utf-8') == 'owned' and not destination.exists()


@pytest.mark.parametrize('arguments', [
    {'path': 'relative.txt', 'new_name': 'valid.txt'},
    {'path': r'C:\owned.txt', 'new_name': 'stream:payload'},
    {'path': r'C:\owned.txt', 'new_name': 'trailing.'},
])
def test_rename_invalid_targets_fail_before_policy(runtime, arguments):
    cap = task(runtime)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute('rename_file', arguments, cap, runtime.ledger)
    assert cap.worker_controller is None


@pytest.mark.parametrize('component', ['executor', 'verifier'])
def test_file_info_required_worker_refuses_unserializable_callable(runtime, monkeypatch, tmp_path, component):
    path = tmp_path / 'owned.txt'
    path.write_text('owned', encoding='utf-8')
    called = []
    spec = runtime.tool_registry.lookup('file_info')
    monkeypatch.setattr(spec, component, lambda value: called.append(True))
    cap = task(runtime)
    result = runtime.tool_registry.execute('file_info', {'path': str(path)}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'PROCESS_ISOLATION_FAILED'
    assert not called and cap.worker_controller is None


@pytest.mark.parametrize('directory', [False, True])
@pytest.mark.parametrize('tool', ['move_file', 'rename_file'])
def test_inverse_refuses_alternate_stream_edit_even_when_primary_timestamp_is_restored(runtime, monkeypatch, tmp_path, directory, tool):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'before', tmp_path / 'after'
    if directory:
        source.mkdir()
        payload = source / 'owned.txt'
    else:
        payload = source
    payload.write_bytes(b'unchanged primary content')
    with open(str(payload) + ':owned-stream', 'wb') as stream:
        stream.write(b'original alternate content')
    cap = task(runtime)
    args = {'source': str(source), 'destination': str(destination)} if tool == 'move_file' else {
        'path': str(source), 'new_name': destination.name}
    result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
    assert result.ok and result.verified, result
    payload = destination / 'owned.txt' if directory else destination
    previous = payload.stat()
    with open(str(payload) + ':owned-stream', 'wb') as stream:
        stream.write(b'newer owner alternate content')
    os.utime(payload, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    from pluma.rollback.recipes import RollbackRecipes
    inverse = RollbackRecipes().apply(tool, cap.undo_stack[-1])
    assert not inverse.ok and inverse.error == 'ROLLBACK_CONFLICT'
    assert not source.exists() and destination.exists()
    with open(str(payload) + ':owned-stream', 'rb') as stream:
        assert stream.read() == b'newer owner alternate content'


@pytest.mark.parametrize('tool', ['move_file', 'rename_file', 'copy_file', 'create_folder'])
def test_guarded_filesystem_automatic_inverse_is_owned_and_drained(runtime, monkeypatch, tmp_path, tool):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'before', tmp_path / 'after'
    if tool != 'create_folder':
        source.write_bytes(b'owned fixture')
    args = {'source': str(source), 'destination': str(destination)}
    if tool == 'rename_file': args = {'path': str(source), 'new_name': destination.name}
    if tool == 'create_folder': args = {'path': str(destination)}
    cap = task(runtime)
    result = runtime.tool_registry.execute(tool, args, cap, runtime.ledger)
    assert result.ok and result.verified, result
    rolled = runtime.rollback_engine.rollback_task(cap.task_id, memory_undo_stack=cap.undo_stack)
    assert rolled.all_ok and not destination.exists(), rolled
    if tool != 'create_folder': assert source.read_bytes() == b'owned fixture'
    assert not cap.inverse_workers
    checks = [entry for entry in cap.cleanup_evidence if entry.identity.get('command_class') == 'rollback_worker']
    assert checks and all(entry.verified for entry in checks)
    assert all(entry.identity['task_id'] == cap.task_id and entry.identity['creation_time'] > 0 for entry in checks)


def test_directory_stream_refuses_before_rename(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'before', tmp_path / 'after'
    source.mkdir()
    with open(str(source) + ':owned-stream', 'wb') as stream:
        stream.write(b'preserved directory metadata')
    cap = task(runtime)
    result = runtime.tool_registry.execute('rename_file', {'path': str(source), 'new_name': destination.name}, cap, runtime.ledger)
    assert not result.ok and result.error_code == 'UNDO_PRESTATE_FAILED'
    assert source.is_dir() and not destination.exists() and not cap.undo_stack
    with open(str(source) + ':owned-stream', 'rb') as stream:
        assert stream.read() == b'preserved directory metadata'


def test_move_stream_size_bound_is_checked_before_content_read(tmp_path, monkeypatch):
    source, destination = tmp_path / 'before', tmp_path / 'after'
    source.write_bytes(b'owned')
    with open(str(source) + ':owned-stream', 'wb') as stream:
        stream.write(b'bounded alternate stream')
    monkeypatch.setattr(file_identity, 'MAX_FILE_BYTES', 8)
    with pytest.raises(ValueError, match='streams exceed'):
        file_identity.capture(str(source), str(destination))
    assert source.read_bytes() == b'owned' and not destination.exists()


def test_stream_read_does_not_weaken_original_delete_guard(tmp_path):
    source, destination = tmp_path / 'before', tmp_path / 'after'
    source.write_bytes(b'owned primary')
    with open(str(source) + ':owned-stream', 'wb') as stream:
        stream.write(b'owned alternate')
    with file_identity._open(source, delete=True) as handle:
        observed = file_identity._observe(handle, source, include_streams=True)
        assert observed['streams_digest']
        with pytest.raises(PermissionError):
            source.rename(destination)
    assert source.read_bytes() == b'owned primary' and not destination.exists()


def test_guarded_inverse_timeout_drains_only_its_owned_worker(runtime, monkeypatch, tmp_path):
    from pluma.rollback.owned import apply_owned
    from pluma.tools import registry
    from tests.unit.test_worker_cancellation import OwnedProbe
    import time
    approved(runtime, monkeypatch)
    original = registry.TaskWorkerController
    class BlockedInverse(original):
        def execute_call(self, executor, args, request, timeout_s, **kwargs):
            return super().execute_call(OwnedProbe(str(tmp_path)), args, request, timeout_s, **kwargs)
    monkeypatch.setattr(registry, 'TaskWorkerController', BlockedInverse)
    cap = task(runtime)
    started = time.perf_counter()
    outcome = apply_owned('copy_file', {'action': 'copy_file'}, cap, timeout_s=1)
    assert not outcome.ok and time.perf_counter() - started < 3
    assert (tmp_path / 'entered').exists() and not (tmp_path / 'late').exists()
    assert not cap.inverse_workers
    checks = [entry for entry in cap.cleanup_evidence if entry.identity.get('command_class') == 'rollback_worker']
    assert checks and all(entry.verified for entry in checks)
