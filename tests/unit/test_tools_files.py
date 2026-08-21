"""tests.unit.test_tools_files — Unit and verification tests for File tools."""

import os
from pathlib import Path
import pytest

from pluma.tools.files import (
    execute_create_folder,
    execute_find_file,
    execute_list_files,
    execute_move_file,
    execute_rename_file,
    undo_builder_create_folder,
    undo_builder_move_file,
    undo_builder_rename_file,
)
from pluma.tools.registry import ToolRegistry, register_default_tools


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    register_default_tools(reg)
    return reg


def test_list_files_and_find_file(tmp_path: Path) -> None:
    # Setup files
    (tmp_path / "file1.txt").write_text("content 1")
    (tmp_path / "file2.log").write_text("content 2")
    sub = tmp_path / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")

    # List files
    res = execute_list_files({"path": str(tmp_path)})
    assert res.ok is True
    assert res.verified is True
    assert res.data["count"] == 3

    # Find file
    res_find = execute_find_file({"directory": str(tmp_path), "pattern": "*.txt"})
    assert res_find.ok is True
    assert res_find.verified is True
    assert res_find.data["count"] == 2


def test_create_folder_and_undo(tmp_path: Path) -> None:
    target_dir = tmp_path / "new_folder"
    args = {"path": str(target_dir)}
    
    # Capture pre-state
    undo_data = undo_builder_create_folder(args)
    assert undo_data is not None
    assert undo_data["existed_before"] is False

    # Execute
    res = execute_create_folder(args)
    assert res.ok is True
    assert res.verified is True
    assert target_dir.exists()
    assert target_dir.is_dir()


def test_move_file_and_verification(tmp_path: Path) -> None:
    src = tmp_path / "source.txt"
    src.write_text("hello move")
    dst = tmp_path / "dest.txt"
    
    args = {"source": str(src), "destination": str(dst)}
    undo_data = undo_builder_move_file(args)
    assert undo_data is not None
    assert undo_data["action"] == "move_file"

    res = execute_move_file(args)
    assert res.ok is True
    assert res.verified is True
    assert dst.exists()
    assert not src.exists()


def test_rename_file_and_verification(tmp_path: Path) -> None:
    src = tmp_path / "original.txt"
    src.write_text("rename me")
    
    args = {"path": str(src), "new_name": "renamed.txt"}
    undo_data = undo_builder_rename_file(args)
    assert undo_data is not None
    assert undo_data["action"] == "rename_file"

    res = execute_rename_file(args)
    assert res.ok is True
    assert res.verified is True
    assert (tmp_path / "renamed.txt").exists()
    assert not src.exists()
