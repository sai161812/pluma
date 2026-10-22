"""pluma.rollback.recipes — Rollback recipe registry.

Spec §13, §17: Tool-specific evidence-based undo procedures.
Before a reversible state change, the executor captures only the minimum
previous state required to restore it. Rollback is used automatically for
a stopped/failed task when restoration is safe.

No heavy ML or OS-automation libraries in this module.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class RollbackStepResult:
    """Result of attempting to reverse a single action."""
    ok: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Default recipe handlers
# ---------------------------------------------------------------------------

def _recipe_memory_write(undo_data: Dict[str, Any]) -> RollbackStepResult:
    from pluma.memory.tool_store import restore
    try:
        restore(undo_data)
        return RollbackStepResult(ok=True, action="memory_write", message="Restored previous memory value.")
    except Exception:
        return RollbackStepResult(ok=False, action="memory_write",
            message="Memory undo conflicted or could not be verified.", error="ROLLBACK_CONFLICT")


def _recipe_clipboard_restore(undo_data):
    from pluma.adapters.clipboard_native import write
    try:
        entry = undo_data['clipboard_private']
        if ({key: value for key, value in undo_data.items() if key != 'clipboard_private'} != entry['record']
                or undo_data.get('guard_version') != 1 or undo_data.get('volatile') is not True
                or entry['after_proof'] is None):
            raise ValueError('Clipboard undo lacks exact private evidence.')
        proof = write(entry['clipboard_before'], entry['after_proof'])
        return RollbackStepResult(ok=True, action='clipboard_restore', message='Restored previous clipboard text.',
                                  data={'clipboard_inverse_proof': proof})
    except Exception:
        return RollbackStepResult(ok=False, action='clipboard_restore',
            message='Clipboard changed or private undo is unavailable; preserved current contents.', error='ROLLBACK_CONFLICT')


def _recipe_window_focus(undo_data):
    from pluma.adapters.window_focus import restore
    try:
        restore(undo_data)
        return RollbackStepResult(ok=True, action='window_focus', message='Restored captured foreground and placement.')
    except Exception:
        return RollbackStepResult(ok=False, action='window_focus',
            message='Foreground changed or inverse was not permitted/verified.', error='ROLLBACK_CONFLICT')


def _recipe_window_state(undo_data):
    from pluma.adapters.window_state import restore
    try:
        restore(undo_data)
        return RollbackStepResult(ok=True, action='window_state', message='Restored captured window placement.')
    except Exception:
        return RollbackStepResult(ok=False, action='window_state',
            message='Window placement changed or inverse could not be verified.', error='ROLLBACK_CONFLICT')


def _recipe_window_geometry(undo_data):
    from pluma.adapters.window_geometry import restore
    try:
        restore(undo_data)
        return RollbackStepResult(ok=True, action='window_geometry', message='Restored captured window geometry.')
    except Exception:
        return RollbackStepResult(ok=False, action='window_geometry',
            message='Window undo conflicted or could not be verified.', error='ROLLBACK_CONFLICT')


def _recipe_pending_mutation(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Unknown partial effects are retained, never guessed at by a generic inverse."""
    if undo_data.get('tool') == 'safe_delete':
        from pluma.adapters.recycle_bin import recover_pending
        try:
            proof = recover_pending(undo_data['pre_state'])
            return RollbackStepResult(ok=True, action='pending_mutation',
                message='Recovered the captured recycle intent by native identity.', data=proof)
        except Exception:
            return RollbackStepResult(ok=False, action='pending_mutation',
                message='Recycle recovery conflicts or lacks exact identity evidence.', error='ROLLBACK_CONFLICT')
    return RollbackStepResult(ok=False, action="pending_mutation",
        message="Mutation outcome is unverified. Pre-state retained for safe recovery.",
        error="MUTATION_OUTCOME_UNKNOWN", data={"operation_id": undo_data.get("operation_id"),
            "tool": undo_data.get("tool"), "pre_state_retained": True})

def _recipe_guarded_file(undo_data: Dict[str, Any]) -> RollbackStepResult:
    from pluma.adapters.file_identity import restore
    try:
        if undo_data.get('cross_volume') is True:
            from pluma.adapters.cross_volume_move import restore as restore_cross_volume
            restore_cross_volume(undo_data)
        else:
            restore(undo_data)
        return RollbackStepResult(ok=True, action=undo_data["action"], message="Restored captured filesystem target.")
    except Exception:
        return RollbackStepResult(ok=False, action=undo_data["action"],
            message="Filesystem undo conflicted or could not be verified.", error="ROLLBACK_CONFLICT")


def _recipe_move_file(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Restore a moved file or directory back to its source location, preserving any newer conflicting content."""
    if undo_data.get("guard_version") == 1:
        return _recipe_guarded_file(undo_data)
    src = Path(undo_data.get("source", ""))
    dst = Path(undo_data.get("destination", ""))
    backup_path_str = undo_data.get("preserved_destination_backup")

    if not dst.exists():
        return RollbackStepResult(
            ok=False,
            action="move_file",
            message=f"Cannot undo move: '{dst}' no longer exists.",
            error=f"Destination '{dst}' not found.",
        )

    try:
        # FAIL-CLOSED: If new content exists at source, refuse to touch either file
        if src.exists() and src != dst:
            return RollbackStepResult(
                ok=False,
                action="move_file",
                message=(
                    f"Rollback conflict: cannot restore '{dst}' to '{src}' because "
                    f"'{src}' already contains new user content. Both files preserved "
                    f"unchanged. Manual resolution required."
                ),
                error="ROLLBACK_CONFLICT",
                data={
                    "conflict": True,
                    "current_path": str(dst),
                    "conflict_path": str(src),
                    "action_required": "manual",
                },
            )

        # If source parent directory doesn't exist, ensure it exists
        if not src.parent.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))

        # Restore preserved destination file if it was overwritten
        if backup_path_str:
            backup_path = Path(backup_path_str)
            if backup_path.exists():
                shutil.move(str(backup_path), str(dst))

        if not src.exists() or (not backup_path_str and dst.exists()):
            raise RuntimeError("Move rollback postcondition failed.")
        if backup_path_str and (Path(backup_path_str).exists() or not dst.exists()):
            raise RuntimeError("Backup restoration postcondition failed.")

        return RollbackStepResult(
            ok=True,
            action="move_file",
            message=f"Restored '{dst.name}' back to '{src}'.",
            data={"restored_path": str(src)},
        )
    except Exception as e:
        return RollbackStepResult(
            ok=False,
            action="move_file",
            message=f"Failed to restore '{dst}' to '{src}': {e}",
            error=str(e),
        )


def _recipe_rename_file(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Rename a file or directory back to its original name, preserving any newer conflicting content."""
    if undo_data.get("guard_version") == 1:
        return _recipe_guarded_file(undo_data)
    orig = Path(undo_data.get("original_path", ""))
    curr = Path(undo_data.get("new_path", ""))

    if not curr.exists():
        return RollbackStepResult(
            ok=False,
            action="rename_file",
            message=f"Cannot undo rename: '{curr}' does not exist.",
            error=f"Path '{curr}' not found.",
        )

    try:
        # FAIL-CLOSED: If new content exists at original path, refuse to touch either file
        if orig.exists() and orig != curr:
            return RollbackStepResult(
                ok=False,
                action="rename_file",
                message=(
                    f"Rollback conflict: cannot restore '{curr}' to '{orig}' because "
                    f"'{orig}' already contains new user content. Both files preserved "
                    f"unchanged. Manual resolution required."
                ),
                error="ROLLBACK_CONFLICT",
                data={
                    "conflict": True,
                    "current_path": str(curr),
                    "conflict_path": str(orig),
                    "action_required": "manual",
                },
            )

        curr.rename(orig)
        if not orig.exists() or curr.exists():
            raise RuntimeError("Rename rollback postcondition failed.")
        return RollbackStepResult(
            ok=True,
            action="rename_file",
            message=f"Renamed '{curr.name}' back to '{orig.name}'.",
            data={"restored_path": str(orig)},
        )
    except Exception as e:
        return RollbackStepResult(
            ok=False,
            action="rename_file",
            message=f"Failed to rename '{curr}' back to '{orig}': {e}",
            error=str(e),
        )


def _recipe_safe_delete(undo_data: Dict[str, Any]) -> RollbackStepResult:
    from pluma.adapters.recycle_bin import restore, verify
    try:
        restore(undo_data)
        if not verify(undo_data, restored=True):
            raise ValueError('Recycle inverse readback failed.')
        return RollbackStepResult(ok=True, action='safe_delete', message='Restored the exact recycled file.')
    except Exception:
        return RollbackStepResult(ok=False, action='safe_delete',
            message='Recycle restore conflicted or could not be verified.', error='ROLLBACK_CONFLICT')


def _recipe_created_target(undo_data: Dict[str, Any]) -> RollbackStepResult:
    from pluma.adapters.file_operations import restore_copy, restore_folder, verify_restored
    try:
        operation = restore_copy if undo_data['action'] == 'copy_file' else restore_folder
        operation(undo_data)
        if not verify_restored(undo_data):
            raise ValueError('Inverse readback failed.')
        return RollbackStepResult(ok=True, action=undo_data['action'], message="Reversed captured filesystem creation.")
    except Exception:
        return RollbackStepResult(ok=False, action=undo_data['action'],
            message="Filesystem undo conflicted or could not be verified.", error="ROLLBACK_CONFLICT")


def _recipe_create_folder(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Delete a created folder only if still empty and task-created."""
    if undo_data.get('guard_version') == 1:
        return _recipe_created_target(undo_data)
    p = Path(undo_data.get("path", ""))
    existed_before = undo_data.get("existed_before", False)

    if existed_before:
        # Folder existed before task, nothing to remove
        return RollbackStepResult(
            ok=True,
            action="create_folder",
            message=f"Folder '{p}' existed prior to task; preserved.",
            data={"path": str(p), "preserved": True},
        )

    if not p.exists():
        return RollbackStepResult(
            ok=True,
            action="create_folder",
            message=f"Created folder '{p}' already removed.",
            data={"path": str(p)},
        )

    try:
        # Spec §13: Delete only if still task-owned and unchanged (empty)
        if any(p.iterdir()):
            return RollbackStepResult(
                ok=False,
                action="create_folder",
                message=f"Cannot remove created folder '{p}': directory is not empty.",
                error="Directory not empty.",
            )
        p.rmdir()
        if p.exists():
            raise RuntimeError("Folder rollback postcondition failed.")
        return RollbackStepResult(
            ok=True,
            action="create_folder",
            message=f"Removed created folder '{p}'.",
            data={"removed_path": str(p)},
        )
    except Exception as e:
        return RollbackStepResult(
            ok=False,
            action="create_folder",
            message=f"Failed to remove folder '{p}': {e}",
            error=str(e),
        )


def _recipe_set_volume(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Restore only the captured endpoint with an unchanged verified post-state."""
    try:
        from pluma.tools.audio import restore_audio
        restore_audio(undo_data)
        return RollbackStepResult(ok=True, action=undo_data['action'],
            message='Restored captured audio endpoint state.')
    except Exception:
        return RollbackStepResult(ok=False, action=undo_data.get('action', 'set_volume'),
            message='Audio undo conflicts or could not be verified.', error='ROLLBACK_CONFLICT')


def _recipe_mute(undo_data: Dict[str, Any]) -> RollbackStepResult:
    return _recipe_set_volume(undo_data)


# ---------------------------------------------------------------------------
# RollbackRecipes Registry
# ---------------------------------------------------------------------------

class RollbackRecipes:
    """Registry of tool-specific rollback recipes."""

    def __init__(self) -> None:
        self._recipes: Dict[str, Callable[[Dict[str, Any]], RollbackStepResult]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("memory_write", _recipe_memory_write)
        self.register('clipboard_restore', _recipe_clipboard_restore)
        self.register("window_geometry", _recipe_window_geometry)
        self.register("window_state", _recipe_window_state)
        self.register("window_focus", _recipe_window_focus)
        self.register("pending_mutation", _recipe_pending_mutation)
        self.register("move_file", _recipe_move_file)
        self.register("rename_file", _recipe_rename_file)
        self.register("create_folder", _recipe_create_folder)
        self.register("copy_file", _recipe_created_target)
        self.register("safe_delete", _recipe_safe_delete)
        self.register("set_volume", _recipe_set_volume)
        self.register("set_default_audio_device", _recipe_set_volume)
        self.register("mute", _recipe_mute)
        self.register("unmute", _recipe_mute)

    def register(
        self,
        action_name: str,
        handler: Callable[[Dict[str, Any]], RollbackStepResult],
    ) -> None:
        """Register a custom rollback handler for an action."""
        self._recipes[action_name] = handler

    def get_recipe(
        self,
        action_name: str,
    ) -> Optional[Callable[[Dict[str, Any]], RollbackStepResult]]:
        """Return the rollback handler for an action or None if non-reversible."""
        return self._recipes.get(action_name)

    def is_reversible(self, action_name: str) -> bool:
        """Return True if a rollback recipe exists for the given action."""
        return action_name in self._recipes

    def apply(self, action_name: str, undo_data: Dict[str, Any]) -> RollbackStepResult:
        """Apply the rollback recipe for *action_name* using *undo_data*."""
        recipe = self.get_recipe(action_name)
        if recipe is None:
            return RollbackStepResult(
                ok=False,
                action=action_name,
                message=f"Action '{action_name}' has no registered rollback recipe (non-undoable).",
                error="Non-undoable action.",
            )
        try:
            return recipe(undo_data)
        except Exception as e:
            logger.exception("Rollback recipe execution failed for %s: %s", action_name, e)
            return RollbackStepResult(
                ok=False,
                action=action_name,
                message=f"Rollback recipe for '{action_name}' failed: {e}",
                error=str(e),
            )
