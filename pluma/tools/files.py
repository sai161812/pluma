"""pluma.tools.files — File system tool implementations.

Spec §11, §13, §14: File operations as registered ToolSpecs.
Pre-state is captured for reversible tools (move_file, rename_file, create_folder).
Postconditions are read back before reporting success.

Boundary: No OS libs imported at module level.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

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
    model_config = {"extra": "forbid", "strict": True}
    directory: str = Field(min_length=1, max_length=32767, description="Explicit absolute search root.")
    pattern: str = Field(min_length=1, max_length=128, description="Glob search pattern (e.g. '*.txt').")
    max_depth: int = Field(default=5, ge=0, le=10, description="Directory descent depth; zero searches only the root.")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum number of matches to return.")
    max_scan_entries: int = Field(default=4096, ge=1, le=4096)
    kind: Literal['any', 'file', 'directory'] = 'any'
    created_after_ns: int | None = Field(default=None, ge=0)
    created_before_ns: int | None = Field(default=None, ge=0)
    modified_after_ns: int | None = Field(default=None, ge=0)
    modified_before_ns: int | None = Field(default=None, ge=0)

    @field_validator('directory')
    @classmethod
    def explicit_root(cls, value):
        return FileInfoArgs.explicit_filesystem_path(value)

    @field_validator('pattern')
    @classmethod
    def basename_pattern(cls, value):
        if any(char in value for char in '\\/:\0'):
            raise ValueError('Search pattern must match a basename, not a path or stream.')
        return value

    @model_validator(mode='after')
    def coherent_times(self):
        for field in ('created', 'modified'):
            after, before = getattr(self, field + '_after_ns'), getattr(self, field + '_before_ns')
            if after is not None and before is not None and after >= before:
                raise ValueError('Search time interval must be nonempty, with an inclusive lower and exclusive upper bound.')
        return self


class FileInfoArgs(BaseModel):
    """One literal, fully qualified Windows filesystem path; no search/expansion."""
    model_config = {"extra": "forbid", "strict": True}
    path: str = Field(min_length=1, max_length=32767)

    @field_validator("path")
    @classmethod
    def explicit_filesystem_path(cls, value: str) -> str:
        from pathlib import PureWindowsPath
        path = PureWindowsPath(value)
        if (not path.is_absolute() or not value.strip() or "\0" in value
                or str(path).startswith(("\\\\.\\", "\\\\?\\"))
                or any(char in value for char in '*?"<>|')
                or any(part in (".", "..") or part.endswith((".", " "))
                       or ":" in part for part in path.parts[1:])
                or any(PureWindowsPath(part).is_reserved() for part in path.parts[1:])):
            raise ValueError("An explicit absolute filesystem path without patterns or device syntax is required.")
        return value


class FileInfoData(BaseModel):
    """Native metadata only; directory size is not a recursive content total."""
    model_config = {"extra": "forbid", "strict": True, "frozen": True}
    path: str
    kind: Literal["file", "directory"]
    size_bytes: Optional[int] = Field(ge=0)
    modified_ns: int
    device: int = Field(ge=0)
    file_id: int = Field(gt=0)


class MoveFileArgs(BaseModel):
    """Arguments for move_file."""
    model_config = {"extra": "forbid", "strict": True}
    source: str = Field(min_length=1, description="Source file or folder path.")
    destination: str = Field(min_length=1, description="Destination directory or target file path.")
    overwrite: bool = Field(default=False, description="Whether to overwrite existing destination.")

    @field_validator("source", "destination")
    @classmethod
    def explicit_path(cls, value):
        return FileInfoArgs.explicit_filesystem_path(value)


_WINDOWS_RESERVED_NAMES = frozenset({
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
})


class RenameFileArgs(BaseModel):
    """Arguments for rename_file."""
    model_config = {"extra": "forbid", "strict": True}
    path: str = Field(min_length=1, description="Target file or folder to rename.")
    new_name: str = Field(min_length=1, max_length=255, description="New filename (basename only).")

    @field_validator("path")
    @classmethod
    def explicit_path(cls, value):
        return FileInfoArgs.explicit_filesystem_path(value)

    @field_validator("new_name")
    @classmethod
    def validate_new_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("new_name cannot be empty or whitespace.")
        if clean != v or v.endswith('.') or any(char in v for char in '*?"<>|:'):
            raise ValueError("new_name must be a literal Windows basename.")
        if "\0" in clean:
            raise ValueError("new_name cannot contain null bytes.")
        if any(sep in clean for sep in ("/", "\\", "..")):
            raise ValueError(f"Path traversal characters are forbidden in rename_file new_name: '{clean}'")
        from pathlib import Path
        if Path(clean).name != clean:
            raise ValueError(f"new_name must be a pure filename without path elements: '{clean}'")
        stem = clean.split(".")[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES or clean.upper() in _WINDOWS_RESERVED_NAMES:
            raise ValueError(f"Windows reserved device name is forbidden: '{clean}'")
        return clean


class CopyFileArgs(MoveFileArgs):
    """A new exact destination; replacing existing data is not permitted."""
    overwrite: Literal[False] = False

    @field_validator('overwrite', mode='before')
    @classmethod
    def exact_no_overwrite(cls, value):
        if value is not False:
            raise ValueError('Copy supports only boolean false for overwrite.')
        return value


class ListFolderArgs(FileInfoArgs):
    max_entries: int = Field(default=100, ge=1, le=200)


class CreateFolderArgs(FileInfoArgs):
    """Arguments for create_folder."""
    exist_ok: bool = Field(default=True, description="Do not raise if directory already exists.")


# ---------------------------------------------------------------------------
# Undo Builders
# ---------------------------------------------------------------------------

def undo_builder_move_file(args: Dict[str, Any]) -> Dict[str, Any]:
    from pathlib import Path
    from pluma.adapters.file_identity import capture
    source = FileInfoArgs.model_validate({"path": args["source"]}).path
    destination = FileInfoArgs.model_validate({"path": args["destination"]}).path
    if args.get("overwrite", False):
        raise ValueError("Overwrite requires a separately verified backup operation.")
    if Path(destination).is_dir():
        destination = str(Path(destination) / Path(source).name)
    from pluma.memory.redaction import redact_string
    if redact_string(source) != source or redact_string(destination) != destination:
        raise ValueError("Private path pre-state cannot be safely journaled.")
    return {"action": "move_file", "source": str(Path(source)), "destination": str(Path(destination)),
            "guard_version": 1, **capture(source, destination)}


def undo_builder_rename_file(args: Dict[str, Any]) -> Dict[str, Any]:
    from pathlib import Path
    from pluma.adapters.file_identity import capture
    source = FileInfoArgs.model_validate({"path": args["path"]}).path
    name = RenameFileArgs.model_validate(args).new_name
    destination = str(Path(source).with_name(name))
    from pluma.memory.redaction import redact_string
    if redact_string(source) != source or redact_string(destination) != destination:
        raise ValueError("Private path pre-state cannot be safely journaled.")
    return {"action": "rename_file", "original_path": str(Path(source)), "new_path": destination,
            "guard_version": 1, **capture(source, destination)}


def undo_builder_create_folder(args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from pluma.adapters.file_operations import capture_folder
    values = CreateFolderArgs.model_validate(args)
    _public_path(values.path)
    return capture_folder(values.path, values.exist_ok)


def _public_path(path):
    from pluma.memory.redaction import redact_string
    if redact_string(path) != path:
        raise ValueError("Private path pre-state cannot be safely journaled.")


def undo_builder_copy_file(args):
    from pluma.adapters.file_operations import capture_copy
    values = CopyFileArgs.model_validate(args)
    _public_path(values.source)
    _public_path(values.destination)
    return capture_copy(values.source, values.destination)


def undo_builder_safe_delete(args):
    from pluma.adapters.recycle_bin import capture
    values = FileInfoArgs.model_validate(args)
    _public_path(values.path)
    return capture(values.path)


def execute_safe_delete(args, task_context=None):
    from pluma.adapters.recycle_bin import recycle
    try:
        state = _captured_state('safe_delete', args, task_context, undo_builder_safe_delete)
        state = recycle(state, getattr(task_context, 'cancellation_token', None))
        _public_path(state['recycled_path'])
        result = ToolResult.success('safe_delete', data={'path': state['path']},
            factual_message='Moved one filesystem target to Windows Recycle Bin.', verified=False,
            adapter_used='native_shell_recycle').model_copy(update={
                'undo_record': state, 'private_context': {'recycle_receipt': state}})
        proof = verify_safe_delete(result)
        return result.model_copy(update={'verified': proof.ok, 'verify_detail': proof})
    except Exception:
        return ToolResult.failure('safe_delete',
            'Recycle operation refused or unverified. Captured intent retained; no permanent-delete fallback.',
            'RECYCLE_UNVERIFIED')


def verify_safe_delete(result):
    from pluma.adapters.recycle_bin import verify
    try:
        state = result.private_context['recycle_receipt']
        valid = (result.ok and state['action'] == 'safe_delete' and state['guard_version'] == 1
            and result.undo_record == state and result.data == {'path': state['path']} and verify(state))
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method='native_recycle_identity_and_stream_digest',
        detail='Exact recycled item verified.' if valid else 'Recycle postcondition was not verified.')


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
    max_depth = args.get("max_depth", 1)
    entries: List[Dict[str, Any]] = []
    root_depth = len(target_dir.parts)
    
    try:
        if max_depth <= 1:
            for entry in os.scandir(target_dir):
                if task_context and hasattr(task_context, "cancellation_token") and task_context.cancellation_token.is_cancelled:
                    return ToolResult.failure("list_files", "Task cancelled during file listing.", error_code="TASK_CANCELLED")
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
        else:
            for current_root, dirs, files in os.walk(target_dir):
                if task_context and hasattr(task_context, "cancellation_token") and task_context.cancellation_token.is_cancelled:
                    return ToolResult.failure("list_files", "Task cancelled during file listing.", error_code="TASK_CANCELLED")
                current_p = Path(current_root)
                depth = len(current_p.parts) - root_depth
                if depth >= max_depth:
                    dirs.clear()

                if not include_hidden:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    files = [f for f in files if not f.startswith(".")]

                for name in (dirs if depth < max_depth else []) + files:
                    full_p = current_p / name
                    is_d = full_p.is_dir()
                    try:
                        stat = full_p.stat()
                        size = stat.st_size if not is_d else 0
                        mtime = stat.st_mtime
                    except Exception:
                        size = 0
                        mtime = 0.0
                    entries.append({
                        "name": name,
                        "path": str(full_p.resolve()),
                        "is_dir": is_d,
                        "size_bytes": size,
                        "modified_at": mtime,
                    })

        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        count = len(entries)
        return ToolResult(
            ok=True,
            tool="list_files",
            data={"path": str(target_dir), "count": count, "entries": entries, "max_depth": max_depth},
            factual_message=f"Listed {count} item{'s' if count != 1 else ''} in '{target_dir}'.",
            verified=True,
        )
    except Exception as e:
        return ToolResult.failure("list_files", str(e))


def execute_find_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    from pluma.adapters.file_search import search
    from pluma.core.cancellation import TaskCancelledError
    try:
        values = FindFileArgs.model_validate(args).model_dump()
        data, proof = search(values, getattr(task_context, 'cancellation_token', None))
        result = ToolResult.success('find_file', data=data, verified=False,
            factual_message=f"Returned {data['count']} file search candidates; bounded search " +
                ('stopped at a limit.' if data['limited'] else 'completed within the requested depth.'),
            adapter_used='native_handle').model_copy(update={'private_context': {'search_observation': proof}})
        checked = verify_find_file(result)
        return result.model_copy(update={'verified': checked.ok, 'verify_detail': checked})
    except TaskCancelledError:
        return ToolResult.failure('find_file', 'File search was stopped.', 'TASK_CANCELLED')
    except Exception:
        return ToolResult.failure('find_file', 'File search could not be verified; root, access, reparse or changed-target conflict.',
                                  'FILE_SEARCH_UNVERIFIED')


def _execute_guarded_move(tool, args, task_context):
    from pluma.adapters.file_identity import move
    from pathlib import Path
    try:
        capture = undo_builder_move_file if tool == "move_file" else undo_builder_rename_file
        if task_context is not None and getattr(task_context, "undo_stack", None):
            state = next(item["pre_state"] for item in reversed(task_context.undo_stack)
                if item.get("action") == "pending_mutation" and item.get("tool") == tool)
        else:
            state = capture(args)
        source = state.get("source", state.get("original_path"))
        destination = state.get("destination", state.get("new_path"))
        if state.get("action") != tool or state.get("guard_version") != 1:
            raise ValueError("File mutation does not match its journal.")
        if tool == "move_file":
            supplied_source, supplied_destination = Path(args["source"]), Path(args["destination"])
            if args.get("overwrite", False) or Path(source) != supplied_source or Path(destination) not in (
                    supplied_destination, supplied_destination / supplied_source.name):
                raise ValueError("File mutation does not match its arguments.")
        elif Path(source) != Path(args["path"]) or Path(destination) != Path(args["path"]).with_name(args["new_name"]):
            raise ValueError("Rename does not match its arguments.")
        move(source, destination, state["identity"], getattr(task_context, "cancellation_token", None),
             parents=(state["source_parent"], state["destination_parent"]))
        data = {"source": source, "destination": destination} if tool == "move_file" else {
            "original_path": source, "new_path": destination}
        result = ToolResult.success(tool, data=data, verified=True,
            factual_message="Moved one filesystem target." if tool == "move_file" else "Renamed one filesystem target.",
            adapter_used="native_handle").model_copy(update={"private_context": {"file_move": state}})
        proof = verify_move_file(result) if tool == "move_file" else verify_rename_file(result)
        return result.model_copy(update={"verified": proof.ok, "verify_detail": proof})
    except Exception:
        return ToolResult.failure(tool, "Filesystem move was refused or could not be verified. Pre-state retained.", "FILE_MOVE_UNVERIFIED")


def execute_move_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _execute_guarded_move("move_file", args, task_context)


def execute_rename_file(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _execute_guarded_move("rename_file", args, task_context)


def _captured_state(tool, args, context, builder):
    if context is not None and getattr(context, "undo_stack", None):
        state = next(item["pre_state"] for item in reversed(context.undo_stack)
            if item.get("action") == "pending_mutation" and item.get("tool") == tool)
    else:
        state = builder(args)
    if state.get("action") != tool or state.get("guard_version") != 1:
        raise ValueError("File mutation does not match its journal.")
    from pathlib import Path
    keys = ("source", "destination") if tool == "copy_file" else ("path",)
    if any(Path(state[key]) != Path(args[key]) for key in keys):
        raise ValueError("File mutation does not match its arguments.")
    if tool == "create_folder" and state['exist_ok'] != args.get('exist_ok', True):
        raise ValueError("Folder mutation does not match its arguments.")
    return state


def _execute_created_target(tool, args, context):
    from pluma.adapters import file_operations as native
    try:
        builder = undo_builder_copy_file if tool == "copy_file" else undo_builder_create_folder
        state = _captured_state(tool, args, context, builder)
        operation = native.copy_file if tool == "copy_file" else native.create_folder
        state = operation(state, getattr(context, "cancellation_token", None))
        data = {key: state[key] for key in (("source", "destination") if tool == "copy_file" else ("path",))}
        result = ToolResult.success(tool, data=data, verified=False,
            factual_message="Copied one file." if tool == "copy_file" else
                "Existing folder verified." if state['existed_before'] else "Created folder path.",
            adapter_used="native_handle", undo_record=state).model_copy(
                update={"private_context": {"created_target": state}})
        proof = _verify_created_target(result)
        return result.model_copy(update={"verified": proof.ok, "verify_detail": proof})
    except Exception:
        return ToolResult.failure(tool, "Filesystem operation was refused or could not be verified. Pre-state retained.",
            "FILE_CREATE_UNVERIFIED")


def execute_copy_file(args, task_context=None):
    return _execute_created_target("copy_file", args, task_context)


def execute_create_folder(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    return _execute_created_target("create_folder", args, task_context)


def execute_list_folder(args, task_context=None):
    from pluma.adapters.file_operations import list_folder
    try:
        values = ListFolderArgs.model_validate(args)
        data, proof = list_folder(values.path, values.max_entries, getattr(task_context, "cancellation_token", None))
        result = ToolResult.success("list_folder", data=data, verified=False,
            factual_message="Read bounded folder entries.", adapter_used="native_handle").model_copy(
                update={"private_context": {"folder_observation": proof}})
        verification = verify_list_folder(result)
        return result.model_copy(update={"verified": verification.ok, "verify_detail": verification})
    except Exception:
        return ToolResult.failure("list_folder", "Folder entries could not be verified.", "FOLDER_READ_UNVERIFIED")


# ---------------------------------------------------------------------------
# Verifiers
# ---------------------------------------------------------------------------

def _read_file_info(path: str, task_context: Any = None) -> Dict[str, Any]:
    """Read metadata with native lstat, refusing reparse targets/ancestors."""
    import stat
    from pathlib import Path
    target = Path(path)
    token = getattr(task_context, "cancellation_token", None)
    info = None
    for component in (*reversed(target.parents), target):
        if token is not None:
            token.raise_if_cancelled()
        current = component.lstat()
        if stat.S_ISLNK(current.st_mode) or getattr(current, "st_file_attributes", 0) & 0x400:
            raise ValueError("Reparse filesystem target is unsupported.")
        if component == target:
            info = current
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise ValueError("Filesystem target type is unsupported.")
    if token is not None:
        token.raise_if_cancelled()
    return FileInfoData(path=str(target), kind="directory" if stat.S_ISDIR(info.st_mode) else "file",
        size_bytes=None if stat.S_ISDIR(info.st_mode) else info.st_size,
        modified_ns=info.st_mtime_ns, device=info.st_dev, file_id=info.st_ino).model_dump()


def execute_file_info(args: Dict[str, Any], task_context: Any = None) -> ToolResult:
    """Return two matching native metadata observations, never file contents."""
    try:
        path = FileInfoArgs.model_validate(args).path
        first = _read_file_info(path, task_context)
        if _read_file_info(path, task_context) != first:
            return ToolResult.failure("file_info", "File metadata changed during inspection.",
                                      error_code="FILE_INFO_CHANGED")
        return ToolResult.success("file_info", data=first, factual_message="File metadata read.",
                                  verified=True, adapter_used="native_api")
    except PermissionError:
        return ToolResult.failure("file_info", "File metadata access was denied.", error_code="FILE_INFO_ACCESS_DENIED")
    except FileNotFoundError:
        return ToolResult.failure("file_info", "The filesystem target was not found.", error_code="FILE_INFO_NOT_FOUND")
    except (ValueError, ValidationError):
        return ToolResult.failure("file_info", "The filesystem target is unsupported or ambiguous.",
                                  error_code="FILE_INFO_UNSUPPORTED")
    except OSError:
        return ToolResult.failure("file_info", "File metadata could not be read.", error_code="FILE_INFO_READ_FAILED")


def verify_file_info(result: ToolResult) -> VerifyResult:
    """Native reads occur in the owned worker; never repeat filesystem I/O here."""
    try:
        metadata = FileInfoData.model_validate(result.data)
        FileInfoArgs(path=metadata.path)
        consistent = ((metadata.kind == "file" and metadata.size_bytes is not None)
                      or (metadata.kind == "directory" and metadata.size_bytes is None))
        ok = result.ok and result.verified and result.adapter_used == "native_api" and consistent
    except (ValueError, ValidationError):
        ok = False
    return VerifyResult(ok=ok, method="native_api", detail="Native metadata readback verified." if ok
                        else "Native metadata readback was not verified.")


def verify_list_files(result: ToolResult) -> VerifyResult:
    return verify_noop(result)


def verify_find_file(result: ToolResult) -> VerifyResult:
    from pluma.adapters.file_search import verify
    try:
        args = FindFileArgs.model_validate({key: result.data[key] for key in FindFileArgs.model_fields}).model_dump()
        valid = (result.ok and result.adapter_used == 'native_handle'
                 and type(result.data['count']) is int and type(result.data['scanned_entries']) is int
                 and type(result.data['limited']) is bool and type(result.data['unambiguous']) is bool
                 and verify(result.data, result.private_context['search_observation'], args))
    except Exception:
        valid = False
    return VerifyResult(ok=bool(valid), method='native_candidate_and_directory_readback', detail=(
        'Bounded candidate identities and directory readback verified.' if valid else 'File search was not verified.'))


def _verify_guarded_move(result: ToolResult) -> VerifyResult:
    from pluma.adapters.file_identity import verify_move
    try:
        state = result.private_context["file_move"]
        source = state.get("source", state.get("original_path"))
        destination = state.get("destination", state.get("new_path"))
        data = {"source": source, "destination": destination} if result.tool == "move_file" else {
            "original_path": source, "new_path": destination}
        valid = result.ok and state['action'] == result.tool and result.data == data and verify_move(source, destination, state["identity"])
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method="native_identity_and_digest",
        detail="Source absence and destination identity/content verified." if valid else "Filesystem move was not verified.")


def verify_move_file(result: ToolResult) -> VerifyResult:
    return _verify_guarded_move(result)


def verify_rename_file(result: ToolResult) -> VerifyResult:
    return _verify_guarded_move(result)


def _verify_created_target(result):
    from pluma.adapters import file_operations as native
    try:
        state = result.private_context['created_target']
        keys = ("source", "destination") if result.tool == 'copy_file' else ("path",)
        valid = (result.ok and state['action'] == result.tool and state['guard_version'] == 1
            and result.undo_record == state and result.data == {key: state[key] for key in keys}
            and (native.verify_copy(state) if result.tool == 'copy_file' else native.verify_created_folder(state)))
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method="native_identity_and_digest",
        detail="Created target readback verified." if valid else "Created target was not verified.")


def verify_create_folder(result):
    return _verify_created_target(result)


def verify_copy_file(result):
    return _verify_created_target(result)


def verify_list_folder(result):
    from pluma.adapters.file_operations import verify_folder
    try:
        data = result.data
        ListFolderArgs(path=data['path'], max_entries=data['max_entries'])
        valid = (result.ok and type(data['has_more']) is bool and data['count'] == len(data['entries'])
            and 0 <= data['count'] <= data['max_entries']
            and (not data['has_more'] or data['count'] == data['max_entries'])
            and verify_folder(data, result.private_context['folder_observation']))
    except Exception:
        valid = False
    return VerifyResult(ok=valid, method="native_metadata",
        detail="Bounded folder readback verified." if valid else "Folder entries were not verified.")


# ---------------------------------------------------------------------------
# Tool Specifications
# ---------------------------------------------------------------------------

FILE_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(name='safe_delete', description='Recycle one bounded local file or folder on a fixed NTFS volume; never permanently delete.',
        args_schema=FileInfoArgs, risk_class=RiskClass.HIGH, timeout_s=15.0, process_isolated=True,
        executor=execute_safe_delete, verifier=verify_safe_delete, undo_builder=undo_builder_safe_delete,
        adapter_priority=[AdapterPriority.NATIVE_API]),
    ToolSpec(name="list_folder", description="Read bounded immediate folder entries without following reparse targets.",
        args_schema=ListFolderArgs, risk_class=RiskClass.READ, timeout_s=5.0, process_isolated=True,
        executor=execute_list_folder, verifier=verify_list_folder, adapter_priority=[AdapterPriority.NATIVE_API]),
    ToolSpec(name="copy_file", description="Copy one regular file to an exact new destination without overwriting.",
        args_schema=CopyFileArgs, risk_class=RiskClass.MEDIUM, timeout_s=15.0, process_isolated=True,
        executor=execute_copy_file, verifier=verify_copy_file, undo_builder=undo_builder_copy_file,
        adapter_priority=[AdapterPriority.NATIVE_API], creates_resources=True),
    ToolSpec(
        name="file_info",
        description="Read metadata for one explicit file or directory without reading its contents.",
        args_schema=FileInfoArgs,
        risk_class=RiskClass.READ,
        timeout_s=5.0,
        process_isolated=True,
        executor=execute_file_info,
        verifier=verify_file_info,
        undo_builder=None,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
    ),
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
        process_isolated=True,
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
        process_isolated=True,
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
        process_isolated=True,
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
        process_isolated=True,
        executor=execute_create_folder,
        verifier=verify_create_folder,
        undo_builder=undo_builder_create_folder,
        adapter_priority=[AdapterPriority.NATIVE_API],
        cancellable=True,
        creates_resources=True,
    ),
]
