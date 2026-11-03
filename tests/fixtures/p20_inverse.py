"""Fault injection: retain a real selected claim until its owned worker is stopped."""
from pathlib import Path
import time


def claim_and_wait(args, context):
    from pluma.memory.undo import claim_latest
    claim_latest(context.storage_path, context.task_id, selected=args['selection'])
    marker = Path(context.storage_path).parent / ('p20-claimed-' + context.task_id + '.marker')
    # Publish the synchronization marker only after its payload is complete.
    # Observing file creation during write_text used to expose an empty marker.
    pending = marker.with_suffix('.pending')
    with pending.open('x', encoding='ascii') as stream:
        stream.write(context.task_id)
    pending.rename(marker)
    # Deliberately unresponsive fixture: production STOP must prove owned absence.
    time.sleep(10)
    raise RuntimeError('Owned inverse fixture was not stopped.')
