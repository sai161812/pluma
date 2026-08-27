"""Unit tests for SQLite-backed PreferencesStore, AliasStore, and RoutineStore (Spec §18, §20)."""
import pytest
from pluma.memory.aliases import AliasStore
from pluma.memory.db import DbConnection
from pluma.memory.preferences import PreferencesStore
from pluma.memory.routines import RoutineStore


@pytest.fixture
def memory_db():
    conn = DbConnection(":memory:")
    conn.open()
    yield conn
    conn.close()


def test_preferences_store(memory_db):
    store = PreferencesStore(memory_db)
    assert store.get("theme", "dark") == "dark"

    store.set("theme", "light")
    assert store.get("theme") == "light"

    store.set("volume_limit", 80)
    store.set("allowed_dirs", ["C:/Work", "D:/Work"])

    all_prefs = store.all()
    assert all_prefs["theme"] == "light"
    assert all_prefs["volume_limit"] == 80
    assert all_prefs["allowed_dirs"] == ["C:/Work", "D:/Work"]

    store.delete("theme")
    assert store.get("theme") is None


def test_alias_store(memory_db):
    store = AliasStore(memory_db)
    assert store.get("work") is None

    store.set("work", {"type": "directory", "path": "D:/Workspace"})
    store.set("editor", {"type": "app", "name": "code"})

    work_alias = store.get("work")
    assert work_alias == {"type": "directory", "path": "D:/Workspace"}

    all_aliases = store.all()
    assert len(all_aliases) == 2
    assert "editor" in all_aliases

    store.delete("work")
    assert store.get("work") is None


def test_routine_store(memory_db):
    store = RoutineStore(memory_db)
    assert store.get("morning_routine") is None

    def_data = {
        "description": "Open work tools and set volume",
        "steps": [
            {"tool": "set_volume", "args": {"level": 40}},
            {"tool": "open_app", "args": {"app_name": "notepad"}},
        ]
    }

    rid = store.save("morning_routine", def_data)
    assert rid is not None

    r = store.get("morning_routine")
    assert r is not None
    assert r["name"] == "morning_routine"
    assert r["definition"] == def_data

    all_routines = store.all()
    assert len(all_routines) == 1
    assert all_routines[0]["name"] == "morning_routine"

    store.delete("morning_routine")
    assert store.get("morning_routine") is None
