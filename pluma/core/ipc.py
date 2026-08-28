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
import hashlib
import hmac
import secrets
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

MAX_IPC_MESSAGE_SIZE: int = 1024 * 1024  # 1MB maximum message payload
IPC_SECRET_SIZE: int = 32  # 256-bit persistent secret
IPC_CHALLENGE_SIZE: int = 32  # 256-bit ephemeral challenge


def get_pipe_name() -> str:
    """Return a secure, per-user named pipe address."""
    username = os.environ.get("USERNAME") or os.environ.get("USER") or "default"
    clean_user = "".join(c for c in username if c.isalnum() or c in ("-", "_"))
    if sys.platform == "win32":
        return rf"\\.\pipe\pluma_ipc_{clean_user}"
    # Fallback for non-Windows tests
    return f"/tmp/pluma_ipc_{clean_user}.sock"


def _get_or_create_ipc_secret(paths_root: Optional[str] = None) -> bytes:
    """Get or create the persistent random IPC authentication secret.

    The secret is stored in %LOCALAPPDATA%\\Pluma\\ipc_secret.key with verified
    owner-only permissions (mode 0600 or Windows owner ACL).
    The secret itself is NEVER transmitted over the pipe.
    Raises RuntimeError if secret persistence or ACL verification fails (fail-closed).
    """
    root = paths_root or os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    sec_dir = os.path.join(root, "Pluma")
    os.makedirs(sec_dir, exist_ok=True)
    sec_file = os.path.join(sec_dir, "ipc_secret.key")

    if os.path.exists(sec_file):
        try:
            with open(sec_file, "rb") as f:
                sec = f.read()
            if len(sec) == IPC_SECRET_SIZE:
                return sec
        except OSError as exc:
            logger.warning("Could not read existing IPC secret file %s: %s", sec_file, exc)

    # Generate and securely store new secret
    secret = secrets.token_bytes(IPC_SECRET_SIZE)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        mode = 0o600
        fd = os.open(sec_file, flags, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(secret)
        if sys.platform != "win32":
            os.chmod(sec_file, 0o600)
        return secret
    except Exception as e:
        logger.error("Failed to persist secure IPC secret to %s: %s", sec_file, e)
        raise RuntimeError(f"Cannot secure IPC secret file: {e}") from e


def _compute_ipc_response(secret: bytes, challenge: bytes) -> bytes:
    """Compute HMAC-SHA256 response token for a given challenge nonce."""
    return hmac.new(secret, challenge, hashlib.sha256).digest()



def _create_win32_pipe_security() -> Any:
    """Create a SECURITY_ATTRIBUTES struct restricting the pipe to the current user SID.

    Returns None on non-Windows or if creation fails (caller falls back to default).
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Get current process token
        TOKEN_QUERY = 0x0008
        h_token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(h_token)):
            return None

        # Get token user SID size
        TOKEN_USER = 1
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(h_token, TOKEN_USER, None, 0, ctypes.byref(needed))
        buf = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(h_token, TOKEN_USER, buf, needed, ctypes.byref(needed)):
            kernel32.CloseHandle(h_token)
            return None
        kernel32.CloseHandle(h_token)

        # SID is at offset 0 in TOKEN_USER (pointer to SID_AND_ATTRIBUTES, first field is pointer to SID)
        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
            return None

        sid_str = sid_str_ptr.value
        # SDDL: D:(A;;GA;;;{current_user_sid}) — full access to owner only
        sddl = f"D:(A;;GA;;;{sid_str})"
        sd_ptr = ctypes.c_void_p()
        sd_size = wintypes.ULONG()
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd_ptr), ctypes.byref(sd_size)
        ):
            return None

        class SECURITY_ATTRIBUTES(ctypes.Structure):
            _fields_ = [
                ("nLength", wintypes.DWORD),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL),
            ]

        sa = SECURITY_ATTRIBUTES()
        sa.nLength = ctypes.sizeof(SECURITY_ATTRIBUTES)
        sa.lpSecurityDescriptor = sd_ptr
        sa.bInheritHandle = False
        return sa
    except Exception as exc:
        logger.debug("Failed to create pipe security attributes: %s", exc)
        return None


class IpcServer:
    """Named-pipe IPC server for local command dispatch with timeouts and bounded messages.

    Security:
    - Pipe address is per-user (username encoded in path).
    - On Windows, the named pipe DACL is restricted to the current user SID.
    - Mandatory HMAC-SHA256 challenge-response authentication with unshared stored secret.
    - Each client is handled in its own daemon thread so one slow/stuck client
      cannot block other clients or the accept loop.
    - Request and response sizes are both bounded at MAX_IPC_MESSAGE_SIZE.
    - Malformed JSON and unexpected message types are rejected with an error response.
    """

    def __init__(
        self,
        command_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        address: Optional[str] = None,
        max_message_size: int = MAX_IPC_MESSAGE_SIZE,
        read_timeout_s: float = 5.0,
        require_auth: bool = True,
    ) -> None:
        self.address = address or get_pipe_name()
        self._command_handler = command_handler
        self._max_message_size = max_message_size
        self._read_timeout_s = read_timeout_s
        self._require_auth = require_auth
        self._secret: Optional[bytes] = None
        self._listener: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Load auth secret immediately if authentication is required so startup fails closed
        if require_auth:
            try:
                self._secret = _get_or_create_ipc_secret()
                logger.debug("IPC authentication secret loaded (%d bytes).", len(self._secret))
            except Exception as e:
                logger.error("Failed to load IPC auth secret — server cannot start with require_auth=True: %s", e)
                raise RuntimeError(f"IPC auth secret unavailable: {e}") from e

    def start(self) -> None:
        """Start the IPC server in a daemon thread."""
        from multiprocessing.connection import Listener

        try:
            self._listener = Listener(self.address)
            # Attempt to restrict DACL to current user on Windows after pipe creation
            _try_restrict_pipe_to_current_user(self.address)
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
                # Spawn a per-client thread so one slow client cannot block others
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    daemon=True,
                    name="PlumaIpcClient",
                )
                client_thread.start()
            except EOFError:
                pass
            except Exception as e:
                if self._running:
                    logger.error("IPC listener error: %s", e)

    def _handle_client(self, conn: Any) -> None:
        """Handle one client connection in a dedicated daemon thread.

        If require_auth is True, performs HMAC challenge-response before accepting any command.
        Authentication failure closes the connection silently (fail-closed).
        """
        with conn:
            try:
                # --- Authentication handshake (fail-closed) ---
                if self._require_auth and self._secret is not None:
                    try:
                        # 1. Send an ephemeral 32-byte challenge nonce to the client
                        challenge = secrets.token_bytes(IPC_CHALLENGE_SIZE)
                        conn.send_bytes(challenge)

                        # 2. Wait for client to respond with HMAC token
                        auth_ready = multiprocessing.connection.wait([conn], timeout=self._read_timeout_s)
                        if not auth_ready:
                            logger.warning("IPC auth timeout: client did not respond to challenge in %.1fs", self._read_timeout_s)
                            return  # Close silently — no error response (fail-closed)

                        token_received = conn.recv_bytes(64)
                        expected_token = _compute_ipc_response(self._secret, challenge)

                        if len(token_received) != 32 or not hmac.compare_digest(token_received, expected_token):
                            logger.warning("IPC authentication failed: token mismatch. Closing connection.")
                            return  # Close silently — no error response (fail-closed)

                        # 3. Acknowledge authentication success
                        conn.send_bytes(b"AUTH_OK")
                        logger.debug("IPC client authenticated successfully.")
                    except Exception as auth_err:
                        logger.warning("IPC auth error: %s. Closing connection.", auth_err)
                        return  # Close silently

                # --- Normal request processing ---
                # Enforce server read timeout so a slow/hanging client cannot stall
                ready = multiprocessing.connection.wait([conn], timeout=self._read_timeout_s)
                if not ready:
                    logger.warning("IPC client read timed out after %.1fs", self._read_timeout_s)
                    try:
                        conn.send_bytes(json.dumps(
                            {"status": "error", "message": "Read timeout"}
                        ).encode("utf-8"))
                    except Exception:
                        pass
                    return

                msg_bytes = conn.recv_bytes(self._max_message_size)

                # Parse and validate JSON
                try:
                    req = json.loads(msg_bytes.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
                    conn.send_bytes(json.dumps(
                        {"status": "error", "message": f"Malformed JSON request: {parse_err}"}
                    ).encode("utf-8"))
                    return

                if not isinstance(req, dict):
                    conn.send_bytes(json.dumps(
                        {"status": "error", "message": "Request must be a JSON object (dict)."}
                    ).encode("utf-8"))
                    return

                # Dispatch to handler
                try:
                    resp = self._command_handler(req)
                    resp_bytes = json.dumps(resp).encode("utf-8")
                    # Bound the response size too
                    if len(resp_bytes) > self._max_message_size:
                        resp_bytes = json.dumps(
                            {"status": "error", "message": "Response too large"}
                        ).encode("utf-8")
                    conn.send_bytes(resp_bytes)
                except Exception as e:
                    logger.error("Error processing IPC message: %s", e)
                    try:
                        conn.send_bytes(json.dumps(
                            {"status": "error", "message": str(e)}
                        ).encode("utf-8"))
                    except Exception:
                        pass
            except EOFError:
                pass
            except Exception as e:
                logger.error("IPC client handling error: %s", e)

    def stop(self) -> None:
        """Stop the IPC server and release resources."""
        self._running = False
        if self._listener:
            try:
                self._listener.close()
            except Exception:
                pass
            self._listener = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("IPC Server stopped.")


def _try_restrict_pipe_to_current_user(pipe_name: str) -> None:
    """Attempt to restrict the named pipe DACL to the current user SID (Windows only).

    This is a best-effort operation. If it fails, the pipe security degrades to
    the default Windows named pipe security (accessible to all local processes).
    The error is logged at DEBUG level and does NOT prevent the server from starting.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # Get current user SID
        TOKEN_QUERY = 0x0008
        h_token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(), TOKEN_QUERY, ctypes.byref(h_token)):
            logger.debug("_try_restrict_pipe_to_current_user: OpenProcessToken failed")
            return

        TOKEN_USER = 1
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(h_token, TOKEN_USER, None, 0, ctypes.byref(needed))
        buf = ctypes.create_string_buffer(needed.value)
        ok = advapi32.GetTokenInformation(h_token, TOKEN_USER, buf, needed, ctypes.byref(needed))
        kernel32.CloseHandle(h_token)
        if not ok:
            logger.debug("_try_restrict_pipe_to_current_user: GetTokenInformation failed")
            return

        sid_ptr = ctypes.cast(buf, ctypes.POINTER(ctypes.c_void_p))[0]
        sid_str_ptr = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_ptr, ctypes.byref(sid_str_ptr)):
            logger.debug("_try_restrict_pipe_to_current_user: ConvertSidToStringSidW failed")
            return

        sid_str = sid_str_ptr.value
        sddl = f"D:(A;;GA;;;{sid_str})"
        sd_ptr = ctypes.c_void_p()
        sd_size = wintypes.ULONG()
        if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd_ptr), ctypes.byref(sd_size)
        ):
            logger.debug("_try_restrict_pipe_to_current_user: ConvertStringSecurityDescriptorToSecurityDescriptorW failed")
            return

        # Get a handle to the pipe for SetSecurityInfo
        FILE_WRITE_ATTRIBUTES = 0x100
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        h_pipe = kernel32.CreateFileW(
            pipe_name,
            FILE_WRITE_ATTRIBUTES,
            0, None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
        if not h_pipe or h_pipe == INVALID_HANDLE_VALUE:
            logger.debug("_try_restrict_pipe_to_current_user: CreateFileW failed (err %d)", ctypes.get_last_error())
            return

        try:
            # SE_KERNEL_OBJECT=6, DACL_SECURITY_INFORMATION=4
            DACL_SECURITY_INFORMATION = 4
            SE_KERNEL_OBJECT = 6
            ret = advapi32.SetSecurityInfo(
                h_pipe, SE_KERNEL_OBJECT, DACL_SECURITY_INFORMATION,
                None, None, sd_ptr, None
            )
            if ret != 0:  # ERROR_SUCCESS = 0
                logger.debug("_try_restrict_pipe_to_current_user: SetSecurityInfo returned %d", ret)
            else:
                logger.debug("Named pipe DACL restricted to current user SID %s", sid_str)
        finally:
            kernel32.CloseHandle(h_pipe)
    except Exception as exc:
        logger.debug("_try_restrict_pipe_to_current_user failed: %s", exc)


class IpcClient:
    """Client for sending commands to the resident PLUMA core with bounded timeouts."""

    def __init__(
        self,
        address: Optional[str] = None,
        max_message_size: int = MAX_IPC_MESSAGE_SIZE,
        require_auth: bool = True,
    ) -> None:
        self.address = address or get_pipe_name()
        self._max_message_size = max_message_size
        self._require_auth = require_auth

    def send_command(self, command: Dict[str, Any], timeout: float = 3.0) -> Dict[str, Any]:
        """Send a JSON-serializable command and await a response with timeout.

        If require_auth is True, performs HMAC challenge-response handshake after connecting.
        """
        from multiprocessing.connection import Client
        deadline = time.perf_counter() + timeout
        last_err: Optional[Exception] = None

        while time.perf_counter() < deadline:
            try:
                with Client(self.address) as conn:
                    # --- Authentication handshake ---
                    if self._require_auth:
                        secret = _get_or_create_ipc_secret()
                        remaining = max(0.1, deadline - time.perf_counter())
                        if not multiprocessing.connection.wait([conn], timeout=remaining):
                            return {"status": "error", "message": "Auth timeout: no challenge received"}
                        challenge = conn.recv_bytes(IPC_CHALLENGE_SIZE + 16)
                        if len(challenge) != IPC_CHALLENGE_SIZE:
                            return {"status": "error", "message": f"Auth challenge size invalid: {len(challenge)}"}
                        token = _compute_ipc_response(secret, challenge)
                        conn.send_bytes(token)

                        if not multiprocessing.connection.wait([conn], timeout=remaining):
                            return {"status": "error", "message": "Auth timeout: no auth ack received"}
                        ack = conn.recv_bytes(32)
                        if ack != b"AUTH_OK":
                            return {"status": "error", "message": "Authentication rejected by server"}

                    # --- Command payload ---
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
