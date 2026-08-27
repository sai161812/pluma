"""pluma.tools.files — File system tool implementations.

Spec §11, §13, §14: File operations as registered ToolSpecs.
Pre-state is captured for reversible tools (move_file, rename_file, create_folder).
Postconditions are read back before reporting success.

Boundary: No OS libs imported at module level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from pluma.tools.base import AdapterPriority, RiskClass, ToolResult, ToolSpec, VerifyResult
from pluma.verify.common import (
    verify_dir_created,
    verify_file_moved,
    verify_file_renamed,
    verify_noop,
)


# ---------------------------------------------------------------------------
# Argument Schemas
# ---------------------------------------------------------------------------

class ListFilesArgs(BaseModel):
    """Arguments for list_files."""
    model_config = {"extra": "forbid"}
    path: str = Field(default=".", description="Directory path to inspect.")
    max_depth: int = Field(default=1, ge=1, le=5, description="Maximum recursion depth.")
    include_hidden: bool = Field(default=False, description="Whether to include hidden files.")


class FindFileArgs(BaseModel):
    """Arguments for find_file."""
    model_config = {"extra": "forbid"}
    directory: str = Field(default=".", description="Root directory to search within.")
    pattern: str = Field(min_length=1, max_length=128, description="Glob search pattern (e.g. '*.txt').")
    max_depth: int = Field(default=5, ge=1, le=10, description="Maximum directory search depth.")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum number of matches to return.")


class MoveFileArgs(BaseModel):
    """Arguments for move_file."""
    model_config = {"extra": "forbid"}
    source: str = Field(min_length=1, description="Source file or folder path.")
    destination: str = Field(min_length=1, description="Destination directory or target file path.")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing destination.")


class RenameFileArgs(BaseModel):
    """Arguments for rename_file."""
    model_config = {"extra": "forbid"}
    path: str = Field(min_length=1, description="Target file or folder to rename.")
    new_name: str = Field(min_length=1, max_length=255, description="New filename or relative name.")


class CreateFolderArgs(BaseModel):
    """Arguments for create_folder."""
    model_config = {"extra": "forbid"}
    path: str = Field(min_length=1, description="Directory path to create.")
    exist_ok: bool = Field(default=True, description="Do not raise if directory already exists.")


# ---------------------------------------------------------------------------
# Undo Builders
# ---------------------------------------------------------------------------

def undo_builder_move_file(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture pre-state before moving a file."""
    import os
    from pathlib import Path
    
    src = str(Path(args["source"]).resolve())
    dst_input = Path(args["destination"])
    
    if not os.path.exists(src):
        return None
        
    if dst_input.is_dir() or args["destination"].endswith(("/", "\\")):
        dst = str((dst_input / Path(src).name).resolve())
    else:
        dst = str(dst_input.resolve())
        
    return {
        "action": "move_file",
        "source": src,
        "destination": dst,
        "destination_existed": os.path.exists(dst),
    }


def undo_builder_rename_file(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture pre-state before renaming a file."""
    import os
    from pathlib import Path
    
    target = str(Path(args["path"]).resolve())
    if not os.path.exists(target):
        return None
        
    parent = Path(target).parent
    new_target = str((parent / args["new_name"]).resolve())
    
    return {
        "action": "rename_file",
        "original_path": target,
        "new_path": new_target,
    }


def undo_builder_create_folder(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Capture pre-state before creating a directory."""
    import os
    from pathlib import Path
    
    target = str(Path(args["path"]).resolve())
    existed = os.path.exists(target)
    return {
        "action": "create_folder",
        "path": target,
        "existed_before": existed,
    }


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------

def execute_list_files(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import os
    from pathlib import Path
    
    target_dir = Path(args.get("path", ".")).resolve()
    if not target_dir.exists():
        return ToolResult.failure("list_files", f"Directory '{target_dir}' does not exist.")
    if not target_dir.is_dir():
        return ToolResult.failure("list_files", f"Path '{target_dir}' is not a directory.")
        
    include_hidden = args.get("include_hidden", False)
    entries: List[Dict[str, Any]] = []
    
    try:
        for entry in os.scandir(target_dir):
            if not include_hidden and entry.name.startswith("."):
                continue
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "path": str(Path(entry.path).resolve()),
                "is_dir": entry.is_dir(),
                "size_bytes": stat.st_size if not entry.is_dir() else 0,
                "modified_at": stat.st_mtime,
            })
            
        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        count = len(entries)
        return ToolResult(
            ok=True,
            tool="list_files",
            data={"path": str(target_dir), "count": count, "entries": entries},
            factual_message=f"Listed {count} item{'s' if count != 1 else ''} in '{target_dir}'.",
            verified=True,
        )
    except Exception as e:
        return ToolResult.failure("list_files", str(e))


def execute_find_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import fnmatch
    import os
    from pathlib import Path
    
    root_dir = Path(args.get("directory", ".")).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        return ToolResult.failure("find_file", f"Search root '{root_dir}' does not exist or is not a directory.")
        
    pattern = args["pattern"]
    max_depth = args.get("max_depth", 5)
    max_results = args.get("max_results", 50)
    
    matches: List[Dict[str, Any]] = []
    root_depth = len(root_dir.parts)
    
    try:
        for current_root, dirs, files in os.walk(root_dir):
            current_path = Path(current_root)
            depth = len(current_path.parts) - root_depth
            if depth >= max_depth:
                dirs.clear()  # Do not recurse further
                
            for name in files + dirs:
                if fnmatch.fnmatch(name, pattern):
                    full_p = current_path / name
                    is_d = full_p.is_dir()
                    matches.append({
                        "name": name,
                        "path": str(full_p.resolve()),
                        "is_dir": is_d,
                    })
                    if len(matches) >= max_results:
                        break
            if len(matches) >= max_results:
                break
                
        count = len(matches)
        return ToolResult(
            ok=True,
            tool="find_file",
            data={"pattern": pattern, "count": count, "matches": matches},
            factual_message=f"Found {count} match{'es' if count != 1 else ''} for '{pattern}'.",
            verified=True,
        )
    except Exception as e:
        return ToolResult.failure("find_file", str(e))


def execute_move_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import os
    import shutil
    from pathlib import Path
    
    src = Path(args["source"]).resolve()
    dst = Path(args["destination"]).resolve()
    overwrite = args.get("overwrite", False)
    
    if not src.exists():
        return ToolResult.failure("move_file", f"Source '{src}' does not exist.")
        
    if dst.is_dir():
        final_dst = dst / src.name
    else:
        final_dst = dst
        
    if final_dst.exists() and not overwrite and final_dst != src:
        return ToolResult.failure("move_file", f"Destination '{final_dst}' already exists and overwrite=False.")
        
    try:
        final_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(final_dst))
        
        # Postcondition verification
        v_res = verify_file_moved(src, final_dst)
        return ToolResult(
            ok=v_res.ok,
            tool="move_file",
            data={"source": str(src), "destination": str(final_dst)},
            factual_message=f"Moved '{src.name}' to '{final_dst}'.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except Exception as e:
        return ToolResult.failure("move_file", str(e))


def execute_rename_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    import os
    from pathlib import Path
    
    target = Path(args["path"]).resolve()
    new_name = args["new_name"]
    
    if not target.exists():
        return ToolResult.failure("rename_file", f"Target '{target}' does not exist.")
        
    new_path = target.parent / new_name
    if new_path.exists() and new_path != target:
        return ToolResult.failure("rename_file", f"Destination '{new_path}' already exists.")
        
    try:
        target.rename(new_path)
        v_res = verify_file_renamed(target, new_path)
        return ToolResult(
            ok=v_res.ok,
            tool="rename_file",
            data={"original_path": str(target), "new_path": str(new_path)},
            factual_message=f"Renamed '{target.name}' to '{new_name}'.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except Exception as e:
        return ToolResult.failure("rename_file", str(e))


def execute_create_folder(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pathlib import Path
    
    target = Path(args["path"]).resolve()
    exist_ok = args.get("exist_ok", True)
    
    try:
        target.mkdir(parents=True, exist_ok=exist_ok)
        v_res = verify_dir_created(target)
        return ToolResult(
            ok=v_res.ok,
            tool="create_folder",
            data={"path": str(target)},
            factual_message=f"Created folder '{target}'.",
            verified=v_res.ok,
            verify_detail=v_res,
        )
    except Exception as e:
        return ToolResult.failure("create_folder", str(e))


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def verify_list_files(result: ToolResult) -> VerifyResult:
    return verify_noop(result)


def verify_find_file(result: ToolResult) -> VerifyResult:
    return verify_noop(result)


def verify_move_file(result: ToolResult) -> VerifyResult:
    if not result.ok or "source" not in result.data or "destination" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Move operation reported failure.")
    return verify_file_moved(result.data["source"], result.data["destination"])


def verify_rename_file(result: ToolResult) -> VerifyResult:
    if not result.ok or "original_path" not in result.data or "new_path" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Rename operation reported failure.")
    return verify_file_renamed(result.data["original_path"], result.data["new_path"])


def verify_create_folder(result: ToolResult) -> VerifyResult:
    if not result.ok or "path" not in result.data:
        return VerifyResult(ok=False, method="api", detail="Create folder reported failure.")
    return verify_dir_created(result.data["path"])


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

FILE_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="list_files",
        description="List files and directories within a folder with metadata.",
        args_schema=ListFilesArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        executor=execute_list_files,
        verifier=verify_list_files,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="find_file",
        description="Search for files matching a pattern in a directory tree.",
        args_schema=FindFileArgs,
        risk_class=RiskClass.READ,
        timeout_s=10.0,
        executor=execute_find_file,
        verifier=verify_find_file,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="move_file",
        description="Move a file or folder to a new destination path.",
        args_schema=MoveFileArgs,
        risk_class=RiskClass.MEDIUM,
        timeout_s=15.0,
        executor=execute_move_file,
        verifier=verify_move_file,
        undo_builder=undo_builder_move_file,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="rename_file",
        description="Rename a file or folder in place.",
        args_schema=RenameFileArgs,
        risk_class=RiskClass.MEDIUM,
        timeout_s=5.0,
        executor=execute_rename_file,
        verifier=verify_rename_file,
        undo_builder=undo_builder_rename_file,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
    ToolSpec(
        name="create_folder",
        description="Create a directory path on disk.",
        args_schema=CreateFolderArgs,
        risk_class=RiskClass.LOW,
        timeout_s=5.0,
        executor=execute_create_folder,
        verifier=verify_create_folder,
        undo_builder=undo_builder_create_folder,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
        creates_resources=True,
    ),
]
