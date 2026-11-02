"""Task-bound, bounded confirmation exchange. No UI thread or desktop access."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import threading
import time
from uuid import uuid4

from pluma.memory.redaction import redact_string, sanitise_args_for_ledger
from pluma.ui.confirmations import ConfirmationContract, ConfirmationResponse


class IpcConfirmationBroker(ConfirmationContract):
    """One-use exact-call decisions; lost clients can only cause denial."""

    def __init__(self, task_resolver, timeout_s=30.0, capacity=32):
        if not 0 < timeout_s <= 30 or not 1 <= capacity <= 32:
            raise ValueError("Confirmation bounds are invalid.")
        self._resolve = task_resolver
        self._timeout = timeout_s
        self._capacity = capacity
        self._lock = threading.RLock()
        self._pending = {}
        self._clients = {}
        self._closed = False

    def _live(self, item):
        try:
            task = self._resolve(item["view"]["task_id"])
        except Exception:
            return False
        return (task is not None and not task.cancellation_token.is_cancelled
                and not task.terminal_ready.is_set())

    @property
    def is_available(self):
        with self._lock:
            self._prune()
            return not self._closed and bool(self._clients) and len(self._pending) < self._capacity

    def _prune(self):
        self._clients = {key: expiry for key, expiry in self._clients.items()
                         if expiry > time.monotonic() and not self._closed}
        for key, item in list(self._pending.items()):
            if (self._closed or time.monotonic() >= item["deadline"] or not self._live(item)
                    or not self._clients or (item["client_id"] is not None
                                            and item["client_id"] not in self._clients)):
                self._pending.pop(key)
                item["done"].set()

    def request_confirmation(self, request):
        call_id = str(uuid4())
        raw = deepcopy(request.arguments)
        material = json.dumps([call_id, request.task_id, request.tool_name,
                               request.risk_class.value, raw, request.prompt_message,
                               request.target_summary], sort_keys=True, ensure_ascii=False, allow_nan=False)
        arguments = json.loads(sanitise_args_for_ledger(request.tool_name, raw))["args"]
        clipboard = "clipboard" in request.tool_name
        view = {"confirmation_id": call_id, "task_id": request.task_id,
                "binding": hashlib.sha256(material.encode("utf-8")).hexdigest(),
                "tool": request.tool_name, "risk": request.risk_class.value,
                "arguments": arguments,
                "prompt": ("Allow this clipboard operation?" if clipboard else redact_string(request.prompt_message)),
                "target_summary": (None if clipboard or request.target_summary is None
                                   else redact_string(request.target_summary)),
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self._timeout)).isoformat()}
        # Keep the entire pending exchange bounded, including display data.
        if len(json.dumps(view).encode("utf-8")) > 16384:
            return ConfirmationResponse(False, "Confirmation exceeds the safe display bound.")
        item = {"view": view, "deadline": time.monotonic() + self._timeout,
                "client_id": None, "approved": False, "done": threading.Event()}
        with self._lock:
            self._prune()
            if self._closed or not self._clients or len(self._pending) >= self._capacity or not self._live(item):
                return ConfirmationResponse(False, "Confirmation is unavailable.")
            self._pending[call_id] = item
        try:
            while not item["done"].wait(0.02):
                with self._lock:
                    self._prune()
            # A decision cannot revive a stopped task or a changed exact call.
            intact = json.dumps(raw, sort_keys=True, allow_nan=False) == json.dumps(
                request.arguments, sort_keys=True, allow_nan=False)
            approved = item["approved"] is True and self._live(item) and intact
            return ConfirmationResponse(approved, "Exact operation approved." if approved else "Operation not approved.")
        finally:
            with self._lock:
                self._pending.pop(call_id, None)

    def pending(self, client_id):
        with self._lock:
            self._prune()
            if self._closed or (client_id not in self._clients and len(self._clients) >= 16):
                raise ValueError("Confirmation client is unavailable.")
            self._clients[client_id] = time.monotonic() + 30.0
            views = []
            for item in self._pending.values():
                if item["client_id"] in (None, client_id):
                    item["client_id"] = client_id
                    views.append(deepcopy(item["view"]))
            return views

    def decide(self, request):
        with self._lock:
            self._prune()
            item = self._pending.get(request.confirmation_id)
            if item is None:
                return False, "CONFIRMATION_NOT_PENDING"
            if (item["client_id"] != request.client_id or item["view"]["task_id"] != request.task_id
                    or item["view"]["binding"] != request.binding):
                return False, "CONFIRMATION_MISMATCH"
            self._pending.pop(request.confirmation_id)
            item["approved"] = request.approved is True
            item["done"].set()
            return True, None

    def disconnect(self, client_id):
        with self._lock:
            before = set(self._pending)
            self._clients.pop(client_id, None)
            items = [item for item in self._pending.values() if item["client_id"] == client_id]
            for item in items:
                self._pending.pop(item["view"]["confirmation_id"])
                item["done"].set()
            self._prune()
            return len(before - self._pending.keys())

    def close(self):
        with self._lock:
            self._closed = True
            self._prune()
