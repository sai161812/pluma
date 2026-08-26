"""tests/unit/test_phase13_5_stage_f_redaction.py — Stage F Redaction and Memory Boundaries regression tests."""

from __future__ import annotations

import json
import pytest

from pluma.memory.redaction import (
    REDACTED_TOKEN,
    RedactionEngine,
    redact_dict,
    redact_sensitive_data,
    redact_string,
    sanitise_args_for_ledger,
)


def test_stage_f_sensitive_keys_and_tokens_redacted() -> None:
    """Gate F: Verify sensitive keys (passwords, tokens, API keys) are masked."""
    payload = {
        "user": "alice",
        "password": "SuperSecretPassword123!",
        "api_key": "sk-1234567890abcdef1234567890abcdef",
        "custom_auth_token": "bearer-xyz-12345",
        "user_secret": "my-secret-value",
        "nested": {
            "jwt_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgN_p_secret",
            "safe_field": "public data",
        },
    }

    redacted = redact_dict(payload)
    assert redacted["user"] == "alice"
    assert redacted["password"] == REDACTED_TOKEN
    assert redacted["api_key"] == REDACTED_TOKEN
    assert redacted["custom_auth_token"] == REDACTED_TOKEN
    assert redacted["user_secret"] == REDACTED_TOKEN
    assert redacted["nested"]["jwt_token"] == REDACTED_TOKEN
    assert redacted["nested"]["safe_field"] == "public data"


def test_stage_f_freeform_string_redaction() -> None:
    """Gate F: Verify free-form strings containing OpenAI keys, JWTs, AWS keys, and private keys are scrubbed."""
    raw_text = (
        "Connecting with sk-proj-1234567890abcdef1234567890abcdef and "
        "AKIAIOSFODNN7EXAMPLE using token=mySecretToken12345"
    )
    scrubbed = redact_string(raw_text)
    assert "sk-proj" not in scrubbed
    assert "AKIAIOSFODNN7EXAMPLE" not in scrubbed
    assert REDACTED_TOKEN in scrubbed


def test_stage_f_ledger_sanitisation() -> None:
    """Gate F: Verify sanitise_args_for_ledger produces clean JSON for SQLite storage."""
    args = {
        "path": "C:\\safe\\path.txt",
        "client_secret": "sensitive-credential-value",
        "headers": {"Authorization": "Bearer secret_jwt_value_here_12345"},
    }
    json_out = sanitise_args_for_ledger("test_tool", args)
    data = json.loads(json_out)

    assert data["tool"] == "test_tool"
    assert data["args"]["path"] == "C:\\safe\\path.txt"
    assert data["args"]["client_secret"] == REDACTED_TOKEN
    assert data["args"]["headers"]["Authorization"] == REDACTED_TOKEN
