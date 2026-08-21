"""pluma.ui.shell_contract — Functional UI interface contract.

Spec §17.1: "Required functional surfaces only."
Spec §17: "The build guide defines required functional surfaces only. The
project owner decides how the interface looks."

This module defines the abstract functional surfaces that any PLUMA UI
implementation must provide. It does NOT define colors, typography, layout,
animations, icons, or any visual design. Those choices belong to the owner.

No OS-automation, ML, or adapter code in this module.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ShellContract(ABC):
    """Abstract contract for the PLUMA shell/UI layer.

    Any concrete UI implementation (tray-only, floating window, etc.)
    must implement these surfaces. The orchestrator calls these methods
    to interact with the user without knowing which UI technology is used.

    Spec §17.1 required functional surfaces:
      - Voice/text command entry.
      - Current task state and material confirmations.
      - Global STOP access and its keyboard hotkey.
      - Activity Ledger/history access.
      - Settings.
      - Clear error/result messages.
    """

    # ------------------------------------------------------------------
    # Command entry
    # ------------------------------------------------------------------

    @abstractmethod
    def show_command_input(self) -> None:
        """Make the command entry surface visible and focused."""
        ...

    @abstractmethod
    def hide_command_input(self) -> None:
        """Hide the command entry surface."""
        ...

    # ------------------------------------------------------------------
    # Task state and confirmations
    # ------------------------------------------------------------------

    @abstractmethod
    def show_task_running(self, task_id: str, summary: str) -> None:
        """Display that a task is in progress.

        *summary* is a short factual string from the executor template,
        e.g. "Opening Notepad...". No AI-generated text.
        """
        ...

    @abstractmethod
    def show_task_result(self, task_id: str, message: str, ok: bool) -> None:
        """Display the final factual result of a task.

        *message* comes from ToolResult.factual_message.
        """
        ...

    @abstractmethod
    def request_confirmation(
        self,
        task_id: str,
        action_description: str,
        risk_class: str,
    ) -> bool:
        """Present a concise confirmation prompt and return True if confirmed.

        Spec §14: HIGH-risk actions require material-effect confirmation.
        *action_description* is a factual one-liner, never AI-generated filler.
        """
        ...

    # ------------------------------------------------------------------
    # STOP
    # ------------------------------------------------------------------

    @abstractmethod
    def show_stopping(self, task_id: str) -> None:
        """Update the UI to indicate that STOP is in progress for *task_id*."""
        ...

    @abstractmethod
    def show_stopped(self, task_id: str, message: str) -> None:
        """Update the UI to indicate that the task has been stopped.

        *message* is a factual ledger-sourced summary.
        """
        ...

    # ------------------------------------------------------------------
    # Activity view
    # ------------------------------------------------------------------

    @abstractmethod
    def show_activity_view(self, records: List[Dict[str, Any]]) -> None:
        """Display the Activity Ledger view with *records*.

        Records are plain dicts from ActivityQuery.recent_tasks().
        Spec §16.1: reachable from tray and from the 'show activity' command.
        """
        ...

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @abstractmethod
    def show_settings(self) -> None:
        """Open the settings surface."""
        ...

    # ------------------------------------------------------------------
    # Error display
    # ------------------------------------------------------------------

    @abstractmethod
    def show_error(self, message: str, detail: Optional[str] = None) -> None:
        """Display a factual error message to the user.

        *message* and *detail* come from deterministic executor templates.
        """
        ...
