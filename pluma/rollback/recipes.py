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

def _recipe_move_file(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Restore a moved file or directory back to its source location."""
    src = Path(undo_data.get("source", ""))
    dst = Path(undo_data.get("destination", ""))

    if not dst.exists():
        return RollbackStepResult(
            ok=False,
            action="move_file",
            message=f"Cannot undo move: '{dst}' no longer exists.",
            error=f"Destination '{dst}' not found.",
        )

    try:
        # If source parent directory doesn't exist, ensure it exists
        if not src.parent.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(src))
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
    """Rename a file or directory back to its original name."""
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
        curr.rename(orig)
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


def _recipe_create_folder(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Delete a created folder only if still empty and task-created."""
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
    """Restore master volume level and mute status."""
    prev_vol = undo_data.get("previous_volume")
    prev_muted = undo_data.get("previous_muted")

    try:
        from pluma.tools.audio import _set_audio_endpoint_volume
        _set_audio_endpoint_volume(level=prev_vol, mute=prev_muted)
        return RollbackStepResult(
            ok=True,
            action="set_volume",
            message=f"Restored volume to {prev_vol}% (muted={prev_muted}).",
            data={"volume": prev_vol, "muted": prev_muted},
        )
    except Exception as e:
        return RollbackStepResult(
            ok=False,
            action="set_volume",
            message=f"Failed to restore volume: {e}",
            error=str(e),
        )


def _recipe_mute(undo_data: Dict[str, Any]) -> RollbackStepResult:
    """Restore mute status."""
    prev_muted = undo_data.get("previous_muted", False)

    try:
        from pluma.tools.audio import _set_audio_endpoint_volume
        _set_audio_endpoint_volume(mute=prev_muted)
        return RollbackStepResult(
            ok=True,
            action="mute",
            message=f"Restored mute state ({'muted' if prev_muted else 'unmuted'}).",
            data={"muted": prev_muted},
        )
    except Exception as e:
        return RollbackStepResult(
            ok=False,
            action="mute",
            message=f"Failed to restore mute status: {e}",
            error=str(e),
        )


# ---------------------------------------------------------------------------
# RollbackRecipes Registry
# ---------------------------------------------------------------------------

class RollbackRecipes:
    """Registry of tool-specific rollback recipes."""

    def __init__(self) -> None:
        self._recipes: Dict[str, Callable[[Dict[str, Any]], RollbackStepResult]] = {}
        self._register_defaults()

    def _register_defaults(self) -> None:
        self.register("move_file", _recipe_move_file)
        self.register("rename_file", _recipe_rename_file)
        self.register("create_folder", _recipe_create_folder)
        self.register("set_volume", _recipe_set_volume)
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
