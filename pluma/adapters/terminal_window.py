"""Open the fixed Windows PowerShell executable; never type or run commands."""
from pathlib import Path
import uuid

from pluma.adapters import file_identity as files
from pluma.adapters.commands import windows_directory, _literal_path


def capture(args, context):
    context.cancellation_token.raise_if_cancelled()
    image = windows_directory() / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    cwd = _literal_path(str(Path.home()))
    with files._open(cwd, parent=True) as handle:
        directory = files._parent_identity(handle)
    return {'action': 'app_launch', 'guard_version': 1, 'non_undoable': True, 'tool': 'open_terminal',
        'app_name': 'windows_powershell', 'launch_id': str(uuid.uuid4()),
        'argv': [str(image), '-NoLogo', '-NoProfile'], 'cwd': str(cwd),
        'image_identity': files.snapshot(image), 'directory_identity': directory,
        'environment_class': 'system_terminal'}
