"""Bounded executor copy, separate from result bodies and private inverse data."""
import json
import re

from pluma.memory.redaction import redact_command_text

TEXT_BYTES = 1024


def _text(tool, value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Invalid executor presentation")
    # Redact the complete value before applying any display bound.
    value = ("[REDACTED CLIPBOARD RESULT]" if "clipboard" in tool or tool in {"paste", "paste_text"}
             else redact_command_text(value))
    value = "".join(c for c in value if ord(c) >= 32 or c in "\n\t").strip()
    encoded = value.encode("utf-8")
    if len(encoded) > TEXT_BYTES:
        value = encoded[:TEXT_BYTES - 3].decode("utf-8", errors="ignore") + "…"
    return value or None


def presentation(tool, message, error_code=None, policy_reason=None):
    code = error_code if isinstance(error_code, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", error_code) else None
    return {"version": 1, "factual_message": _text(tool, message), "error_code": code,
            "policy_reason": _text(tool, policy_reason)}


def encode_presentation(record):
    code = record.error_detail.get("code") if record.error_detail else None
    if record.factual_message is None and record.policy_reason is None and code is None:
        return None
    return json.dumps(presentation(record.tool, record.factual_message, code, record.policy_reason))


def decode_presentation(tool, encoded):
    if encoded is None:
        return presentation(tool, None)
    if len(encoded) > 14000:
        raise ValueError("Oversized executor presentation")
    value = json.loads(encoded)
    if (not isinstance(value, dict) or set(value) != {"version", "factual_message", "error_code", "policy_reason"}
            or type(value["version"]) is not int or value["version"] != 1):
        raise ValueError("Invalid executor presentation")
    for key in ("factual_message", "policy_reason"):
        text = value[key]
        if text is not None and (not isinstance(text, str) or len(text.encode("utf-8")) > TEXT_BYTES):
            raise ValueError("Invalid executor presentation text")
    code = value["error_code"]
    if code is not None and (not isinstance(code, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code)):
        raise ValueError("Invalid executor error identity")
    return presentation(tool, value["factual_message"], code, value["policy_reason"])
