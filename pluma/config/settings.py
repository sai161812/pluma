"""P21 local settings persistence, without UI, runtime activation or tool admission.

Callers must supply an explicit path and an observed revision. This storage
primitive is not a planner API; a future save entry must use the typed task and
policy boundary. No hotkey, model, microphone or background worker starts here.
"""

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_SETTINGS_BYTES = 256 * 1024
SCHEMA_VERSION = 1
ABSENT_REVISION = "absent"
EDITABLE_FIELDS = frozenset({
    "agent.text_hotkey", "agent.stop_hotkey", "agent.voice_hotkey",
    "agent.max_plan_steps", "brain.model_path", "voice.model_path",
})


class SettingsError(ValueError):
    """Factual bounded code; never include user configuration in the message."""

    def __init__(self, code, *, restored=False):
        self.code = code
        self.restored = restored
        super().__init__(code)


@dataclass(frozen=True)
class SettingsSnapshot:
    overrides: dict
    revision: str
    schema_version: int


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise SettingsError("SETTINGS_DUPLICATE_KEY")
        result[key] = value
    return result


def decode_settings(raw):
    """Read legacy override objects or the versioned envelope, without rewriting."""
    if len(raw) > MAX_SETTINGS_BYTES:
        raise SettingsError("SETTINGS_TOO_LARGE")
    try:
        def invalid_constant(_):
            raise SettingsError("SETTINGS_INVALID_JSON")
        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise SettingsError("SETTINGS_INVALID_JSON")
            return number
        document = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_object,
                              parse_constant=invalid_constant, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, SettingsError):
            raise exc from None
        raise SettingsError("SETTINGS_INVALID_JSON") from None
    if not isinstance(document, dict):
        raise SettingsError("SETTINGS_INVALID_DOCUMENT")
    if "settings_schema_version" not in document:
        return document, 0
    if (type(document["settings_schema_version"]) is not int
            or document["settings_schema_version"] != SCHEMA_VERSION):
        raise SettingsError("SETTINGS_UNSUPPORTED_VERSION")
    if set(document) != {"settings_schema_version", "overrides"} or not isinstance(document["overrides"], dict):
        raise SettingsError("SETTINGS_INVALID_DOCUMENT")
    return document["overrides"], SCHEMA_VERSION


def _read(path):
    try:
        if path.is_symlink():
            raise SettingsError("SETTINGS_LINK_REFUSED")
        with path.open("rb") as stream:
            raw = stream.read(MAX_SETTINGS_BYTES + 1)
        if len(raw) > MAX_SETTINGS_BYTES:
            raise SettingsError("SETTINGS_TOO_LARGE")
        return raw
    except FileNotFoundError:
        return None
    except OSError:
        raise SettingsError("SETTINGS_READ_DENIED") from None


def _revision(raw):
    return ABSENT_REVISION if raw is None else hashlib.sha256(raw).hexdigest()


def _hotkey(value):
    # Match only syntax the resident parser actually implements; no fallback to V.
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        raise SettingsError("SETTINGS_INVALID_HOTKEY")
    aliases = {"control": "ctrl", "menu": "alt", "windows": "win", "super": "win",
               "escape": "esc", "return": "enter"}
    parts = [aliases.get(part.strip().lower(), part.strip().lower()) for part in value.split("+")]
    modifiers = {"ctrl", "alt", "shift", "win"}
    keys = [part for part in parts if part not in modifiers]
    if (len(parts) != len(set(parts)) or len(keys) != 1
            or not any(part in modifiers for part in parts)
            or not re.fullmatch(r"[a-z0-9]|f(?:[1-9]|1[0-2])|esc|space|tab|enter", keys[0])):
        raise SettingsError("SETTINGS_INVALID_HOTKEY")
    return frozenset(parts)


def _validate(overrides):
    from pluma.config.loader import _load_yaml, _DEFAULTS_FILE, _merge, get

    config = _merge(_load_yaml(_DEFAULTS_FILE), overrides)
    hotkeys = [_hotkey(get(config, "agent", key, default="ctrl+alt+v"))
               for key in ("text_hotkey", "stop_hotkey", "voice_hotkey")]
    if len(set(hotkeys)) != 3:
        raise SettingsError("SETTINGS_HOTKEY_CONFLICT")
    steps = get(config, "agent", "max_plan_steps")
    # Existing planner hard cap; importing its contracts does not load a model.
    from pluma.brain.schemas import MAX_PLAN_STEPS_HARD_CAP
    if type(steps) is not int or not 1 <= steps <= MAX_PLAN_STEPS_HARD_CAP:
        raise SettingsError("SETTINGS_INVALID_PLAN_LIMIT")
    # Saving cannot launder legacy overrides that violate the locked runtime laws.
    required = {
        "voice.required": True, "voice.wake_phrase_enabled": False,
        "agent.continuous_screen_polling": False,
        "policy.confirm_high_risk": True, "policy.permanent_elevation": False,
        "policy.redact_sensitive_logs": True,
        "stop.block_new_steps_immediately": True, "stop.rollback_reversible_actions": True,
        "stop.terminate_owned_unresponsive_workers": True, "stop.touch_preexisting_user_apps": False,
        "memory.save_chain_of_thought": False, "memory.deterministic_activity_text": True,
        "perception.uia_first": True, "perception.coordinate_fallback_requires_fresh_snapshot": True,
    }
    for field, expected in required.items():
        if get(config, *field.split(".")) is not expected:
            raise SettingsError("SETTINGS_UNSAFE_OVERRIDE")


def _apply(overrides, changes):
    if type(changes) is not dict or not changes or set(changes) - EDITABLE_FIELDS:
        raise SettingsError("SETTINGS_UNSUPPORTED_FIELD")
    result = deepcopy(overrides)
    for field, value in changes.items():
        section, key = field.split(".")
        if key == "model_path":
            if (not isinstance(value, str) or len(value) > 4096 or "\0" in value
                    or value.startswith(("\\\\", "//")) or not Path(value).is_absolute()):
                raise SettingsError("SETTINGS_INVALID_MODEL_PATH")
            try:
                if not Path(value).is_file():
                    raise SettingsError("SETTINGS_INVALID_MODEL_PATH")
                with Path(value).open("rb") as stream:
                    if not stream.read(1):
                        raise SettingsError("SETTINGS_INVALID_MODEL_PATH")
            except OSError:
                raise SettingsError("SETTINGS_INVALID_MODEL_PATH") from None
        if section in result and not isinstance(result[section], dict):
            raise SettingsError("SETTINGS_INVALID_DOCUMENT")
        result.setdefault(section, {})[key] = value
    _validate(result)
    return result


def _replace(path, raw, *, directory=None):
    """Flush a private sibling, atomically replace, then independently read back."""
    fd, name = tempfile.mkstemp(prefix=".pluma-settings-", suffix=".tmp", dir=directory or path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        # Only our exclusively created sibling may be removed.
        temporary.unlink(missing_ok=True)


@contextmanager
def _exclusive(path):
    """Non-waiting cross-process writer lock. Never unlink a shared lock inode."""
    if path.is_symlink():
        raise SettingsError("SETTINGS_LINK_REFUSED")
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SettingsError("SETTINGS_BUSY") from None
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


class SettingsStore:
    """Validated storage for a future admitted Save operation, never live apply."""

    def __init__(self, path):
        self.path = Path(path)
        if (not self.path.is_absolute() or self.path.suffix.lower() != ".json"
                or str(self.path).startswith(("\\\\", "//"))):
            raise SettingsError("SETTINGS_INVALID_STORAGE_PATH")
        self.backup_path = self.path.with_name(self.path.name + ".previous")

    def snapshot(self):
        raw = _read(self.path)
        overrides, version = ({}, SCHEMA_VERSION) if raw is None else decode_settings(raw)
        return SettingsSnapshot(overrides, _revision(raw), version)

    def previous(self):
        raw = _read(self.backup_path)
        if raw is None:
            raise SettingsError("SETTINGS_NO_PREVIOUS")
        overrides, version = decode_settings(raw)
        _validate(overrides)
        return SettingsSnapshot(overrides, _revision(raw), version)

    def save(self, changes, *, expected_revision, scratch_dir=None):
        # Reject malformed requests before creating even a lock or directory.
        if type(changes) is not dict or not changes or set(changes) - EDITABLE_FIELDS:
            raise SettingsError("SETTINGS_UNSUPPORTED_FIELD")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with _exclusive(self.path.with_name(self.path.name + ".lock")):
                before = _read(self.path)
                if _revision(before) != expected_revision:
                    raise SettingsError("SETTINGS_CONFLICT")
                overrides = {} if before is None else decode_settings(before)[0]
                # Keep last-known-valid evidence, not a corrupt/security-invalid backup.
                _validate(overrides)
                updated = _apply(overrides, changes)
                try:
                    payload = json.dumps({"settings_schema_version": SCHEMA_VERSION, "overrides": updated},
                                         ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2).encode("utf-8")
                except (ValueError, UnicodeError, TypeError, RecursionError):
                    raise SettingsError("SETTINGS_INVALID_DOCUMENT") from None
                if len(payload) > MAX_SETTINGS_BYTES:
                    raise SettingsError("SETTINGS_TOO_LARGE")
                if before is not None:
                    if self.backup_path.is_symlink():
                        raise SettingsError("SETTINGS_LINK_REFUSED")
                    _replace(self.backup_path, before, directory=scratch_dir)
                    if _read(self.backup_path) != before:
                        raise SettingsError("SETTINGS_BACKUP_UNVERIFIED")
                if _read(self.path) != before:
                    raise SettingsError("SETTINGS_CONFLICT")
                try:
                    _replace(self.path, payload, directory=scratch_dir)
                    readback = self.snapshot()
                    if readback.revision != _revision(payload) or readback.overrides != updated:
                        raise SettingsError("SETTINGS_WRITE_UNVERIFIED")
                    return readback
                except (OSError, SettingsError):
                    # Restore only our exact just-written bytes; never overwrite an
                    # intervening external editor. An uncertain commit is not success.
                    restored = False
                    try:
                        current = _read(self.path)
                        if current == payload:
                            if before is None:
                                self.path.unlink()
                            else:
                                _replace(self.path, before, directory=scratch_dir)
                            restored = _read(self.path) == before
                        elif current == before:
                            restored = True
                    except (OSError, SettingsError):
                        pass
                    raise SettingsError("SETTINGS_SAVE_FAILED", restored=restored) from None
        except OSError:
            raise SettingsError("SETTINGS_WRITE_DENIED") from None
