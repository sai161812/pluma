"""pluma.ui.activity_contract — Activity view UI contract.

Spec §16.1, §17.1:
Activity view is a functional contract exposing access to task history,
actions, verification, timings, and rollback state without defining
visual design or styling.
"""

from __future__ import annotations

import abc
from typing import Any, Dict, List, Optional


class ActivityViewContract(abc.ABC):
    """Abstract activity view contract for PLUMA functional surfaces."""

    @abc.abstractmethod
    def show_activity(self, tasks: List[Dict[str, Any]]) -> None:
        """Display recent tasks in the Activity view."""
        raise NotImplementedError

    @abc.abstractmethod
    def show_task_detail(self, task: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
        """Display detailed step execution and rollback for a specific task."""
        raise NotImplementedError
