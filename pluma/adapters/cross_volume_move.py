"""Cross-volume regular-file move using verified native copy and recycle recovery."""
from contextlib import ExitStack
import os
from pathlib import Path

from pluma.adapters import file_identity as identity, file_operations as files, recycle_bin as recycle


def capture(source, destination):
    copied = files.capture_copy(source, destination)
    if copied['source_parent']['volume'] == copied['destination_parent']['volume']:
        raise ValueError('Cross-volume adapter requires distinct volumes.')
    recovered = recycle.capture(source)
    if recovered['identity'] != copied['identity']:
        raise ValueError('Source changed during move capture.')
    return {'action': 'move_file', 'guard_version': 1, 'cross_volume': True,
        'source': source, 'destination': destination, 'copy': copied, 'recycle': recovered}


def apply(state, token=None):
    # CopyFileEx refuses an occupied destination and proves the created native ID,
    # all stream bytes and source stability before source removal is attempted.
    copied = files.copy_file(state['copy'], token)
    recovered = recycle.recycle(state['recycle'], token)
    receipt = dict(state, copy_receipt=copied, recycle_receipt=recovered)
    if not verify(receipt):
        raise ValueError('Cross-volume move postcondition did not read back.')
    return receipt


def _destination(state):
    copied = state['copy_receipt']
    destination = identity._checked_path(copied['destination'])
    with ExitStack() as held:
        for parent in reversed(destination.parents):
            handle = held.enter_context(identity._open(parent, parent=True))
        if identity._parent_identity(handle) != copied['destination_parent']:
            return False
        return files._copy_snapshot(destination) == copied['created_identity']


def verify(state, *, restored=False):
    if (state.get('guard_version') != 1 or state.get('action') != 'move_file' or state.get('cross_volume') is not True
            or state['source'] != state['copy']['source'] or state['source'] != state['recycle']['path']
            or state['destination'] != state['copy']['destination']):
        return False
    copied, recovered = state['copy_receipt'], state['recycle_receipt']
    if any(copied.get(key) != value for key, value in state['copy'].items()) or any(
            recovered.get(key) != value for key, value in state['recycle'].items()):
        return False
    if restored:
        return not os.path.lexists(state['destination']) and recycle.verify(recovered, restored=True)
    return (_destination(state) and recycle.verify(recovered)
        and all(copied['identity'][key] == copied['created_identity'][key]
                for key in ('digest', 'size_bytes', 'streams_digest')))


def restore(state):
    # Preflight BOTH paths and the exact Bin item before mutating either path.
    # Restore the original before removing the exact owned copy. If a later race
    # prevents copy cleanup, both copies remain; no data-loss rollback is guessed.
    if not verify(state):
        raise ValueError('Cross-volume undo conflicts with newer content or parent identity.')
    recycle.restore(state['recycle_receipt'])
    files.restore_copy(state['copy_receipt'])
    if not verify(state, restored=True):
        raise ValueError('Cross-volume inverse was not verified.')
