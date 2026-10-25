"""On-demand Win32 power observation, with no device work at import/startup."""
from __future__ import annotations

import sys


def decode_power_status(raw: dict) -> dict:
    """Interpret documented unsigned bytes/unknown sentinels without guessing."""
    byte_keys = ('ac_line', 'battery_flags', 'percent', 'battery_saver')
    second_keys = ('remaining_seconds', 'full_seconds')
    if set(raw) != set(byte_keys + second_keys):
        raise ValueError('Invalid native power fields.')
    for key in byte_keys + second_keys:
        limit = 255 if key in byte_keys else 0xffffffff
        if type(raw[key]) is not int or not 0 <= raw[key] <= limit:
            raise ValueError('Invalid native power value.')
    ac, flags, percent = raw['ac_line'], raw['battery_flags'], raw['percent']
    if ac not in (0, 1, 255) or (percent > 100 and percent != 255):
        raise ValueError('Invalid native power status.')
    if flags != 255 and flags != 128 and flags & ~15:
        raise ValueError('Invalid native battery flags.')
    present = None if flags == 255 else flags != 128
    charging = None if present is None else bool(present and flags & 8)
    def seconds(key):
        value = raw[key]
        return None if value == 0xffffffff or ac == 1 or present is False else value
    return {
        'ac_connected': None if ac == 255 else ac == 1,
        'has_battery': present,
        'percent': None if percent == 255 or present is False else percent,
        'charging': charging,
        'battery_saver': bool(raw['battery_saver']) if raw['battery_saver'] in (0, 1) else None,
        'remaining_seconds': seconds('remaining_seconds'),
        'full_seconds': seconds('full_seconds'),
        'native_status': dict(raw),
    }


def read_battery_status() -> dict:
    if sys.platform != 'win32':
        raise NotImplementedError('Native Windows power status is unavailable.')
    import ctypes
    from ctypes import wintypes

    class SystemPowerStatus(ctypes.Structure):
        _fields_ = [('ACLineStatus', wintypes.BYTE), ('BatteryFlag', wintypes.BYTE),
                    ('BatteryLifePercent', wintypes.BYTE), ('SystemStatusFlag', wintypes.BYTE),
                    ('BatteryLifeTime', wintypes.DWORD), ('BatteryFullLifeTime', wintypes.DWORD)]

    read = ctypes.WinDLL('kernel32', use_last_error=True).GetSystemPowerStatus
    read.argtypes = [ctypes.POINTER(SystemPowerStatus)]
    read.restype = wintypes.BOOL
    value = SystemPowerStatus()
    if not read(ctypes.byref(value)):
        raise OSError('Native power status could not be read.')
    return decode_power_status({
        'ac_line': int(value.ACLineStatus), 'battery_flags': int(value.BatteryFlag),
        'percent': int(value.BatteryLifePercent), 'battery_saver': int(value.SystemStatusFlag),
        'remaining_seconds': int(value.BatteryLifeTime), 'full_seconds': int(value.BatteryFullLifeTime),
    })
