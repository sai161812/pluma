"""Unit tests for RollbackRecipes (Spec §13, §17)."""
import pytest
from pathlib import Path
from pluma.rollback.recipes import RollbackRecipes, RollbackStepResult


def test_recipes_registry_defaults():
    r = RollbackRecipes()
    assert r.is_reversible('move_file')
    assert r.is_reversible('rename_file')
    assert r.is_reversible('create_folder')
    assert r.is_reversible('set_volume')
    assert r.is_reversible('mute')
    assert r.is_reversible('unmute')
    assert not r.is_reversible('non_existent_tool')


def test_recipe_move_file(tmp_path):
    r = RollbackRecipes()
    src = tmp_path / 'original.txt'
    dst = tmp_path / 'moved.txt'
    
    # Destination file exists (simulating moved state)
    dst.write_text('content')
    
    undo_data = {'action': 'move_file', 'source': str(src), 'destination': str(dst)}
    res = r.apply('move_file', undo_data)
    
    assert res.ok
    assert not dst.exists()
    assert src.exists()
    assert src.read_text() == 'content'


def test_recipe_move_file_destination_missing(tmp_path):
    r = RollbackRecipes()
    src = tmp_path / 'original.txt'
    dst = tmp_path / 'missing.txt'
    
    undo_data = {'action': 'move_file', 'source': str(src), 'destination': str(dst)}
    res = r.apply('move_file', undo_data)
    
    assert not res.ok
    assert 'no longer exists' in res.message


def test_recipe_rename_file(tmp_path):
    r = RollbackRecipes()
    orig = tmp_path / 'report_old.txt'
    new = tmp_path / 'report_new.txt'
    
    new.write_text('hello')
    
    undo_data = {'action': 'rename_file', 'original_path': str(orig), 'new_path': str(new)}
    res = r.apply('rename_file', undo_data)
    
    assert res.ok
    assert not new.exists()
    assert orig.exists()
    assert orig.read_text() == 'hello'


def test_recipe_create_folder_empty(tmp_path):
    r = RollbackRecipes()
    folder = tmp_path / 'new_folder'
    folder.mkdir()
    
    undo_data = {'action': 'create_folder', 'path': str(folder), 'existed_before': False}
    res = r.apply('create_folder', undo_data)
    
    assert res.ok
    assert not folder.exists()


def test_recipe_create_folder_not_empty_fails(tmp_path):
    r = RollbackRecipes()
    folder = tmp_path / 'new_folder_with_files'
    folder.mkdir()
    (folder / 'file.txt').write_text('keep me')
    
    undo_data = {'action': 'create_folder', 'path': str(folder), 'existed_before': False}
    res = r.apply('create_folder', undo_data)
    
    assert not res.ok
    assert 'not empty' in res.message
    assert folder.exists()


def test_recipe_create_folder_existed_before_preserved(tmp_path):
    r = RollbackRecipes()
    folder = tmp_path / 'existing_folder'
    folder.mkdir()
    
    undo_data = {'action': 'create_folder', 'path': str(folder), 'existed_before': True}
    res = r.apply('create_folder', undo_data)
    
    assert res.ok
    assert folder.exists()


def test_recipe_set_volume():
    r = RollbackRecipes()
    undo_data = {'action': 'set_volume', 'previous_volume': 35, 'previous_muted': False}
    res = r.apply('set_volume', undo_data)
    assert res.ok
    assert '35%' in res.message
