"""Native owned fixtures for bounded file copy, folder reads and creation undo."""
import json
from functools import partial

import pytest

from pluma.adapters import file_operations as native
from pluma.brain.schemas import RouteMode
from pluma.brain.tool_subset import ToolSubsetSelector
from pluma.core.cancellation import CancellationToken
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery
from pluma.rollback.recipes import RollbackRecipes
from pluma.tools.files import execute_copy_file, execute_create_folder, execute_list_folder, verify_list_folder
from pluma.tools.registry import ToolArgumentError
from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult
from tests.unit.test_mutation_journal import EmptyArgs
from tests.unit.test_memory_tools import approved
from tests.unit.test_runtime_shutdown import runtime, task


@pytest.mark.parametrize('content', ['', 'owned Unicode fixture: తెలుగు café', 'x' * 1048576], ids=['empty', 'unicode', 'one-mib'])
def test_native_copy_receipt_and_durable_manual_undo(runtime, monkeypatch, tmp_path, content):
    approved(runtime, monkeypatch)
    source, destination = tmp_path / 'source.txt', tmp_path / 'copied.txt'
    source.write_text(content, encoding='utf-8')
    original = source.read_bytes()
    cap = task(runtime, 'owned-file-copy')
    result = runtime.tool_registry.execute('copy_file', {'source': str(source), 'destination': str(destination)}, cap, runtime.ledger)
    assert result.ok and result.verified, result
    assert source.read_bytes() == destination.read_bytes() == original
    record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
    state = json.loads(record['undo_json'])
    assert state['created_identity'] == cap.undo_stack[-1]['created_identity']
    assert state['created_identity']['file_id'] != state['identity']['file_id']
    assert result.private_context == {} and 'private_context' not in result.model_dump()
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    undo = task(runtime, 'undo-owned-copy')
    result = runtime.tool_registry.execute('undo_last', {}, undo, runtime.ledger)
    assert result.ok and result.verified, result
    assert source.read_bytes() == original and not destination.exists()
    assert ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id) == []


@pytest.mark.parametrize('change', ['content', 'replacement'])
def test_copy_inverse_preserves_newer_owner_state(tmp_path, change):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.write_text('owned fixture', encoding='utf-8')
    result = execute_copy_file({'source': str(source), 'destination': str(target)})
    assert result.ok and result.verified
    if change == 'replacement':
        target.rename(tmp_path / 'original-output')
    target.write_text('new owner content', encoding='utf-8')
    assert not RollbackRecipes().apply('copy_file', result.undo_record).ok
    assert target.read_text(encoding='utf-8') == 'new owner content'
    assert source.read_text(encoding='utf-8') == 'owned fixture'


def test_copy_refuses_capture_and_dispatch_collisions(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.write_text('source', encoding='utf-8')
    state = native.capture_copy(str(source), str(target))
    target.write_text('owner collision', encoding='utf-8')
    with pytest.raises((OSError, ValueError)):
        native.copy_file(state)
    assert target.read_text(encoding='utf-8') == 'owner collision'
    assert not execute_copy_file({'source': str(source), 'destination': str(target)}).ok


def test_native_copy_preserves_alternate_stream_and_inverse_refuses_newer_stream_edit(tmp_path):
    source, target = tmp_path / 'source', tmp_path / 'target'
    source.write_bytes(b'owned main stream')
    with open(str(source) + ':Zone.Identifier', 'wb') as stream:
        stream.write(b'owned alternate stream fixture')
    result = execute_copy_file({'source': str(source), 'destination': str(target)})
    assert result.ok and result.verified, result
    with open(str(target) + ':Zone.Identifier', 'rb') as stream:
        assert stream.read() == b'owned alternate stream fixture'
    with open(str(target) + ':Zone.Identifier', 'wb') as stream:
        stream.write(b'owner changed alternate stream')
    assert not RollbackRecipes().apply('copy_file', result.undo_record).ok
    assert target.read_bytes() == b'owned main stream'
    with open(str(target) + ':Zone.Identifier', 'rb') as stream:
        assert stream.read() == b'owner changed alternate stream'


@pytest.mark.parametrize('existing', [False, True])
def test_folder_receipt_and_durable_manual_undo(runtime, monkeypatch, tmp_path, existing):
    approved(runtime, monkeypatch)
    target = tmp_path / 'new-parent' / 'new-child'
    if existing:
        target.mkdir(parents=True)
        (target / 'owner.txt').write_text('preserve', encoding='utf-8')
    cap = task(runtime, 'owned-folder-creation')
    result = runtime.tool_registry.execute('create_folder', {'path': str(target)}, cap, runtime.ledger)
    assert result.ok and result.verified, result
    record = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)[0]
    state = json.loads(record['undo_json'])
    assert len(state['created']) == (0 if existing else 2)
    runtime.supervisor.finalize_task(cap.task_id, TaskState.SUCCEEDED)
    undo = runtime.tool_registry.execute('undo_last', {}, task(runtime, 'owned-folder-undo'), runtime.ledger)
    assert undo.ok and undo.verified, undo
    assert target.exists() == existing
    assert target.parent.exists() == existing
    if existing:
        assert (target / 'owner.txt').read_text(encoding='utf-8') == 'preserve'


@pytest.mark.parametrize('conflict', ['nonempty', 'replacement'])
def test_folder_inverse_refuses_owner_content_or_replacement(tmp_path, conflict):
    target = tmp_path / 'created'
    result = execute_create_folder({'path': str(target)})
    assert result.ok
    if conflict == 'replacement':
        target.rename(tmp_path / 'original')
        target.mkdir()
    else:
        (target / 'owner.txt').write_text('owner', encoding='utf-8')
    assert not RollbackRecipes().apply('create_folder', result.undo_record).ok
    assert target.is_dir()
    if conflict == 'nonempty':
        assert (target / 'owner.txt').read_text(encoding='utf-8') == 'owner'


def test_folder_does_not_adopt_directory_created_after_capture(tmp_path):
    target = tmp_path / 'raced'
    state = native.capture_folder(str(target), True)
    target.mkdir()
    with pytest.raises(FileExistsError):
        native.create_folder(state)
    assert target.is_dir()


def test_list_folder_native_bound_readback_and_changed_entry(tmp_path):
    for name in ('alpha.txt', 'beta.txt', 'γ.txt'):
        (tmp_path / name).write_text('owned', encoding='utf-8')
    result = execute_list_folder({'path': str(tmp_path), 'max_entries': 2})
    assert result.ok and result.verified and verify_list_folder(result).ok
    assert result.data['count'] == 2 and result.data['has_more']
    false_extent = result.model_copy(update={'data': dict(result.data, has_more=False)})
    assert not verify_list_folder(false_extent).ok
    assert all(set(row) == {'name', 'kind', 'file_id', 'device', 'size_bytes', 'modified_ns'} for row in result.data['entries'])
    (tmp_path / result.data['entries'][0]['name']).write_text('newer owner data', encoding='utf-8')
    assert not verify_list_folder(result).ok
    full = execute_list_folder({'path': str(tmp_path), 'max_entries': 200})
    assert full.ok and full.verified and full.data['count'] == 3 and not full.data['has_more']


def test_list_folder_required_worker_and_history(runtime, monkeypatch, tmp_path):
    approved(runtime, monkeypatch)
    (tmp_path / 'owned.txt').write_text('not returned as content', encoding='utf-8')
    cap = task(runtime)
    result = runtime.tool_registry.execute('list_folder', {'path': str(tmp_path)}, cap, runtime.ledger)
    assert result.ok and result.verified and result.private_context == {}
    assert cap.worker_controller is not None
    rows = ActivityQuery(runtime.db).actions_for_task(cap.task_id)
    assert len(rows) == 1 and rows[0]['verified']
    assert 'not returned as content' not in json.dumps(rows)


@pytest.mark.parametrize('tool,args', [
    ('copy_file', {'source': 'relative', 'destination': 'D:\\owned'}),
    ('copy_file', {'source': 'D:\\owned', 'destination': 'D:\\other', 'overwrite': True}),
    ('create_folder', {'path': 'relative'}),
    ('create_folder', {'path': 'D:\\owned', 'exist_ok': 'yes'}),
    ('list_folder', {'path': 'D:\\owned', 'max_entries': 201}),
])
def test_new_file_schemas_refuse_before_policy(runtime, monkeypatch, tool, args):
    decisions = approved(runtime, monkeypatch)
    with pytest.raises(ToolArgumentError):
        runtime.tool_registry.execute(tool, args, task(runtime), runtime.ledger)
    assert decisions == []


def test_cancellation_before_copy_or_folder_write_preserves_target_absence(tmp_path):
    source, copy, folder = tmp_path / 'source', tmp_path / 'copy', tmp_path / 'folder'
    source.write_text('owned', encoding='utf-8')
    token = CancellationToken()
    token.cancel()
    with pytest.raises(Exception):
        native.copy_file(native.capture_copy(str(source), str(copy)), token)
    with pytest.raises(Exception):
        native.create_folder(native.capture_folder(str(folder), True), token)
    assert not copy.exists() and not folder.exists()


def test_copy_file_and_routine_file_hints_keep_required_registered_tools():
    selector = ToolSubsetSelector()
    assert 'copy_file' in selector.get_tool_names_for_route(RouteMode.SMART, 'copy this file')
    assert 'list_folder' in selector.get_tool_names_for_route(RouteMode.SMART, 'list that folder')
    assert 'run_routine' in selector.get_tool_names_for_route(RouteMode.SMART, 'run my folder routine')
    assert 'clipboard_read' in selector.get_tool_names_for_route(RouteMode.SMART, 'copy this file to clipboard')


def receipt_capture(args):
    return {'action': 'owned_receipt_probe', 'captured_value': 'before'}


def receipt_executor(args, context, *, variant):
    receipt = dict(receipt_capture(args), created_identity=[1, 2, 3])
    if variant in ('changed', 'changed_with_backup'):
        receipt['captured_value'] = 'replaced'
    elif variant == 'omitted':
        receipt.pop('captured_value')
    return ToolResult.success('owned_receipt_probe', factual_message='Inert receipt fixture.', undo_record=receipt,
        data={'preserved_destination_backup': 'inert-backup'} if variant == 'changed_with_backup' else {})


def receipt_verifier(result):
    return VerifyResult(ok=True, method='inert_fixture', detail='Inert fixture allows registry invariant check.')


@pytest.mark.parametrize('variant', ['extended', 'changed', 'omitted', 'changed_with_backup'])
def test_registry_receipt_can_extend_but_never_replace_captured_prestate(runtime, monkeypatch, variant):
    approved(runtime, monkeypatch)
    runtime.tool_registry.register(ToolSpec(name='owned_receipt_probe', description='Inert receipt fixture',
        args_schema=EmptyArgs, risk_class=RiskClass.LOW, timeout_s=5, process_isolated=True,
        executor=partial(receipt_executor, variant=variant), undo_builder=receipt_capture, verifier=receipt_verifier))
    cap = task(runtime)
    result = runtime.tool_registry.execute('owned_receipt_probe', {}, cap, runtime.ledger)
    rows = ActivityQuery(runtime.db).available_undo_records_for_task(cap.task_id)
    assert len(rows) == 1
    if variant == 'extended':
        assert result.ok and result.verified
        assert json.loads(rows[0]['undo_json']) == dict(receipt_capture({}), created_identity=[1, 2, 3])
    else:
        assert not result.ok and not result.verified and result.error_code == 'UNDO_RECEIPT_INVALID'
        assert not result.verify_detail.ok
        pending = json.loads(rows[0]['undo_json'])
        assert pending['action'] == 'pending_mutation' and pending['pre_state'] == receipt_capture({})
