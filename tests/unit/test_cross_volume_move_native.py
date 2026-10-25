"""Native C:/D: owned regular-file moves, safe recycle recovery and conflicts."""
from contextlib import contextmanager
import json
from pathlib import Path
import uuid

import pytest

from pluma.adapters import cross_volume_move as native, recycle_bin
from pluma.core.task_supervisor import TaskState
from pluma.core.cancellation import CancellationToken
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@contextmanager
def cross_paths(tmp_path):
    source = tmp_path / 'source.txt'
    workspace = Path.cwd().resolve()
    directory = workspace / 'output' / ('p11-move-' + str(uuid.uuid4()))
    assert directory.parent == workspace / 'output' and directory.is_absolute()
    directory.mkdir()
    destination = directory / 'destination.txt'
    try:
        # Required native evidence, never silently replaced by a same-volume mock.
        assert tmp_path.stat().st_dev != directory.stat().st_dev
        yield source, destination
    finally:
        # Exact fixture files only; no recursive deletion or unrelated paths.
        if destination.exists(): destination.unlink()
        directory.rmdir()


@pytest.mark.parametrize('inverse', ['manual', 'automatic'])
@pytest.mark.parametrize('content', [b'', 'Owned cross-volume Unicode \u2713'.encode()], ids=['empty', 'unicode'])
def test_native_cross_volume_move_readback_and_undo(runtime, monkeypatch, tmp_path, inverse, content):
    approved(runtime, monkeypatch)
    with cross_paths(tmp_path) as (source, destination):
        source.write_bytes(content)
        with open(str(source) + ':fixture-stream', 'wb') as stream: stream.write(b'Owned alternate bytes')
        cap = task(runtime)
        state = None
        try:
            result = runtime.tool_registry.execute('move_file', {'source': str(source), 'destination': str(destination)}, cap, runtime.ledger)
            assert result.ok and result.verified, result
            state = cap.undo_stack[-1]
            assert state['cross_volume'] and not source.exists() and destination.read_bytes() == content
            assert native.verify(state)
            assert state['copy']['identity']['volume'] != state['copy_receipt']['created_identity']['volume']
            assert json.loads(ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]['undo_json']) == state
            with open(str(destination) + ':fixture-stream', 'rb') as stream: assert stream.read() == b'Owned alternate bytes'
            if inverse == 'manual':
                runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
                undo = runtime.tool_registry.execute('undo_last', {}, task(runtime), runtime.ledger)
                assert undo.ok and undo.verified, undo
            else:
                runtime.supervisor.request_stop(cap.task_id)
                assert cap.terminal_ready.wait(8)
                assert cap.state == TaskState.STOPPED, cap.stop_error
                assert not cap.inverse_workers
            assert native.verify(state, restored=True) and source.read_bytes() == content
            assert not ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
        finally:
            if not source.exists():
                pending = next((item.get('pre_state', item) for item in cap.undo_stack
                    if item.get('pre_state', item).get('cross_volume')), None)
                if state: recycle_bin.restore(state['recycle_receipt'])
                elif pending: recycle_bin.recover_pending(pending['recycle'])


@pytest.mark.parametrize('changed', ['destination', 'stream', 'source'])
def test_cross_volume_inverse_preserves_newer_content(tmp_path, changed):
    with cross_paths(tmp_path) as (source, destination):
        source.write_bytes(b'Original fixture data')
        state = native.apply(native.capture(str(source), str(destination)))
        try:
            if changed == 'destination': destination.write_bytes(b'Newer fixture data')
            if changed == 'stream':
                with open(str(destination) + ':newer', 'wb') as stream: stream.write(b'Newer alternate data')
            if changed == 'source': source.write_bytes(b'Newer occupied source')
            before = destination.read_bytes()
            assert not RollbackRecipes().apply('move_file', state).ok
            assert destination.read_bytes() == before
            if changed == 'source': assert source.read_bytes() == b'Newer occupied source'
        finally:
            if source.exists(): source.unlink()  # exact test-created conflicting path
            recycle_bin.restore(state['recycle_receipt'])


def test_cross_volume_changed_source_or_occupied_destination_refuses(tmp_path):
    with cross_paths(tmp_path) as (source, destination):
        source.write_bytes(b'Original fixture')
        state = native.capture(str(source), str(destination))
        source.write_bytes(b'Newer fixture')
        with pytest.raises(ValueError): native.apply(state)
        assert source.read_bytes() == b'Newer fixture' and not destination.exists()
        state = native.capture(str(source), str(destination))
        destination.write_bytes(b'Existing destination fixture')
        with pytest.raises(OSError): native.apply(state)
        assert source.read_bytes() == b'Newer fixture' and destination.read_bytes() == b'Existing destination fixture'


def test_cross_volume_stop_before_copy_leaves_source_untouched(tmp_path):
    with cross_paths(tmp_path) as (source, destination):
        source.write_bytes(b'Original owned fixture')
        state = native.capture(str(source), str(destination))
        token = CancellationToken(); token.cancel()
        with pytest.raises(Exception): native.apply(state, token)
        assert source.read_bytes() == b'Original owned fixture' and not destination.exists()


def test_secondary_stream_reader_preserves_primary_delete_guard(tmp_path):
    source = tmp_path / 'guarded.txt'
    source.write_bytes(b'Owned primary')
    with open(str(source) + ':fixture', 'wb') as stream: stream.write(b'Owned alternate')
    with native.identity._open(source, delete=True) as handle:
        native.files._copy_observe(handle, source)
        with pytest.raises(OSError): source.rename(tmp_path / 'outside-rename')
    assert source.read_bytes() == b'Owned primary'
