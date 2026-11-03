"""COM fault fixtures, not native Explorer acceptance; no desktop is accessed."""
import sys
from types import SimpleNamespace

import pytest

from pluma.adapters import folder_view as native
from pluma.core.cancellation import CancellationToken, TaskCancelledError
from pluma.tools import system


@pytest.fixture
def com(tmp_path, monkeypatch):
    state = SimpleNamespace(rows=[{'url': tmp_path.as_uri(), 'visible': True}],
        alive={}, uninit_live=[], metadata=[], calls=[], creations=0, fail_create=False, cancel_on_count=None)

    class Raw:
        def __init__(self, kind, row=None):
            self.kind, self.row = kind, row
            state.alive[id(self)] = kind

        def __del__(self):
            state.alive.pop(id(self), None)

        def GetTypeInfo(self):
            state.metadata.append(self.kind)
            if self.kind == 'window':
                raise TimeoutError('Owned fixture: returned window type information does not answer.')
            return None

        def GetIDsOfNames(self, name):
            return name

        def Invoke(self, name, lcid, flags, wanted, *args):
            assert lcid == 0 and wanted
            state.calls.append((self.kind, name, args))
            if name in ('Explore', 'Windows', 'Item'):
                assert flags == 1
            else:
                assert flags == 2
            if name == 'Explore': return None
            if name == 'Windows': return Raw('collection')
            if name == 'Count':
                if state.cancel_on_count is not None: state.cancel_on_count.cancel()
                return len(state.rows)
            if name == 'Item': return Raw('window', state.rows[args[0]])
            if name == 'LocationURL':
                if self.row.get('error'): raise OSError('Owned COM property unavailable.')
                return self.row['url']
            if name == 'Visible': return self.row['visible']
            raise AssertionError('Unexpected fixture COM operation: ' + name)

    def create(*args):
        state.creations += 1
        if state.fail_create: raise OSError('Owned Shell activation refused.')
        return Raw('shell')

    # Model pywin32's automatic wrapper: returned Item IDispatch objects cause
    # GetTypeInfo before the caller can read the actual folder properties.
    class Automatic:
        def __init__(self, raw): self.raw = raw
        def __getattr__(self, name):
            if name in ('Explore', 'Windows', 'Item'):
                def call(*args):
                    value = self.raw.Invoke(name, 0, 1, True, *args)
                    if isinstance(value, Raw):
                        value.GetTypeInfo()
                        return Automatic(value)
                    return value
                return call
            return self.raw.Invoke(name, 0, 2, True)

    api = SimpleNamespace(CoInitialize=lambda: None,
        CoUninitialize=lambda: state.uninit_live.append(len(state.alive)),
        CoCreateInstance=create, CLSCTX_SERVER=21, IID_IDispatch='fixture:IDispatch',
        DISPATCH_METHOD=1, DISPATCH_PROPERTYGET=2)
    client = SimpleNamespace(Dispatch=lambda *args: Automatic(create()))
    monkeypatch.setitem(sys.modules, 'pythoncom', api)
    monkeypatch.setitem(sys.modules, 'win32com', SimpleNamespace(client=client))
    monkeypatch.setitem(sys.modules, 'win32com.client', client)
    return state


def test_folder_observation_does_not_request_blocked_type_information(com, tmp_path):
    token = CancellationToken()
    assert native.open_view(str(tmp_path), token) == {'path': str(tmp_path), 'visible': True}
    assert native.verify_view(str(tmp_path)) is True
    assert not com.metadata
    assert com.creations == 2  # The verifier observes afresh, not a cached result.
    assert com.uninit_live == [0, 0] and not com.alive
    assert sum(name == 'Explore' for _, name, _ in com.calls) == 1


@pytest.mark.parametrize('change', ['hidden', 'different', 'unavailable'])
def test_saved_success_cannot_replace_independent_folder_readback(com, tmp_path, change):
    result = system.execute_open_folder({'path': str(tmp_path)}, SimpleNamespace(cancellation_token=CancellationToken()))
    assert result.ok and not result.verified
    if change == 'hidden': com.rows[0]['visible'] = False
    if change == 'different': com.rows[0]['url'] = tmp_path.parent.as_uri()
    if change == 'unavailable': com.rows[0]['error'] = True
    verified = system.verify_open_folder(result)
    assert not verified.ok
    assert com.uninit_live == [0, 0] and not com.alive


def test_oversized_window_enumeration_refuses_and_releases_com(com, tmp_path):
    com.rows *= 257
    with pytest.raises(ValueError): native.open_view(str(tmp_path), CancellationToken())
    assert not any(name == 'Item' for _, name, _ in com.calls)
    assert com.uninit_live == [0] and not com.alive


def test_failed_shell_activation_cannot_report_opened_folder(com, tmp_path):
    com.fail_create = True
    result = system.execute_open_folder({'path': str(tmp_path)}, SimpleNamespace(cancellation_token=CancellationToken()))
    assert not result.ok and not result.verified and result.error_code == 'FOLDER_VIEW_UNVERIFIED'
    assert not result.data and com.uninit_live == [0]


def test_stop_before_native_dispatch_does_not_create_shell(com, tmp_path):
    token = CancellationToken()
    token.cancel()
    with pytest.raises(TaskCancelledError): native.open_view(str(tmp_path), token)
    assert not com.creations and not com.calls and not com.alive


def test_stop_during_readback_prevents_next_com_request_and_releases_refs(com, tmp_path):
    token = CancellationToken()
    com.cancel_on_count = token
    with pytest.raises(TaskCancelledError): native.open_view(str(tmp_path), token)
    assert not any(name == 'Item' for _, name, _ in com.calls)
    assert com.uninit_live == [0] and not com.alive
