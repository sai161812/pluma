"""P21 persistence fixtures: only private temporary settings/storage are used."""

import json
from pathlib import Path

import pytest

from pluma.config.settings import ABSENT_REVISION, SettingsError, SettingsStore


@pytest.mark.parametrize("supplied_config", [None, {}])
def test_runtime_reads_its_selected_roaming_settings(tmp_path, monkeypatch, supplied_config):
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.paths import PlumaPaths

    monkeypatch.delenv("PLUMA_CONFIG", raising=False)
    paths = PlumaPaths(tmp_path / "local", tmp_path / "selected-roaming")
    paths.roaming_root.mkdir()
    paths.user_settings_path.write_text(
        json.dumps({"agent": {"max_plan_steps": 3}}), encoding="utf-8"
    )
    runtime = PlumaApplicationRuntime(paths=paths, config=supplied_config)
    try:
        assert runtime.config["agent"]["max_plan_steps"] == 3
        assert runtime.llm_lifecycle.adapter.max_plan_steps == 3
    finally:
        assert runtime.close().complete


def test_missing_explicit_environment_path_never_loads_another_user_file(tmp_path, monkeypatch):
    from pluma.config.loader import load_config

    roaming = tmp_path / "roaming"
    (roaming / "PLUMA").mkdir(parents=True)
    (roaming / "PLUMA" / "user_settings.json").write_text(
        '{"agent":{"max_plan_steps":2}}', encoding="utf-8"
    )
    monkeypatch.setenv("APPDATA", str(roaming))
    monkeypatch.setenv("PLUMA_CONFIG", str(tmp_path / "missing.json"))
    assert load_config()["agent"]["max_plan_steps"] == 8


def test_atomic_save_reload_restart_and_cold_effective_readback(tmp_path):
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.loader import load_config
    from pluma.config.paths import PlumaPaths

    paths = PlumaPaths(tmp_path / "local", tmp_path / "roaming")
    planner, stt = tmp_path / "planner.gguf", tmp_path / "speech.bin"
    planner.write_bytes(b"owned model path fixture")
    stt.write_bytes(b"owned model path fixture")
    store = SettingsStore(paths.user_settings_path)
    first = store.snapshot()
    assert first.revision == ABSENT_REVISION and first.overrides == {}
    changes = {"agent.max_plan_steps": 4, "agent.text_hotkey": "ctrl+shift+p",
               "agent.stop_hotkey": "ctrl+shift+s", "agent.voice_hotkey": "ctrl+shift+v",
               "brain.model_path": str(planner), "voice.model_path": str(stt)}
    saved = store.save(changes, expected_revision=first.revision)
    assert saved.revision != first.revision and saved.schema_version == 1
    assert SettingsStore(paths.user_settings_path).snapshot() == saved
    assert not list(paths.roaming_root.glob(".pluma-settings-*.tmp"))
    # A newly constructed actual runtime consumes the disk settings, not a
    # fixture-injected config. It never opens a desktop or starts inference.
    for _ in range(2):
        runtime = PlumaApplicationRuntime(paths=paths)
        try:
            view = runtime.resident_core.handle_ipc_command({
                "protocol_version": 1, "message_type": "settings_query",
                "request_id": "9eb00b7f-69f5-4bc1-b6ef-360de5234bc1"})
            assert view["max_plan_steps"] == runtime.llm_lifecycle.adapter.max_plan_steps == 4
            assert view["text_hotkey"] == "ctrl+shift+p"
            assert view["stop_hotkey"] == "ctrl+shift+s"
            assert view["voice_hotkey"] == runtime.resident_core.voice_hotkey_str == "ctrl+shift+v"
            assert view["planner_model_path"] == str(planner)
            assert view["stt_model_path"] == runtime.voice_lifecycle.model_path == str(stt)
            assert runtime.llm_lifecycle.state.value == "COLD"
            assert runtime.voice_lifecycle.state == "COLD"
            assert not runtime.voice_lifecycle.adapter.is_loaded
        finally:
            assert runtime.close().complete
    assert load_config(paths.user_settings_path)["agent"]["max_plan_steps"] == 4


def test_legacy_migration_preserves_unrelated_keys_and_exact_previous_bytes(tmp_path):
    from pluma.config.loader import load_config

    path = tmp_path / "user_settings.json"
    before = b'{"agent":{"max_plan_steps":3},"custom":{"unicode":"\\u65e5", "value":42}}'
    path.write_bytes(before)
    store = SettingsStore(path)
    original = store.snapshot()
    assert original.schema_version == 0
    assert path.read_bytes() == before  # Read/migrate never writes automatically.
    store.save({"agent.text_hotkey": "ctrl+shift+p"}, expected_revision=original.revision)
    assert store.backup_path.read_bytes() == before
    assert store.previous().overrides == original.overrides
    config = load_config(path)
    assert config["custom"] == {"unicode": "日", "value": 42}
    assert config["agent"]["max_plan_steps"] == 3
    assert config["voice"]["required"] is True


def test_stale_editor_cannot_overwrite_saved_changes(tmp_path):
    path = tmp_path / "settings.json"
    one, two = SettingsStore(path), SettingsStore(path)
    old = two.snapshot()
    saved = one.save({"agent.max_plan_steps": 3}, expected_revision=old.revision)
    with pytest.raises(SettingsError, match="SETTINGS_CONFLICT"):
        two.save({"agent.max_plan_steps": 5}, expected_revision=old.revision)
    assert one.snapshot() == saved


def test_cancel_is_read_only_and_snapshot_has_no_shared_mutable_cache(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    draft = store.snapshot()
    draft.overrides["agent"] = {"max_plan_steps": 2}
    assert store.snapshot().overrides == {}
    assert not path.exists() and not store.backup_path.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change,code", [
    ({"agent.max_plan_steps": True}, "INVALID_PLAN_LIMIT"),
    ({"agent.max_plan_steps": 0}, "INVALID_PLAN_LIMIT"),
    ({"agent.max_plan_steps": 21}, "INVALID_PLAN_LIMIT"),
    ({"agent.text_hotkey": "ctrl+wat+v"}, "INVALID_HOTKEY"),
    ({"agent.text_hotkey": "ctrl+v+q"}, "INVALID_HOTKEY"),
    ({"agent.text_hotkey": "é"}, "INVALID_HOTKEY"),
    ({"agent.text_hotkey": "ctrl++p"}, "INVALID_HOTKEY"),
    ({"agent.stop_hotkey": "control+alt+v"}, "HOTKEY_CONFLICT"),
    ({"agent.voice_hotkey": "SPACE + ALT"}, "HOTKEY_CONFLICT"),
    ({"brain.model_path": "relative.gguf"}, "INVALID_MODEL_PATH"),
    ({"brain.model_path": "https://example.com/model"}, "INVALID_MODEL_PATH"),
    ({"voice.model_path": r"\\server\share\model.bin"}, "INVALID_MODEL_PATH"),
    ({"voice.required": False}, "UNSUPPORTED_FIELD"),
    ({"policy.confirm_high_risk": False}, "UNSUPPORTED_FIELD"),
    ({"policy.permanent_elevation": True}, "UNSUPPORTED_FIELD"),
    ({"voice.wake_phrase_enabled": True}, "UNSUPPORTED_FIELD"),
    ({"runtime.allow_short_warm_grace": True}, "UNSUPPORTED_FIELD"),
    ({"voice.save_audio": True}, "UNSUPPORTED_FIELD"),
])
def test_invalid_or_unimplemented_fields_preserve_valid_settings(tmp_path, change, code):
    path = tmp_path / "settings.json"
    path.write_text('{"agent":{"max_plan_steps":3}}', encoding="utf-8")
    before = path.read_bytes()
    store = SettingsStore(path)
    with pytest.raises(SettingsError, match="SETTINGS_" + code):
        store.save(change, expected_revision=store.snapshot().revision)
    assert path.read_bytes() == before
    assert not store.backup_path.exists()


@pytest.mark.parametrize("target", ["missing", "empty", "directory"])
def test_model_path_requires_readable_nonempty_file(tmp_path, target):
    path = tmp_path / target
    if target == "empty":
        path.touch()
    if target == "directory":
        path.mkdir()
    store = SettingsStore(tmp_path / "settings.json")
    with pytest.raises(SettingsError, match="SETTINGS_INVALID_MODEL_PATH"):
        store.save({"brain.model_path": str(path)}, expected_revision=ABSENT_REVISION)
    assert not store.path.exists()


@pytest.mark.parametrize("raw", [b"{", b"[]", b'{"x":NaN}', b'{"x":1e999}', b'{"x":1,"x":2}',
    b'{"settings_schema_version":2,"overrides":{}}',
    b'{"settings_schema_version":true,"overrides":{}}',
    b'{"settings_schema_version":1,"overrides":{},"surprise":true}',
    b'{"settings_schema_version":1,"overrides":[]}', b'\xff', b' ' * (256 * 1024 + 1)])
def test_corrupt_or_unknown_version_is_preserved_and_never_falls_back(tmp_path, raw):
    from pluma.config.loader import load_config

    path = tmp_path / "settings.json"
    path.write_bytes(raw)
    with pytest.raises(SettingsError):
        load_config(path)
    assert path.read_bytes() == raw


def test_failed_write_keeps_previous_and_removes_only_owned_temporary(tmp_path, monkeypatch):
    import pluma.config.settings as settings

    path = tmp_path / "settings.json"
    path.write_bytes(b'{"agent":{"max_plan_steps":3}}')
    unrelated = tmp_path / "unrelated.tmp"
    unrelated.write_bytes(b"preserve")
    store = SettingsStore(path)
    before = path.read_bytes()
    real_replace = settings.os.replace
    def deny(source, destination):
        if Path(destination) == path:
            raise PermissionError("PRIVATE_SYNTHETIC_DO_NOT_LOG")
        real_replace(source, destination)
    monkeypatch.setattr(settings.os, "replace", deny)
    with pytest.raises(SettingsError) as caught:
        store.save({"agent.max_plan_steps": 4}, expected_revision=store.snapshot().revision)
    assert caught.value.code == "SETTINGS_SAVE_FAILED" and caught.value.restored
    assert "PRIVATE_SYNTHETIC" not in str(caught.value)
    assert path.read_bytes() == store.backup_path.read_bytes() == before
    assert unrelated.read_bytes() == b"preserve"
    assert not list(tmp_path.glob(".pluma-settings-*.tmp"))


def test_failed_postcommit_readback_restores_previous_with_verified_bytes(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_bytes(b'{"agent":{"max_plan_steps":3}}')
    store = SettingsStore(path)
    revision = store.snapshot().revision
    before = path.read_bytes()
    monkeypatch.setattr(store, "snapshot", lambda: (_ for _ in ()).throw(SettingsError("READBACK_FAULT")))
    with pytest.raises(SettingsError) as caught:
        store.save({"agent.max_plan_steps": 4}, expected_revision=revision)
    assert caught.value.code == "SETTINGS_SAVE_FAILED" and caught.value.restored
    assert path.read_bytes() == before


def test_failed_readback_does_not_overwrite_intervening_external_edit(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    external = b'{"agent":{"max_plan_steps":6}}'
    def changed_readback():
        path.write_bytes(external)
        raise SettingsError("READBACK_FAULT")
    monkeypatch.setattr(store, "snapshot", changed_readback)
    with pytest.raises(SettingsError) as caught:
        store.save({"agent.max_plan_steps": 4}, expected_revision=ABSENT_REVISION)
    assert not caught.value.restored
    assert path.read_bytes() == external


def test_busy_writer_returns_immediately_without_changing_file(tmp_path):
    from pluma.config.settings import _exclusive
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    with _exclusive(path.with_name(path.name + ".lock")):
        with pytest.raises(SettingsError, match="SETTINGS_BUSY"):
            store.save({"agent.max_plan_steps": 4}, expected_revision=ABSENT_REVISION)
    assert not path.exists()


def test_valid_previous_remains_readable_after_corruption_without_silent_restore(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b'{"agent":{"max_plan_steps":3}}')
    store = SettingsStore(path)
    store.save({"agent.max_plan_steps": 4}, expected_revision=store.snapshot().revision)
    path.write_bytes(b"{corrupt")
    with pytest.raises(SettingsError):
        store.snapshot()
    assert store.previous().overrides == {"agent": {"max_plan_steps": 3}}
    assert path.read_bytes() == b"{corrupt"


def test_unsafe_existing_overrides_are_not_laundered_into_valid_backup(tmp_path):
    path = tmp_path / "settings.json"
    path.write_bytes(b'{"policy":{"permanent_elevation":true}}')
    store = SettingsStore(path)
    before = path.read_bytes()
    with pytest.raises(SettingsError, match="SETTINGS_UNSAFE_OVERRIDE"):
        store.save({"agent.max_plan_steps": 4}, expected_revision=store.snapshot().revision)
    assert path.read_bytes() == before and not store.backup_path.exists()


def test_loader_honors_pluma_appdata_override(tmp_path, monkeypatch):
    from pluma.config.loader import load_config
    monkeypatch.delenv("PLUMA_CONFIG", raising=False)
    monkeypatch.setenv("PLUMA_APPDATA", str(tmp_path))
    (tmp_path / "user_settings.json").write_bytes(b'{"agent":{"max_plan_steps":5}}')
    assert load_config()["agent"]["max_plan_steps"] == 5


def test_native_windows_locked_destination_cannot_report_success(tmp_path):
    """Real Windows sharing denial, against only this owned settings fixture."""
    import win32con
    import win32file

    path = tmp_path / "settings.json"
    path.write_bytes(b'{"agent":{"max_plan_steps":3}}')
    store = SettingsStore(path)
    before = path.read_bytes()
    revision = store.snapshot().revision
    handle = win32file.CreateFile(str(path), win32con.GENERIC_READ,
        win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, 0, None)
    try:
        with pytest.raises(SettingsError) as caught:
            store.save({"agent.max_plan_steps": 4}, expected_revision=revision)
        assert caught.value.code == "SETTINGS_SAVE_FAILED" and caught.value.restored
        assert path.read_bytes() == before
    finally:
        handle.Close()
    assert store.snapshot().revision == revision
    assert store.previous().overrides == {"agent": {"max_plan_steps": 3}}
    assert not list(tmp_path.glob(".pluma-settings-*.tmp"))


def test_backup_denial_prevents_primary_write(tmp_path, monkeypatch):
    import pluma.config.settings as settings

    path = tmp_path / "settings.json"
    path.write_bytes(b'{"agent":{"max_plan_steps":3}}')
    store = SettingsStore(path)
    revision = store.snapshot().revision
    real_replace = settings.os.replace
    def deny_backup(source, destination):
        if Path(destination) == store.backup_path:
            raise PermissionError("owned injected backup denial")
        real_replace(source, destination)
    monkeypatch.setattr(settings.os, "replace", deny_backup)
    with pytest.raises(SettingsError, match="SETTINGS_WRITE_DENIED"):
        store.save({"agent.max_plan_steps": 4}, expected_revision=revision)
    assert store.snapshot().revision == revision
    assert not list(tmp_path.glob(".pluma-settings-*.tmp"))


def test_first_save_readback_failure_restores_absence(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    monkeypatch.setattr(store, "snapshot", lambda: (_ for _ in ()).throw(SettingsError("READBACK_FAULT")))
    with pytest.raises(SettingsError) as caught:
        store.save({"agent.max_plan_steps": 4}, expected_revision=ABSENT_REVISION)
    assert caught.value.restored and not path.exists()


def test_settings_storage_and_reload_import_no_device_or_ml_runtime(tmp_path):
    import subprocess
    import sys

    code = """
import sys
from pathlib import Path
from pluma.config.settings import SettingsStore, ABSENT_REVISION
from pluma.config.loader import load_config
path = Path(sys.argv[1]); store = SettingsStore(path)
store.save({'agent.max_plan_steps': 4}, expected_revision=ABSENT_REVISION)
assert load_config(path)['agent']['max_plan_steps'] == 4
for name in ('llama_cpp', 'pywhispercpp', 'whisper', 'paddle', 'paddleocr',
             'onnxruntime', 'torch', 'sounddevice', 'win32com', 'pywinauto'):
    assert name not in sys.modules, name
"""
    result = subprocess.run([sys.executable, "-c", code, str(tmp_path / "cold.json")],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_json_extension_case_and_legacy_yaml_have_explicit_semantics(tmp_path):
    from pluma.config.loader import load_config

    path = tmp_path / "settings.JSON"
    store = SettingsStore(path)
    store.save({"agent.max_plan_steps": 4}, expected_revision=ABSENT_REVISION)
    assert load_config(path)["agent"]["max_plan_steps"] == 4
    yaml_path = tmp_path / "legacy.yaml"
    yaml_path.write_text("agent:\n  max_plan_steps: 5\n", encoding="utf-8")
    assert load_config(yaml_path)["agent"]["max_plan_steps"] == 5
    with pytest.raises(SettingsError, match="SETTINGS_INVALID_STORAGE_PATH"):
        SettingsStore(yaml_path)
    assert yaml_path.read_text(encoding="utf-8") == "agent:\n  max_plan_steps: 5\n"


def test_legacy_unpaired_surrogate_fails_without_leaking_or_rewriting(tmp_path):
    path = tmp_path / "settings.json"
    before = b'{"custom":{"value":"\\ud800"}}'
    path.write_bytes(before)
    store = SettingsStore(path)
    with pytest.raises(SettingsError, match="SETTINGS_INVALID_DOCUMENT"):
        store.save({"agent.max_plan_steps": 4}, expected_revision=store.snapshot().revision)
    assert path.read_bytes() == before and not store.backup_path.exists()
