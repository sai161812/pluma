"""pluma.core.resident — Resident process, hotkeys and tray entry.

Spec §5.1 Resident Core: "Hotkeys, voice trigger, STOP, IPC, request creation,
runtime lifecycle, task state. Must not load heavy ML at startup."
"""

import logging
import sys
import threading
from typing import Any, Dict, Optional

from pluma.core.ipc import IpcServer
from pluma.core.ownership import OwnershipRegistry
from pluma.core.task_supervisor import TaskSupervisor

logger = logging.getLogger(__name__)

# Hotkey identifiers
HOTKEY_ID_TEXT = 1
HOTKEY_ID_STOP = 2


class ResidentCore:
    """Resident process coordinating IPC, Task Supervisor, and global hotkeys."""

    def __init__(self) -> None:
        self.registry = OwnershipRegistry()
        self.supervisor = TaskSupervisor(ownership_registry=self.registry)
        self.ipc = IpcServer(command_handler=self.handle_ipc_command)
        
        self._hotkey_thread: Optional[threading.Thread] = None
        self._running = False

    def handle_ipc_command(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """Process incoming IPC commands."""
        cmd = req.get("command")
        if cmd == "stop_all":
            self.supervisor.stop_all_active_tasks()
            return {"status": "ok", "message": "All active tasks stopped."}
        elif cmd == "stop_task":
            tid = req.get("task_id")
            if tid:
                self.supervisor.stop_task(tid)
                return {"status": "ok", "message": f"Task {tid} stopped."}
            return {"status": "error", "message": "Missing task_id"}
        elif cmd == "status":
            return {"status": "ok", "message": "Resident core running"}
        
        return {"status": "error", "message": f"Unknown command: {cmd}"}

    def _run_crash_recovery(self) -> None:
        """Scan for unfinished tasks from previous run and clean up.
        
        Spec §13: "On PLUMA startup, stale tasks are marked ABORTED and 
        residual temp metadata is checked."
        """
        # In a complete implementation, this queries the local SQLite ledger
        # for tasks left in RUNNING state, transitions them to ABORTED_BY_CRASH,
        # and calls self.registry.cleanup_task_resources(tid).
        logger.info("Running startup crash recovery...")
        pass

    def _hotkey_loop(self) -> None:
        """Windows message loop for global hotkeys."""
        if sys.platform != "win32":
            return
            
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        
        # MOD_ALT = 0x0001, MOD_CONTROL = 0x0002, MOD_WIN = 0x0008
        # Register Win+Alt+P (Text)
        if not user32.RegisterHotKey(None, HOTKEY_ID_TEXT, 0x0008 | 0x0001, 0x50):
            logger.warning("Failed to register Text hotkey (Win+Alt+P)")
            
        # Register Ctrl+Alt+S (STOP)
        if not user32.RegisterHotKey(None, HOTKEY_ID_STOP, 0x0002 | 0x0001, 0x53):
            logger.warning("Failed to register STOP hotkey (Ctrl+Alt+S)")

        msg = wintypes.MSG()
        # GetMessageW blocks until a message is received
        while self._running:
            bRet = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if bRet <= 0:
                break
                
            if msg.message == 0x0312:  # WM_HOTKEY
                if msg.wParam == HOTKEY_ID_STOP:
                    logger.info("Global STOP hotkey triggered!")
                    self.supervisor.stop_all_active_tasks()
                elif msg.wParam == HOTKEY_ID_TEXT:
                    logger.info("Global Text hotkey triggered! (stub)")
            
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterHotKey(None, HOTKEY_ID_TEXT)
        user32.UnregisterHotKey(None, HOTKEY_ID_STOP)

    def start(self) -> None:
        """Start the resident core and its background workers."""
        self._run_crash_recovery()
        self.ipc.start()
        
        self._running = True
        if sys.platform == "win32":
            self._hotkey_thread = threading.Thread(target=self._hotkey_loop, daemon=True, name="HotkeyThread")
            self._hotkey_thread.start()

    def stop(self) -> None:
        """Stop the resident core and IPC server."""
        self._running = False
        self.ipc.stop()
        
        if sys.platform == "win32" and self._hotkey_thread and self._hotkey_thread.is_alive():
            # Send a dummy message to wake up GetMessageW so it can exit
            import ctypes
            user32 = ctypes.WinDLL("user32")
            # WM_QUIT = 0x0012
            user32.PostThreadMessageW(self._hotkey_thread.ident, 0x0012, 0, 0)
            self._hotkey_thread.join(timeout=1.0)
