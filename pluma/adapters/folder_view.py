"""User-requested Shell folder view. Never owns or terminates Explorer itself."""
from pathlib import Path
import time


def _location(window, uri):
    try:
        return str(window.LocationURL).casefold().rstrip('/') == uri.casefold().rstrip('/') and bool(window.Visible)
    except Exception:
        return False


def open_view(path, token):
    from pluma.adapters.commands import _literal_path
    import pythoncom
    import win32com.client
    folder = _literal_path(path)
    if not folder.is_dir():
        raise ValueError('The recorded folder is unavailable.')
    uri = folder.as_uri()
    pythoncom.CoInitialize()
    try:
        shell = win32com.client.Dispatch('Shell.Application')
        token.raise_if_cancelled()
        shell.Explore(str(folder))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            token.raise_if_cancelled()
            windows = shell.Windows()
            if windows.Count > 256:
                raise ValueError('Folder view enumeration exceeds its bound.')
            for index in range(windows.Count):
                if _location(windows.Item(index), uri):
                    return {'path': str(folder), 'visible': True}
            time.sleep(.05)
        raise ValueError('Folder view was not observed.')
    finally:
        pythoncom.CoUninitialize()


def verify_view(path):
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    try:
        windows = win32com.client.Dispatch('Shell.Application').Windows()
        return windows.Count <= 256 and any(_location(windows.Item(index), Path(path).as_uri()) for index in range(windows.Count))
    finally:
        pythoncom.CoUninitialize()
