"""Opt-in stack capture in owned disposable-host Python fixture processes."""
import atexit
import faulthandler
import os
import sys
from pathlib import Path


root = os.environ.get('PLUMA_P20_FOLDER_TRACE_ROOT')
if root and '--multiprocessing-fork' in sys.argv:
    root = Path(root)
    if not root.is_dir() or not root.name.startswith('PLUMA-P16-'):
        raise RuntimeError('An owned P20 fixture directory is required for stack capture.')
    stream = (root / ('folder-stack-' + str(os.getpid()) + '.txt')).open('x', encoding='utf-8')
    faulthandler.dump_traceback_later(1, repeat=True, file=stream)
    def finish():
        faulthandler.cancel_dump_traceback_later()
        stream.close()
    atexit.register(finish)
