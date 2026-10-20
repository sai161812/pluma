"""Real owned file/folder moves and inverse conflicts, without user targets."""
import json
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
