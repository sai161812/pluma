"""Console-free Windows spawn for PLUMA-owned workers, without global patches.

The bootstrap follows CPython's multiprocessing.popen_spawn_win32.Popen (3.12,
PSF license); only process creation flags and failed-bootstrap cleanup differ.
Containment, identity and admission remain owned by TaskWorkerController.
"""
import multiprocessing
import sys


if sys.platform == "win32":
    import _winapi
    import msvcrt
    import os
    import subprocess
    from multiprocessing import context, reduction, spawn, util
    from multiprocessing.popen_spawn_win32 import Popen, WINENV, _close_handles, _path_eq

    class _NoConsolePopen(Popen):
        def __init__(self, process_obj):
            preparation = spawn.get_preparation_data(process_obj._name)
            read_handle, write_handle = _winapi.CreatePipe(None, 0)
            descriptor = msvcrt.open_osfhandle(write_handle, 0)
            command = spawn.get_command_line(parent_pid=os.getpid(), pipe_handle=read_handle)
            executable = spawn.get_executable()
            environment = None
            if WINENV and _path_eq(executable, sys.executable):
                command[0] = executable = sys._base_executable
                environment = os.environ.copy()
                environment["__PYVENV_LAUNCHER__"] = sys.executable
            command = " ".join('"%s"' % value for value in command)
            with open(descriptor, "wb", closefd=True) as to_child:
                try:
                    handle, thread, pid, _ = _winapi.CreateProcess(executable, command, None, None,
                        False, subprocess.CREATE_NO_WINDOW, environment, None, None)
                    _winapi.CloseHandle(thread)
                except BaseException:
                    _winapi.CloseHandle(read_handle)
                    raise
                self.pid = pid
                self.returncode = None
                self._handle = handle
                self.sentinel = int(handle)
                self.finalizer = util.Finalize(self, _close_handles, (self.sentinel, int(read_handle)))
                context.set_spawning_popen(self)
                try:
                    reduction.dump(preparation, to_child)
                    reduction.dump(process_obj, to_child)
                except BaseException:
                    # Startup failed before Process.start can retain its Popen.
                    # Drain this original handle, never a potentially reused PID.
                    _winapi.TerminateProcess(handle, 1)
                    _winapi.WaitForSingleObject(handle, 1000)
                    self.finalizer()
                    raise
                finally:
                    context.set_spawning_popen(None)

    class _WorkerProcess(context.SpawnProcess):
        @staticmethod
        def _Popen(process_obj):
            return _NoConsolePopen(process_obj)

    class _WorkerContext(context.SpawnContext):
        Process = _WorkerProcess


def worker_context():
    return _WorkerContext() if sys.platform == "win32" else multiprocessing.get_context("spawn")
