"""Fault injection: retain a real selected claim until its owned worker is stopped."""
from pathlib import Path
import time


def claim_and_wait(args, context):
    from pluma.memory.undo import claim_latest
    claim_latest(context.storage_path, context.task_id, selected=args['selection'])
    marker = Path(context.storage_path).parent / ('p20-claimed-' + context.task_id + '.marker')
    marker.write_text(context.task_id, encoding='ascii')
    # Deliberately unresponsive fixture: production STOP must prove owned absence.
    time.sleep(10)
    raise RuntimeError('Owned inverse fixture was not stopped.')
