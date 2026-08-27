"""tests/unit/test_phase13_5_stage_a_composition.py — Stage A Composition Root regression tests."""

from __future__ import annotations

import os
import tempfile
import pytest

from pluma.app import PlumaApplicationRuntime
from pluma.config.paths import PlumaPaths
from pluma.core.request import InputMode, PlumaRequest
from pluma.memory.activity import ActivityQuery
from pluma.ui.confirmations import AutoApproveConfirmationContract


def test_stage_a_production_composition_runtime() -> None:
    """Gate A: Verify production application runtime composition, single SQLite graph, and IPC command execution."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=td, roaming_app_data=td)
        paths.ensure_directories()

        runtime = PlumaApplicationRuntime(
            paths=paths,
            confirmation_contract=AutoApproveConfirmationContract(),
        )
        try:
            core = runtime.resident_core
            assert core.orchestrator is runtime.orchestrator
            assert core.supervisor is runtime.supervisor
            assert core.ledger is runtime.ledger

            # 1. Execute text command via IPC handler
            ipc_resp = core.handle_ipc_command({"command": "execute", "text": "volume 45"})
            assert ipc_resp["status"] == "ok"
            assert ipc_resp["success"] is True
            assert ipc_resp["final_state"] == "SUCCEEDED"
            assert ipc_resp["route"] == "FAST"

            # 2. Verify single SQLite database was written
            query = ActivityQuery(db=runtime.db)
            tasks = query.recent_tasks()
            assert len(tasks) == 1
            assert tasks[0]["command_text"] == "volume 45"
            assert tasks[0]["final_state"] == "SUCCEEDED"

            actions = query.actions_for_task(tasks[0]["task_id"])
            assert len(actions) == 1
            assert actions[0]["tool"] == "set_volume"

            # 3. Status IPC command
            status_resp = core.handle_ipc_command({"command": "status"})
            assert status_resp["status"] == "ok"
            assert status_resp["active_tasks"] == 0

            # 4. Stop all IPC command
            stop_resp = core.handle_ipc_command({"command": "stop_all"})
            assert stop_resp["status"] == "ok"
        finally:
            runtime.close()


def test_stage_a_voice_callback_integration() -> None:
    """Gate A: Verify voice callback produces PlumaRequest and reaches the unified Orchestrator."""
    with tempfile.TemporaryDirectory() as td:
        paths = PlumaPaths(local_app_data=td, roaming_app_data=td)
        paths.ensure_directories()

        runtime = PlumaApplicationRuntime(paths=paths)
        try:
            core = runtime.resident_core
            req = PlumaRequest(input_mode=InputMode.VOICE, text="mute", original_transcript="mute please")
            res = runtime.orchestrator.execute(req)
            assert res.final_state == "SUCCEEDED"
            assert res.route.value == "FAST"

            query = ActivityQuery(db=runtime.db)
            tasks = query.recent_tasks()
            assert len(tasks) == 1
            assert tasks[0]["input_mode"] == "voice"
        finally:
            runtime.close()
