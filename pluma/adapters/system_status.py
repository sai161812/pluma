"""On-demand Windows resource/interface snapshots; no resident monitoring."""
from __future__ import annotations

import math
import os
import re
import sys
import time


def decode_system_status(raw: dict) -> dict:
    counts = ('disk_free_bytes', 'disk_total_bytes', 'ram_available_bytes', 'ram_total_bytes')
    if set(raw) != set(counts + ('os', 'python_version', 'disk_root', 'cpu_percent', 'cpu_sample_seconds')):
        raise ValueError('Invalid resource observation fields.')
    for key in counts:
        if type(raw[key]) is not int or raw[key] < 0:
            raise ValueError('Invalid native resource size.')
    for prefix, available in (('disk', 'disk_free_bytes'), ('ram', 'ram_available_bytes')):
        if raw[prefix + '_total_bytes'] <= 0 or raw[available] > raw[prefix + '_total_bytes']:
            raise ValueError('Inconsistent native resource sizes.')
    for key in ('cpu_percent', 'cpu_sample_seconds'):
        if type(raw[key]) not in (float, int) or not math.isfinite(raw[key]):
            raise ValueError('Invalid native CPU sample.')
    if not 0 <= raw['cpu_percent'] <= 100 or raw['cpu_sample_seconds'] <= 0:
        raise ValueError('Invalid native CPU sample.')
    if (not isinstance(raw['disk_root'], str) or not re.fullmatch(r'[A-Za-z]:\\', raw['disk_root'])
            or any(not isinstance(raw[key], str) or not 0 < len(raw[key]) <= 2048 for key in ('os', 'python_version'))):
        raise ValueError('Invalid native system identity.')
    return {
        'os': raw['os'], 'python_version': raw['python_version'], 'disk_root': raw['disk_root'],
        'cpu_percent': float(raw['cpu_percent']), 'cpu_sample_seconds': float(raw['cpu_sample_seconds']),
        'disk_free_gb': round(raw['disk_free_bytes'] / 1024**3, 1),
        'disk_total_gb': round(raw['disk_total_bytes'] / 1024**3, 1),
        'ram_free_gb': round(raw['ram_available_bytes'] / 1024**3, 1),
        'ram_total_gb': round(raw['ram_total_bytes'] / 1024**3, 1),
        'memory_load_percent': round(100 * (1 - raw['ram_available_bytes'] / raw['ram_total_bytes']), 1),
        'native_metrics': dict(raw),
    }


def _system_drive():
    import ctypes
    from ctypes import wintypes
    read = ctypes.WinDLL('kernel32', use_last_error=True).GetWindowsDirectoryW
    read.argtypes = [wintypes.LPWSTR, wintypes.UINT]
    read.restype = wintypes.UINT
    value = ctypes.create_unicode_buffer(32768)
    length = read(value, len(value))
    if not 0 < length < len(value):
        raise OSError('Windows directory could not be observed.')
    drive = os.path.splitdrive(value.value)[0]
    if not re.fullmatch(r'[A-Za-z]:', drive):
        raise OSError('Windows system volume is unsupported.')
    return drive + '\\'


def read_system_status():
    if sys.platform != 'win32':
        raise NotImplementedError
    import platform
    import psutil
    root = _system_drive()
    disk, ram = psutil.disk_usage(root), psutil.virtual_memory()
    started = time.monotonic()
    cpu = psutil.cpu_percent(interval=.1)
    elapsed = time.monotonic() - started
    return decode_system_status({
        'os': platform.platform(), 'python_version': platform.python_version(), 'disk_root': root,
        'disk_free_bytes': disk.free, 'disk_total_bytes': disk.total,
        'ram_available_bytes': ram.available, 'ram_total_bytes': ram.total,
        'cpu_percent': cpu, 'cpu_sample_seconds': elapsed,
    })


def read_network_status(max_entries):
    if sys.platform != 'win32':
        raise NotImplementedError
    import psutil
    stats = psutil.net_if_stats()
    entries = []
    for name, item in sorted(stats.items())[:max_entries]:
        if type(item.isup) is not bool or type(item.mtu) is not int or item.mtu < 0:
            raise ValueError('Invalid native interface state.')
        speed = item.speed
        if type(speed) not in (int, float) or not math.isfinite(speed) or speed < 0:
            raise ValueError('Invalid native link speed.')
        entries.append({'name': name, 'is_up': item.isup, 'mtu': item.mtu,
                        'link_speed_mbps': float(speed) if speed else None})
    return {'interfaces': entries, 'observed_count': len(stats), 'max_entries': max_entries,
            'truncated': len(stats) > len(entries), 'internet_connectivity': None}
