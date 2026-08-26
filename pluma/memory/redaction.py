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

_SENSITIVE_KEY_SUBSTRINGS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "auth", "bearer", "credential", "private_key", "privkey",
    "access_key", "session_token", "jwt", "client_secret",
    "clipboard", "audio_path", "raw_audio",
)


def _is_sensitive_key(key: str) -> bool:
    clean_k = key.lower().replace("-", "_").replace(" ", "_")
    return any(sub in clean_k for sub in _SENSITIVE_KEY_SUBSTRINGS)


# Regex patterns for values that look like secrets (applied after key check).
_SECRET_VALUE_PATTERNS: List[re.Pattern] = [
    re.compile(r"^(?:[A-Za-z0-9+/]{20,}={0,2})$"),      # base64-like blobs
    re.compile(r"^[0-9a-fA-F]{32,}$"),                   # hex tokens
    re.compile(r"^ghp_[A-Za-z0-9]{36}$"),                # GitHub PAT
    re.compile(r"^sk-[A-Za-z0-9_-]{20,}"),               # OpenAI / Anthropic keys
    re.compile(r"^AKIA[0-9A-Z]{16}$"),                   # AWS access key
]


def _looks_like_secret_value(value: str) -> bool:
    if len(value) < 16:
        return False
    return any(p.match(value) for p in _SECRET_VALUE_PATTERNS)


def redact_dict(data: Dict[str, Any], *, deep: bool = True) -> Dict[str, Any]:
    """Return a copy of *data* with sensitive values replaced by REDACTED_TOKEN.

    If *deep* is True, nested dicts and lists are also processed recursively.
    String values are sanitized against all known unanchored secret patterns.
    """
    result: Dict[str, Any] = {}
    for key, value in data.items():
        if _is_sensitive_key(key):
            result[key] = REDACTED_TOKEN
        elif deep and isinstance(value, dict):
            result[key] = redact_dict(value, deep=True)
        elif deep and isinstance(value, list):
            result[key] = _redact_list(value)
        elif isinstance(value, str):
            result[key] = redact_string(value)
        else:
            result[key] = value
    return result


def _redact_list(items: List[Any]) -> List[Any]:
    return [
        redact_dict(item, deep=True) if isinstance(item, dict)
        else _redact_list(item) if isinstance(item, list)
        else redact_string(item) if isinstance(item, str)
        else item
        for item in items
    ]


def redact_json_str(json_str: str) -> str:
    """Parse *json_str*, redact, and re-serialise.

    If parsing fails (malformed JSON or raw string), redacts secrets from the raw string
    directly to guarantee no sensitive data is leaked.
    """
    if not isinstance(json_str, str):
        return json_str
    try:
        data = json.loads(json_str)
        if isinstance(data, dict):
            return json.dumps(redact_dict(data))
        elif isinstance(data, list):
            return json.dumps(_redact_list(data))
    except (json.JSONDecodeError, TypeError):
        pass
    return redact_string(json_str)


def sanitise_args_for_ledger(tool_name: str, args: Dict[str, Any]) -> str:
    """Return a redacted JSON string of tool arguments suitable for ledger storage.

    This is the canonical function called by the executor before writing
    to the actions table. The tool name is included in the output for context.
    """
    sanitised = redact_dict(args, deep=True)
    return json.dumps({"tool": tool_name, "args": sanitised}, ensure_ascii=False)


_UNANCHORED_SECRET_PATTERNS: List[re.Pattern] = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    # Connection strings with credentials (URI format: postgres://user:pass@host:port/db)
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp[s]?|mssql|oracle)://([^:\s/@]+):([^@\s/]+)@"),
    # Connection strings key-value format (Server=...;User Id=...;Password=...;)
    re.compile(r"(?i)(?:Password|PWD)\s*=\s*['\"]?([^;'\"]+)['\"]?"),
    re.compile(r"(?i)\b(api_key|apikey|password|passwd|secret|token)\s*[:=]\s*['\"]?([^\s'\"]+)['\"]?"),
    re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9._~+/-]{20,})"),
]


def redact_string(text: str) -> str:
    """Return a copy of *text* with unanchored secrets and credentials replaced by REDACTED_TOKEN."""
    if not isinstance(text, str) or not text:
        return text

    redacted = text
    # 1. URI connection strings: redact the password portion
    redacted = re.sub(
        r"(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp[s]?|mssql|oracle)://[^:\s/@]+:)(?:[^@\s/]+)(@)",
        r"\1" + REDACTED_TOKEN + r"\2",
        redacted,
    )
    # 2. Key-value connection strings (Password=...;)
    redacted = re.sub(
        r"(?i)(\b(?:Password|PWD)\s*=\s*['\"]?)(?:[^;'\"]+)(['\"]?)",
        r"\1" + REDACTED_TOKEN + r"\2",
        redacted,
    )
    # 3. Standard unanchored patterns
    for pat in _UNANCHORED_SECRET_PATTERNS:
        redacted = pat.sub(REDACTED_TOKEN, redacted)
    for pattern in _SECRET_VALUE_PATTERNS:
        redacted = pattern.sub(REDACTED_TOKEN, redacted)
    return redacted


def redact_sensitive_data(data: Any) -> Any:
    """Recursively redact sensitive data in dicts, lists, strings, or primitives."""
    if isinstance(data, dict):
        return redact_dict(data)
    elif isinstance(data, list):
        return _redact_list(data)
    elif isinstance(data, str):
        return redact_string(data)
    return data


class RedactionEngine:
    """Convenience wrapper providing static redaction methods."""
    redact_string = staticmethod(redact_string)
    redact_dict = staticmethod(redact_dict)
    redact_sensitive_data = staticmethod(redact_sensitive_data)
    sanitise_args = staticmethod(sanitise_args_for_ledger)
