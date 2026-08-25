"""pluma.memory.redaction — Sensitive-value redaction for logs and ledger.

Spec §14: "Credentials/secrets must be handled outside model context. Stored
logs redact tokens, passwords, private clipboard values and other sensitive data."
Spec §16.3: "Passwords, auth tokens or sensitive clipboard values" are not
stored by default.

This module provides deterministic redaction: no ML, no heuristics. The
redaction rules are an explicit allowlist/denylist of key names. Unknown keys
that look like passwords (matching common patterns) are also redacted.

No OS-automation or adapter code in this module.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Union

# Replacement token used wherever a value is redacted.
REDACTED_TOKEN = "[REDACTED]"

# Exact key names (case-insensitive) that always trigger redaction.
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "bearer",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
    "access_key",
    "accesskey",
    "session_token",
    "sessiontoken",
    "client_secret",
    "clientsecret",
    "clipboard",      # Raw clipboard values per spec §16.3.
    "audio_path",     # Raw audio file paths per spec §16.3.
    "raw_audio",
})

# Regex patterns for values that look like secrets (applied after key check).
_SECRET_VALUE_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(?:[A-Za-z0-9+/]{20,}={0,2})$"),      # base64-like blobs
    re.compile(r"^[0-9a-fA-F]{32,}$"),                   # hex tokens
    re.compile(r"^ghp_[A-Za-z0-9]{36}$"),                # GitHub PAT
    re.compile(r"^sk-[A-Za-z0-9]{32,}"),                 # OpenAI-style keys
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                   # AWS access key
]


def _is_sensitive_key(key: str) -> bool:
    return key.lower() in _SENSITIVE_KEYS


def _looks_like_secret_value(value: str) -> bool:
    if len(value) < 16:
        return False
    return any(p.match(value) for p in _SECRET_VALUE_PATTERNS)


def redact_dict(data: Dict[str, Any], *, deep: bool = True) -> Dict[str, Any]:
    """Return a copy of *data* with sensitive values replaced by REDACTED_TOKEN.

    If *deep* is True, nested dicts and lists are also processed recursively.
    String values are checked against known patterns only when the key itself
    is not flagged (to avoid redacting benign short strings).
    """
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            result[key] = REDACTED_TOKEN
        elif deep and isinstance(value, dict):
            result[key] = redact_dict(value, deep=True)
        elif deep and isinstance(value, list):
            result[key] = _redact_list(value)
        elif isinstance(value, str) and _looks_like_secret_value(value):
            result[key] = REDACTED_TOKEN
        else:
            result[key] = value
    return result


def _redact_list(items: List[Any]) -> List[Any]:
    return [
        redact_dict(item, deep=True) if isinstance(item, dict)
        else _redact_list(item) if isinstance(item, list)
        else item
        for item in items
    ]


def redact_json_str(json_str: str) -> str:
    """Parse *json_str*, redact, and re-serialise.

    Returns the original string unchanged if parsing fails (safe default).
    """
    try:
        data = json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return json_str
    if isinstance(data, dict):
        return json.dumps(redact_dict(data))
    return json_str


def sanitise_args_for_ledger(tool_name: str, args: Dict[str, Any]) -> str:
    """Return a redacted JSON string of tool arguments suitable for ledger storage.

    This is the canonical function called by the executor before writing
    to the actions table. The tool name is included in the output for context.
    """
    sanitised = redact_dict(args, deep=True)
    return json.dumps({"tool": tool_name, "args": sanitised}, ensure_ascii=False)


def redact_string(text: str) -> str:
    """Redact known secret patterns and tokens from an arbitrary string."""
    result = text
    for pattern in _SECRET_VALUE_PATTERNS:
        result = pattern.sub(REDACTED_TOKEN, result)
    # Also check specific token words like "api_key=...", "password=..."
    result = re.sub(r"(?i)\b(api_key|apikey|password|passwd|secret|token)\s*=\s*['\"]?([^\s'\"]+)['\"]?", r"\1=" + REDACTED_TOKEN, result)
    return result


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive data in dicts, lists, strings, or primitives."""
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, list):
        return _redact_list(data)
    elif isinstance(data, str):
        return redact_string(data)
    return data
