"""Lazy Windows Core Audio adapter. No audio capture, playback or idle COM work."""
from __future__ import annotations

import sys


def _with_com(operation, *args):
    if sys.platform != "win32":
        raise NotImplementedError("Core Audio requires Windows.")
    import comtypes
    import pycaw  # dependency presence is required even if submodules were cached
    comtypes.CoInitialize()
    try:
        # Interface wrappers belong to the inner call and are released before
        # this apartment's matching CoUninitialize. Only ordinary data escapes.
        return operation(*args)
    finally:
        comtypes.CoUninitialize()


def _enumerator():
    import comtypes
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator
    return comtypes.CoCreateInstance(CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
                                     comtypes.CLSCTX_INPROC_SERVER)


def _volume(level=None, mute=None, expected_endpoint=None):
    import comtypes
    from pycaw.api.endpointvolume import IAudioEndpointVolume
    enumerator = device = volume = None
    try:
        enumerator = _enumerator()
        device = enumerator.GetDefaultAudioEndpoint(0, 1)  # render, multimedia
        identity = device.GetId()
        if expected_endpoint is not None and identity != expected_endpoint:
            raise ValueError("Audio endpoint identity changed.")
        volume = device.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_INPROC_SERVER, None)
        volume = volume.QueryInterface(IAudioEndpointVolume)
        if level is not None:
            volume.SetMasterVolumeLevelScalar(level / 100.0, None)
        if mute is not None:
            volume.SetMute(int(mute), None)
        scalar = float(volume.GetMasterVolumeLevelScalar())
        muted = bool(volume.GetMute())
        if device.GetState() != 1 or enumerator.GetDefaultAudioEndpoint(0, 1).GetId() != identity:
            raise ValueError("Audio endpoint changed during the operation.")
        return dict(endpoint_id=identity, volume=int(round(scalar * 100)),
                    scalar=scalar, muted=muted, is_mock=False)
    finally:
        enumerator = device = volume = None


def read_volume():
    return _with_com(_volume)


def set_volume(level=None, mute=None, expected_endpoint=None):
    return _with_com(_volume, level, mute, expected_endpoint)


def _devices(max_entries, context):
    from _ctypes import COMError
    import comtypes
    from pycaw.api.mmdeviceapi import IMMEndpoint
    from pycaw.api.mmdeviceapi.depend import PROPERTYKEY
    enumerator = collection = device = store = value = None
    try:
        enumerator = _enumerator()
        collection = enumerator.EnumAudioEndpoints(2, 15)  # both flows, all states
        count = collection.GetCount()
        devices = []
        key = PROPERTYKEY(comtypes.GUID('{a45c254e-df1c-4efd-8020-67d146a850e0}'), 14)
        for i in range(min(count, max_entries)):
            token = getattr(context, 'cancellation_token', None)
            if token is not None:
                token.raise_if_cancelled()
            device = collection.Item(i)
            identity = device.GetId()
            state = device.GetState()
            flow = device.QueryInterface(IMMEndpoint).GetDataFlow()
            name = None
            # A missing display name is an explicit unavailable property. Identity,
            # state and flow must succeed; none is replaced with an invented device.
            try:
                store = device.OpenPropertyStore(0)
                value = store.GetValue(key)
                try:
                    candidate = value.GetValue()
                    if isinstance(candidate, str) and candidate:
                        name = candidate
                finally:
                    value.clear()
            except (OSError, COMError):
                pass
            if device.GetId() != identity or device.GetState() != state:
                raise ValueError("Audio device changed during enumeration.")
            devices.append(dict(endpoint_id=identity, name=name, state=state,
                                flow={0: 'render', 1: 'capture'}[flow]))
        return dict(devices=devices, observed_device_count=count, truncated=count > len(devices))
    finally:
        enumerator = collection = device = store = value = None


def list_devices(max_entries, context=None):
    return _with_com(_devices, max_entries, context)
