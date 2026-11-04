"""Opt-in diagnostics in disposable-host owned folder workers only."""
import atexit
import faulthandler
import os
from pathlib import Path
import sys

root=os.environ.get('PLUMA_P20_FOLDER_TRACE_ROOT')
if root and os.environ.get('GITHUB_ACTIONS')=='true' and '--multiprocessing-fork' in sys.argv:
    root=Path(root)
    if not root.is_dir() or not root.name.startswith('PLUMA-P16-'):
        raise RuntimeError('An owned native fixture directory is required.')
    stream=(root/('folder-stack-'+str(os.getpid())+'.txt')).open('x',encoding='utf-8')
    faulthandler.dump_traceback_later(1,repeat=True,file=stream)
    def finish():
        faulthandler.cancel_dump_traceback_later();stream.close()
    atexit.register(finish)
