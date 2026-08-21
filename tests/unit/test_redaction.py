"""tests.unit.test_redaction — Sensitive-value redaction tests."""

from __future__ import annotations

from pluma.memory.redaction import (
    redact_dict, redact_json_str, sanitise_args_for_ledger, REDACTED_TOKEN
)


class TestRedactDict:
    def test_password_key_redacted(self) -> None:
        result = redact_dict({"password": "supersecret"})
        assert result["password"] == REDACTED_TOKEN

    def test_token_key_redacted(self) -> None:
        result = redact_dict({"token": "ghp_abc123abc123abc123abc123abc123abc123"})
        assert result["token"] == REDACTED_TOKEN

    def test_clipboard_key_redacted(self) -> None:
        """Spec §16.3: raw clipboard values not stored."""
        result = redact_dict({"clipboard": "my private copied text"})
        assert result["clipboard"] == REDACTED_TOKEN

    def test_audio_path_redacted(self) -> None:
        """Spec §16.3: raw audio paths not stored."""
        result = redact_dict({"audio_path": "C:\\Temp\\recording.wav"})
        assert result["audio_path"] == REDACTED_TOKEN

    def test_case_insensitive_key_matching(self) -> None:
        result = redact_dict({"PASSWORD": "secret", "Token": "tok"})
        assert result["PASSWORD"] == REDACTED_TOKEN
        assert result["Token"] == REDACTED_TOKEN

    def test_safe_key_preserved(self) -> None:
        result = redact_dict({"level": 30, "app_name": "notepad"})
        assert result["level"] == 30
        assert result["app_name"] == "notepad"

    def test_deep_nested_redaction(self) -> None:
        data = {"outer": {"password": "deep_secret", "safe": "value"}}
        result = redact_dict(data, deep=True)
        assert result["outer"]["password"] == REDACTED_TOKEN
        assert result["outer"]["safe"] == "value"

    def test_list_of_dicts_redacted(self) -> None:
        data = {"items": [{"password": "a"}, {"safe": "b"}]}
        result = redact_dict(data)
        assert result["items"][0]["password"] == REDACTED_TOKEN
        assert result["items"][1]["safe"] == "b"

    def test_original_dict_not_mutated(self) -> None:
        original = {"password": "secret", "level": 30}
        redact_dict(original)
        assert original["password"] == "secret"  # Original unchanged.

    def test_hex_token_value_redacted(self) -> None:
        """A hex string ≥16 chars with a benign key is flagged by value pattern."""
        result = redact_dict({"some_key": "deadbeefcafebabe1234567890abcdef"})
        assert result["some_key"] == REDACTED_TOKEN

    def test_short_string_not_redacted(self) -> None:
        result = redact_dict({"some_key": "short"})
        assert result["some_key"] == "short"


class TestRedactJsonStr:
    def test_json_with_password_redacted(self) -> None:
        import json
        raw = json.dumps({"password": "mypass", "level": 5})
        result = redact_json_str(raw)
        parsed = json.loads(result)
        assert parsed["password"] == REDACTED_TOKEN
        assert parsed["level"] == 5

    def test_invalid_json_returned_unchanged(self) -> None:
        bad = "not json {{"
        assert redact_json_str(bad) == bad


class TestSanitiseArgsForLedger:
    def test_output_is_json_string(self) -> None:
        import json
        result = sanitise_args_for_ledger("set_volume", {"level": 30})
        parsed = json.loads(result)
        assert parsed["tool"] == "set_volume"
        assert parsed["args"]["level"] == 30

    def test_sensitive_arg_redacted(self) -> None:
        import json
        result = sanitise_args_for_ledger("run_command", {"password": "secret", "cmd": "ls"})
        parsed = json.loads(result)
        assert parsed["args"]["password"] == REDACTED_TOKEN
        assert parsed["args"]["cmd"] == "ls"
