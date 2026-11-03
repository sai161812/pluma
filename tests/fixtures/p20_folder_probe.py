"""Opt-in stage evidence for the owned disposable-host folder fixture only."""
from contextlib import contextmanager
from dataclasses import dataclass
import json
import os
from pathlib import Path
import threading
import time
from unittest.mock import patch


class Trace:
    def __init__(self, path):
        self.path, self.count = Path(path), 0

    def emit(self, stage):
        if self.count >= 1000:
            return
        self.count += 1
        with self.path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'stage': stage, 'pid': os.getpid(),
                'thread': threading.get_ident(), 'seconds': round(time.perf_counter(), 6)}) + '\n')

    def call(self, stage, function, *args, **kwargs):
        self.emit(stage + '.enter')
        try:
            result = function(*args, **kwargs)
        except BaseException:
            self.emit(stage + '.error')
            raise
        self.emit(stage + '.return')
        return result


class Window:
    def __init__(self, value, trace):
        self.value, self.trace = value, trace

    @property
    def LocationURL(self):
        return self.trace.call('window.LocationURL', lambda: self.value.LocationURL)

    @property
    def Visible(self):
        return self.trace.call('window.Visible', lambda: self.value.Visible)


class Windows:
    def __init__(self, value, trace):
        self.value, self.trace = value, trace

    @property
    def Count(self):
        return self.trace.call('windows.Count', lambda: self.value.Count)

    def Item(self, index):
        return Window(self.trace.call('windows.Item', lambda: self.value.Item(index)), self.trace)


class Shell:
    def __init__(self, value, trace):
        self.value, self.trace = value, trace

    def Explore(self, path):
        return self.trace.call('shell.Explore', lambda: self.value.Explore(path))

    def Windows(self):
        return Windows(self.trace.call('shell.Windows', lambda: self.value.Windows()), self.trace)


@contextmanager
def traced(path):
    trace = Trace(path)
    trace.emit('imports.enter')
    import pythoncom
    import win32com.client
    trace.emit('imports.return')
    initialize, uninitialize = pythoncom.CoInitialize, pythoncom.CoUninitialize
    dispatch = win32com.client.Dispatch
    def traced_dispatch(*args, **kwargs):
        value = trace.call('Dispatch', dispatch, *args, **kwargs)
        return Shell(value, trace) if args and args[0] == 'Shell.Application' else value
    with patch.object(pythoncom, 'CoInitialize', lambda: trace.call('CoInitialize', initialize)), \
            patch.object(pythoncom, 'CoUninitialize', lambda: trace.call('CoUninitialize', uninitialize)), \
            patch.object(win32com.client, 'Dispatch', traced_dispatch):
        yield trace


@dataclass
class FolderExecute:
    trace_path: str

    def __call__(self, args, context):
        with traced(self.trace_path) as trace:
            from pluma.tools.system import execute_open_folder
            return trace.call('executor', execute_open_folder, args, context)


@dataclass
class FolderVerify:
    trace_path: str

    def __call__(self, result):
        with traced(self.trace_path) as trace:
            from pluma.tools.system import verify_open_folder
            return trace.call('verifier', verify_open_folder, result)
