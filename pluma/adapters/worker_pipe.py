"""Bounded parent-side Windows message-pipe I/O, with no helper threads.

The child uses multiprocessing's normal wire format. Keep native overlapped
operations here so the registry never depends on Win32 I/O implementation.
"""
from __future__ import annotations

import ctypes
from multiprocessing.reduction import ForkingPickler
import threading
import time


class WorkerIOCancelled(Exception):
    """The owning task stopped while a pipe operation was pending."""


class WorkerPipe:
    POLL_S = 0.02
    DRAIN_S = 0.2

    def __init__(self, connection, stopped):
        self.connection = connection
        self.stopped = stopped
        self._operation = threading.Lock()
        self._pending = None

    def _check(self, deadline):
        if self.stopped():
            raise WorkerIOCancelled()
        if time.monotonic() >= deadline:
            raise TimeoutError("Worker pipe deadline expired.")

    def _drain(self, deadline):
        import _winapi
        ov = self._pending
        if ov is None:
            return
        ov.cancel()
        milliseconds = max(0, int((deadline - time.monotonic()) * 1000))
        if _winapi.WaitForSingleObject(ov.event, milliseconds) != _winapi.WAIT_OBJECT_0:
            # Retain both OVERLAPPED and connection for explicit cleanup retry.
            raise RuntimeError("Owned worker pipe cancellation did not drain.")
        ov.GetOverlappedResult(False)
        self._pending = None

    def _complete(self, ov, error, deadline):
        import _winapi
        self._pending = ov
        try:
            if error == _winapi.ERROR_IO_PENDING:
                while True:
                    self._check(deadline)
                    milliseconds = max(1, int(min(self.POLL_S, deadline - time.monotonic()) * 1000))
                    state = _winapi.WaitForSingleObject(ov.event, milliseconds)
                    if state == _winapi.WAIT_OBJECT_0:
                        break
                    if state != _winapi.WAIT_TIMEOUT:
                        raise OSError("Worker pipe wait failed.")
            count, error = ov.GetOverlappedResult(False)
            self._pending = None
            return count, error
        finally:
            if self._pending is not None:
                self._drain(time.monotonic() + self.DRAIN_S)

    def send(self, message, deadline):
        import _winapi
        # Only registered callables and validated request data reach this pipe.
        data = ForkingPickler.dumps(message)
        with self._operation:
            self._check(deadline)
            ov, error = _winapi.WriteFile(self.connection.fileno(), data, overlapped=True)
            count, error = self._complete(ov, error, deadline)
            if error:
                raise ctypes.WinError(error)
            if count != len(data):
                raise OSError("Incomplete worker request write.")

    def poll(self, timeout):
        with self._operation:
            return self.connection.poll(timeout)

    def recv(self, deadline):
        import _winapi
        with self._operation:
            self._check(deadline)
            ov, error = _winapi.ReadFile(self.connection.fileno(), 128, overlapped=True)
            _, error = self._complete(ov, error, deadline)
            data = ov.getbuffer()
            if error == _winapi.ERROR_MORE_DATA:
                remaining = _winapi.PeekNamedPipe(self.connection.fileno())[1]
                self._check(deadline)
                ov, error = _winapi.ReadFile(self.connection.fileno(), remaining, overlapped=True)
                _, error = self._complete(ov, error, deadline)
                data += ov.getbuffer()
            if error:
                raise ctypes.WinError(error)
            return ForkingPickler.loads(data)

    def close(self):
        deadline = time.monotonic() + self.DRAIN_S
        if not self._operation.acquire(timeout=self.DRAIN_S):
            raise RuntimeError("Owned worker pipe operation is still active.")
        try:
            self._drain(deadline)
            self.connection.close()
        finally:
            self._operation.release()
