"""User-requested Shell folder view. Never owns or terminates Explorer itself."""
from pathlib import Path
import time


def _invoke(dispatch, name, flags, *args):
    """Use IDispatch directly; auto-wrapping asks every returned window for type info.

    Explorer can block that metadata RPC while a view is initializing. None of
    the fixed operations here needs a type library or a generated Python class.
    """
    try:
        member = dispatch.GetIDsOfNames(name)
        return dispatch.Invoke(member, 0, flags, True, *args)
    finally:
        dispatch = None  # Exception tracebacks must not retain apartment proxies.


def _shell(api):
    return api.CoCreateInstance('Shell.Application', None, api.CLSCTX_SERVER, api.IID_IDispatch)


def _location(window, uri, api):
    try:
        location = _invoke(window, 'LocationURL', api.DISPATCH_PROPERTYGET)
        return (isinstance(location, str) and location.casefold().rstrip('/') == uri.casefold().rstrip('/')
                and _invoke(window, 'Visible', api.DISPATCH_PROPERTYGET) is True)
    except Exception:
        return False
    finally:
        window = None


def _visible(shell, uri, api, token=None):
    windows = window = None
    try:
        windows = _invoke(shell, 'Windows', api.DISPATCH_METHOD)
        count = _invoke(windows, 'Count', api.DISPATCH_PROPERTYGET)
        if type(count) is not int or not 0 <= count <= 256:
            raise ValueError('Folder view enumeration exceeds its bound.')
        for index in range(count):
            if token is not None: token.raise_if_cancelled()
            window = _invoke(windows, 'Item', api.DISPATCH_METHOD, index)
            if _location(window, uri, api): return True
            window = None
        return False
    finally:
        window = windows = shell = None


def _open(folder, token, api):
    shell = None
    try:
        token.raise_if_cancelled()
        shell = _shell(api)
        token.raise_if_cancelled()
        _invoke(shell, 'Explore', api.DISPATCH_METHOD, str(folder))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            token.raise_if_cancelled()
            if _visible(shell, folder.as_uri(), api, token):
                return {'path': str(folder), 'visible': True}
            time.sleep(.05)
        raise ValueError('Folder view was not observed.')
    finally:
        shell = None


def open_view(path, token):
    token.raise_if_cancelled()
    from pluma.adapters.commands import _literal_path
    import pythoncom
    folder = _literal_path(path)
    if not folder.is_dir():
        raise ValueError('The recorded folder is unavailable.')
    pythoncom.CoInitialize()
    try:
        return _open(folder, token, pythoncom)
    finally:
        pythoncom.CoUninitialize()


def _verify(path, api):
    shell = None
    try:
        shell = _shell(api)
        return _visible(shell, Path(path).as_uri(), api)
    finally:
        shell = None


def verify_view(path):
    import pythoncom
    pythoncom.CoInitialize()
    try:
        return _verify(path, pythoncom)
    finally:
        pythoncom.CoUninitialize()
