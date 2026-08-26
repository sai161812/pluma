"""pluma.core.ipc — Local-only named-pipe IPC contract.

Spec §18: "Windows named pipe or equivalent local-only IPC."
Spec §25: "All local IPC must be bound to the user/local machine."
Implemented in Phase 1.
"""

from __future__ import annotations

import json
import logging
import multiprocessing.connection
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

MAX_IPC_MESSAGE_SIZE: int = 1024 * 1024  # 1MB maximum message payload
SERVER_READ_TIMEOUT_SECONDS: float = 5.0
CLIENT_CONNECT_TIMEOUT_SECONDS: float = 3.0


def get_pipe_name() -> str:
    """Return a secure, per-user named pipe address."""
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    clean_user = "".join(c for c in username if c.isalnum() or c in ("-", "_"))
    if sys.platform == "win32":
        return rf"\\.\pipe\pluma_ipc_{clean_user}"
    # Fallback for non-Windows tests
    return f"/tmp/pluma_ipc_{clean_user}.sock"


class IpcServer:
    """Named-pipe IPC server for local command dispatch with timeouts and bounded messages."""

    def __init__(
        self,
        command_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        address: Optional[str] = None,
        max_message_size: int = MAX_IPC_MESSAGE_SIZE,
        read_timeout_s: float = SERVER_READ_TIMEOUT_SECONDS,
    ) -> None:
        self.address = address or get_pipe_name()
        self._command_handler = command_handler
        self._max_message_size = max_message_size
        self._read_timeout_s = read_timeout_s
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
                    # Enforce server read timeout so a slow or hanging client cannot stall the server
                    ready = multiprocessing.connection.wait([conn], timeout=self._read_timeout_s)
                    if not ready:
                        logger.warning("IPC client read timed out after %0.1fs", self._read_timeout_s)
                        continue

                    msg_bytes = conn.recv_bytes(self._max_message_size)
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
    """Client for sending commands to the resident PLUMA core with bounded timeouts."""

    def __init__(
        self,
        address: Optional[str] = None,
        max_message_size: int = MAX_IPC_MESSAGE_SIZE,
    ) -> None:
        self.address = address or get_pipe_name()
        self._max_message_size = max_message_size

    def send_command(self, command: Dict[str, Any], timeout: float = 3.0) -> Dict[str, Any]:
        """Send a JSON-serializable command and await a response with timeout."""
        from multiprocessing.connection import Client
        deadline = time.perf_counter() + timeout
        last_err: Optional[Exception] = None

        while time.perf_counter() < deadline:
            try:
                with Client(self.address) as conn:
                    conn.send_bytes(json.dumps(command).encode("utf-8"))
                    
                    remaining = max(0.1, deadline - time.perf_counter())
                    if multiprocessing.connection.wait([conn], timeout=remaining):
                        msg_bytes = conn.recv_bytes(self._max_message_size)
                        return json.loads(msg_bytes.decode("utf-8"))  # type: ignore[no-any-return]
                    else:
                        return {"status": "error", "message": "Timeout waiting for response"}
            except (ConnectionRefusedError, FileNotFoundError) as conn_err:
                last_err = conn_err
                time.sleep(0.05)
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "error", "message": f"Connection timeout: {last_err or 'server unreachable'}"}


# Aliases for explicit naming
NamedPipeIpcServer = IpcServer
NamedPipeIpcClient = IpcClient
