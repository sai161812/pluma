"""pluma.core.ipc — Local-only named-pipe IPC contract.

Spec §18: "Windows named pipe or equivalent local-only IPC."
Spec §25: "All local IPC must be bound to the user/local machine."
Implemented in Phase 1.
"""

import json
import logging
import os
import threading
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def get_pipe_name() -> str:
    """Return a user-specific named pipe address."""
    import sys
    username = os.environ.get("USERNAME", "default")
    if sys.platform == "win32":
        return rf"\\.\pipe\pluma_ipc_{username}"
    # Fallback for non-Windows tests
    return f"/tmp/pluma_ipc_{username}.sock"


class IpcServer:
    """Named-pipe IPC server for local command dispatch."""

    def __init__(self, command_handler: Callable[[Dict[str, Any]], Dict[str, Any]], address: Optional[str] = None) -> None:
        self.address = address or get_pipe_name()
        self._command_handler = command_handler
        self._listener: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the IPC server in a daemon thread."""
        from multiprocessing.connection import Listener
        try:
            self._listener = Listener(self.address)
        except Exception as e:
            logger.error("Failed to start IPC server at %s: %s", self.address, e)
            return

        self._running = True
        self._thread = threading.Thread(target=self._serve, name="PlumaIpcServer", daemon=True)
        self._thread.start()
        logger.info("IPC Server started at %s", self.address)

    def _serve(self) -> None:
        while self._running:
            try:
                if not self._listener:
                    break
                conn = self._listener.accept()
                with conn:
                    msg_bytes = conn.recv_bytes()
                    try:
                        req = json.loads(msg_bytes.decode("utf-8"))
                        resp = self._command_handler(req)
                        conn.send_bytes(json.dumps(resp).encode("utf-8"))
                    except Exception as e:
                        logger.error("Error processing IPC message: %s", e)
                        conn.send_bytes(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))
            except EOFError:
                pass
            except Exception as e:
                if self._running:
                    logger.error("IPC listener error: %s", e)

    def stop(self) -> None:
        """Stop the IPC server and close the named pipe."""
        self._running = False
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


class IpcClient:
    """Client for sending commands to the resident PLUMA core."""

    def __init__(self, address: Optional[str] = None) -> None:
        self.address = address or get_pipe_name()

    def send_command(self, command: Dict[str, Any], timeout: float = 2.0) -> Dict[str, Any]:
        """Send a JSON-serializable command and await a response."""
        from multiprocessing.connection import Client
        try:
            # Note: The multiprocessing Client on Windows doesn't easily support timeouts on connect,
            # but IPC is strictly local so connection should be immediate.
            with Client(self.address) as conn:
                conn.send_bytes(json.dumps(command).encode("utf-8"))
                
                # Wait for response with timeout
                import multiprocessing.connection
                if multiprocessing.connection.wait([conn], timeout=timeout):
                    msg_bytes = conn.recv_bytes()
                    return json.loads(msg_bytes.decode("utf-8"))  # type: ignore[no-any-return]
                else:
                    return {"status": "error", "message": "Timeout waiting for response"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
