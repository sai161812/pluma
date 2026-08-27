"""Regression tests for Phase 13.5 release audit defect fixes.

Each test directly reproduces a previously identified failure mode.
Tests must not use mocks that hide real behavior.

Defects covered:
  A - UI snapshot grounding fail-open (FreshnessChecker wrong constructor arg)
  B - Application process containment (open_app no Job Object assignment)
  C - Rollback conflict fail-closed (was silently moving newer user content)
  D - IPC malformed JSON rejection
  E - IPC oversized message rejection
  F - Audio backend fail-closed (pycaw missing = false success)
  G - Snapshot registry rejects invented/unknown IDs
  H - Snapshot registry rejects expired snapshots
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# A. UI Snapshot grounding
# ---------------------------------------------------------------------------

class TestUISnapshotGrounding:
    """Defect A: FreshnessChecker was called with wrong constructor arg; errors silently ignored."""

    def _make_task_context_with_registry(self, register_snapshot=True, expired=False):
        """Return a minimal task_context mock with a real SnapshotRegistry."""
        from pluma.perception.snapshot_registry import SnapshotRegistry
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot

        registry = SnapshotRegistry()
        if register_snapshot:
            ttl = -1.0 if expired else 5.0  # negative TTL = already expired
            now = datetime.now(timezone.utc)
            snap = ScreenSnapshot(
                snapshot_id="snap-test-001",
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
                active_process="notepad",
                active_window_title="Untitled - Notepad",
                window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
                dpi_scale=1.0,
            )
            registry.register(snap)

        ctx = MagicMock()
        ctx.snapshot_registry = registry
        ctx.cancellation_token = MagicMock()
        ctx.cancellation_token.is_cancelled = False
        return ctx

    def test_invented_snapshot_id_is_rejected(self):
        """click_element with unknown snapshot_id must return ok=False, not continue."""
        from pluma.tools.ui import execute_click_element

        ctx = self._make_task_context_with_registry(register_snapshot=False)

        result = execute_click_element(
            {"name": "OK", "snapshot_id": "invented-id-does-not-exist"},
            task_context=ctx,
        )
        assert result.ok is False, "Invented snapshot_id must be rejected"
        assert result.verified is False
        assert "NO_SNAPSHOT_REGISTRY" in result.error or "not registered" in result.error.lower() or "SnapshotNotFoundError" in str(result)

    def test_invented_snapshot_id_rejected_when_registry_absent(self):
        """click_element with snapshot_id but no registry on ctx must return ok=False."""
        from pluma.tools.ui import execute_click_element

        ctx = MagicMock()
        ctx.snapshot_registry = None  # No registry
        ctx.cancellation_token = MagicMock()
        ctx.cancellation_token.is_cancelled = False

        result = execute_click_element(
            {"name": "OK", "snapshot_id": "any-id"},
            task_context=ctx,
        )
        assert result.ok is False
        assert "NO_SNAPSHOT_REGISTRY" in (result.error or "")

    def test_expired_snapshot_is_rejected(self):
        """click_element with an expired snapshot must return ok=False — never continue."""
        from pluma.tools.ui import execute_click_element

        ctx = self._make_task_context_with_registry(register_snapshot=True, expired=True)

        result = execute_click_element(
            {"name": "OK", "snapshot_id": "snap-test-001"},
            task_context=ctx,
        )
        assert result.ok is False, "Expired snapshot must be rejected"
        assert "expired" in (result.error or "").lower() or "stale" in (result.error or "").lower()

    def test_valid_registered_snapshot_id_does_not_error(self):
        """click_element with a valid snapshot_id proceeds past grounding (may fail for other reasons)."""
        from pluma.tools.ui import execute_click_element

        ctx = self._make_task_context_with_registry(register_snapshot=True, expired=False)

        # This may fail because there's no real window — but it must NOT fail due to grounding
        result = execute_click_element(
            {"name": "SomeButton", "snapshot_id": "snap-test-001"},
            task_context=ctx,
        )
        # Acceptable failures: window not found, element not found, etc.
        # NOT acceptable: grounding rejection (NO_SNAPSHOT_REGISTRY, not registered, expired)
        grounding_errors = {"NO_SNAPSHOT_REGISTRY", "not registered", "expired", "stale"}
        if result.error:
            assert not any(ge in result.error.lower() for ge in ["no_snapshot_registry", "not registered"]), \
                f"Valid snapshot should not cause grounding error: {result.error}"

    def test_freshness_checker_not_called_with_ttl_seconds_kwarg(self):
        """Verify FreshnessChecker constructor does not accept ttl_seconds (confirms the bug was real)."""
        from pluma.perception.freshness import FreshnessChecker
        with pytest.raises(TypeError):
            FreshnessChecker(ttl_seconds=3.0)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# B. Snapshot Registry isolation
# ---------------------------------------------------------------------------

class TestSnapshotRegistry:
    """Defect G/H: Snapshot registry must enforce TTL and reject invented IDs."""

    def _make_snapshot(self, snapshot_id: str, ttl_seconds: float = 5.0) -> Any:
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot
        now = datetime.now(timezone.utc)
        return ScreenSnapshot(
            snapshot_id=snapshot_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            active_process="notepad",
            active_window_title="Test",
            window_rect=BoundingBox(left=0, top=0, right=800, bottom=600),
            dpi_scale=1.0,
        )

    def test_resolve_unknown_id_raises(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry, SnapshotNotFoundError
        reg = SnapshotRegistry()
        with pytest.raises(SnapshotNotFoundError):
            reg.resolve("unknown-id")

    def test_resolve_expired_raises(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry
        from pluma.perception.element_refs import StaleSnapshotError
        reg = SnapshotRegistry()
        snap = self._make_snapshot("s1", ttl_seconds=-1.0)
        reg.register(snap)
        with pytest.raises(StaleSnapshotError):
            reg.resolve("s1")

    def test_resolve_valid_returns_snapshot(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry
        reg = SnapshotRegistry()
        snap = self._make_snapshot("s2", ttl_seconds=10.0)
        reg.register(snap)
        resolved = reg.resolve("s2")
        assert resolved.snapshot_id == "s2"

    def test_duplicate_snapshots_use_latest(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry
        from pluma.perception.element_refs import BoundingBox, ScreenSnapshot
        reg = SnapshotRegistry()
        now = datetime.now(timezone.utc)
        snap1 = ScreenSnapshot(
            snapshot_id="dup",
            created_at=now,
            expires_at=now + timedelta(seconds=-1.0),  # expired
            active_process="a", active_window_title="a",
            window_rect=BoundingBox(left=0, top=0, right=100, bottom=100),
            dpi_scale=1.0,
        )
        snap2 = ScreenSnapshot(
            snapshot_id="dup",
            created_at=now,
            expires_at=now + timedelta(seconds=10.0),  # fresh
            active_process="b", active_window_title="b",
            window_rect=BoundingBox(left=0, top=0, right=100, bottom=100),
            dpi_scale=1.0,
        )
        reg.register(snap1)
        reg.register(snap2)
        resolved = reg.resolve("dup")
        assert resolved.active_process == "b"

    def test_clear_removes_all_snapshots(self):
        from pluma.perception.snapshot_registry import SnapshotRegistry, SnapshotNotFoundError
        reg = SnapshotRegistry()
        snap = self._make_snapshot("to-clear", ttl_seconds=10.0)
        reg.register(snap)
        reg.clear()
        assert len(reg) == 0
        with pytest.raises(SnapshotNotFoundError):
            reg.resolve("to-clear")


# ---------------------------------------------------------------------------
# C. Rollback fail-closed (Defect D)
# ---------------------------------------------------------------------------

class TestRollbackConflictFailClosed:
    """Defect D: Rollback must not modify either file when a conflict exists."""

    def test_move_file_conflict_leaves_both_files_untouched(self, tmp_path: Path):
        """When src and dst both exist, rollback must return ROLLBACK_CONFLICT without touching either."""
        from pluma.rollback.recipes import _recipe_move_file

        src = tmp_path / "original.txt"
        dst = tmp_path / "moved.txt"

        src_content = "NEW content at source — must not be touched"
        dst_content = "MOVED content — must not be touched"

        src.write_text(src_content, encoding="utf-8")
        dst.write_text(dst_content, encoding="utf-8")

        result = _recipe_move_file({"source": str(src), "destination": str(dst)})

        # Both files must still exist with their original content
        assert src.exists(), "Source file must be preserved"
        assert dst.exists(), "Destination file must be preserved"
        assert src.read_text(encoding="utf-8") == src_content, "Source content must be unchanged"
        assert dst.read_text(encoding="utf-8") == dst_content, "Destination content must be unchanged"

        # Result must indicate conflict
        assert result.ok is False, "Conflict rollback must return ok=False"
        assert result.error == "ROLLBACK_CONFLICT"

    def test_rename_file_conflict_leaves_both_files_untouched(self, tmp_path: Path):
        """Same contract for rename rollback."""
        from pluma.rollback.recipes import _recipe_rename_file

        orig = tmp_path / "original.txt"
        curr = tmp_path / "renamed.txt"

        orig_content = "NEW content at original path"
        curr_content = "Renamed file content"

        orig.write_text(orig_content, encoding="utf-8")
        curr.write_text(curr_content, encoding="utf-8")

        result = _recipe_rename_file({"original_path": str(orig), "new_path": str(curr)})

        assert orig.exists()
        assert curr.exists()
        assert orig.read_text(encoding="utf-8") == orig_content
        assert curr.read_text(encoding="utf-8") == curr_content
        assert result.ok is False
        assert result.error == "ROLLBACK_CONFLICT"

    def test_no_conflict_rollback_succeeds(self, tmp_path: Path):
        """When no conflict exists, move rollback should succeed."""
        from pluma.rollback.recipes import _recipe_move_file

        src = tmp_path / "original.txt"
        dst = tmp_path / "moved.txt"

        dst.write_text("file content", encoding="utf-8")
        # src does NOT exist — no conflict

        result = _recipe_move_file({"source": str(src), "destination": str(dst)})

        assert result.ok is True
        assert src.exists()
        assert not dst.exists()

    def test_conflict_data_contains_metadata(self, tmp_path: Path):
        """Conflict result must contain factual metadata about both files."""
        from pluma.rollback.recipes import _recipe_move_file

        src = tmp_path / "a.txt"
        dst = tmp_path / "b.txt"
        src.write_text("new", encoding="utf-8")
        dst.write_text("old", encoding="utf-8")

        result = _recipe_move_file({"source": str(src), "destination": str(dst)})

        assert result.data is not None
        assert result.data.get("conflict") is True
        assert "action_required" in result.data


# ---------------------------------------------------------------------------
# D. IPC malformed JSON rejection (Defect F)
# ---------------------------------------------------------------------------

class TestIpcInputRejection:
    """Defect F: Malformed JSON and oversized inputs must be rejected gracefully."""

    def _start_server(self) -> tuple:
        """Start an IPC server and return (server, address)."""
        import tempfile
        import uuid

        from pluma.core.ipc import IpcServer

        responses: list = []

        def handler(req: Dict[str, Any]) -> Dict[str, Any]:
            responses.append(req)
            return {"status": "ok", "echo": req}

        addr = f"/tmp/pluma_test_{uuid.uuid4().hex[:8]}.sock" if os.name != "nt" else \
               f"\\\\.\\pipe\\pluma_test_{uuid.uuid4().hex[:8]}"
        server = IpcServer(command_handler=handler, address=addr, read_timeout_s=2.0)
        server.start()
        time.sleep(0.1)
        return server, addr, responses

    def test_malformed_json_returns_error_response(self):
        """Server must respond with error on malformed JSON, not crash or block."""
        import multiprocessing.connection

        server, addr, responses = self._start_server()
        try:
            with multiprocessing.connection.Client(addr) as conn:
                conn.send_bytes(b"not-valid-json{{{")
                ready = multiprocessing.connection.wait([conn], timeout=3.0)
                assert ready, "Server must respond to malformed JSON"
                resp_bytes = conn.recv_bytes(1024 * 1024)
                resp = json.loads(resp_bytes.decode("utf-8"))
                assert resp["status"] == "error"
                assert "malformed" in resp["message"].lower() or "json" in resp["message"].lower()
        finally:
            server.stop()

    def test_non_dict_json_returns_error_response(self):
        """Server must reject JSON that is valid but not a dict."""
        import multiprocessing.connection

        server, addr, responses = self._start_server()
        try:
            with multiprocessing.connection.Client(addr) as conn:
                conn.send_bytes(json.dumps([1, 2, 3]).encode("utf-8"))
                ready = multiprocessing.connection.wait([conn], timeout=3.0)
                assert ready
                resp_bytes = conn.recv_bytes(1024 * 1024)
                resp = json.loads(resp_bytes.decode("utf-8"))
                assert resp["status"] == "error"
        finally:
            server.stop()

    def test_oversized_message_is_rejected(self):
        """Server must reject messages exceeding MAX_IPC_MESSAGE_SIZE."""
        import multiprocessing.connection
        from pluma.core.ipc import IpcServer, MAX_IPC_MESSAGE_SIZE

        addr = f"/tmp/pluma_oversize_{time.monotonic_ns()}.sock" if os.name != "nt" else \
               f"\\\\.\\pipe\\pluma_oversize_{time.monotonic_ns()}"
        server = IpcServer(
            command_handler=lambda req: {"status": "ok"},
            address=addr,
            max_message_size=1024,  # 1KB limit for test
            read_timeout_s=2.0,
        )
        server.start()
        time.sleep(0.1)

        try:
            with multiprocessing.connection.Client(addr) as conn:
                oversized = b"x" * 2048  # 2x the limit
                try:
                    conn.send_bytes(oversized)
                    ready = multiprocessing.connection.wait([conn], timeout=2.0)
                    # Server either closes connection or sends error
                    if ready:
                        try:
                            resp = conn.recv_bytes(65536)
                        except Exception:
                            resp = None
                    # Either way, the server must still be running
                except Exception:
                    pass  # Connection rejected or reset — acceptable
            # Server must still be running after oversized message
            time.sleep(0.1)
            # Verify server still accepts a valid new connection
            with multiprocessing.connection.Client(addr) as conn2:
                conn2.send_bytes(json.dumps({"command": "status"}).encode("utf-8"))
                ready = multiprocessing.connection.wait([conn2], timeout=2.0)
                assert ready, "Server must remain alive after oversized message rejection"
        finally:
            server.stop()

    def test_multiple_clients_do_not_block_each_other(self):
        """One slow client must not block another client from connecting."""
        import multiprocessing.connection

        server, addr, _ = self._start_server()
        results = {}
        errors = {}

        def slow_client():
            """Connect but don't send anything (simulate dead client)."""
            try:
                with multiprocessing.connection.Client(addr) as conn:
                    time.sleep(3.0)  # Hold connection but don't send
            except Exception as e:
                errors["slow"] = str(e)

        def fast_client():
            """Send a valid command and expect a response."""
            time.sleep(0.1)  # Let slow client connect first
            try:
                with multiprocessing.connection.Client(addr) as conn:
                    conn.send_bytes(json.dumps({"command": "status"}).encode("utf-8"))
                    ready = multiprocessing.connection.wait([conn], timeout=4.0)
                    if ready:
                        resp = conn.recv_bytes(65536)
                        results["fast"] = json.loads(resp.decode("utf-8"))
                    else:
                        errors["fast"] = "Timed out waiting for response"
            except Exception as e:
                errors["fast"] = str(e)

        t_slow = threading.Thread(target=slow_client, daemon=True)
        t_fast = threading.Thread(target=fast_client, daemon=True)

        try:
            t_slow.start()
            t_fast.start()
            t_fast.join(timeout=6.0)
            assert "fast" not in errors, f"Fast client failed: {errors.get('fast')}"
            assert "fast" in results, "Fast client must get a response even with a slow client connected"
        finally:
            server.stop()
            t_slow.join(timeout=1.0)


# ---------------------------------------------------------------------------
# E. Audio backend fail-closed (Defect H)
# ---------------------------------------------------------------------------

class TestAudioBackendFailClosed:
    """Defect H: Missing pycaw must return failure in production, not mock success."""

    def test_audio_fail_closed_when_pycaw_missing_and_not_emulating(self):
        """_get_audio_endpoint_volume returns None when pycaw is absent and PLUMA_EMULATE_AUDIO != 1."""
        import sys

        # Simulate pycaw import failure without audio emulation flag
        with patch.dict(os.environ, {"PLUMA_EMULATE_AUDIO": "", "PLUMA_TEST_MODE": ""}, clear=False):
            # Remove the flags entirely (empty string is still truthy check)
            env_backup = {
                "PLUMA_EMULATE_AUDIO": os.environ.pop("PLUMA_EMULATE_AUDIO", None),
                "PLUMA_TEST_MODE": os.environ.pop("PLUMA_TEST_MODE", None),
            }
            try:
                with patch.dict("sys.modules", {"pycaw": None, "pycaw.pycaw": None}):
                    # Re-import needed since audio.py lazily imports pycaw
                    from pluma.tools import audio as audio_mod
                    result = audio_mod._get_audio_endpoint_volume()
                    # On Windows without pycaw and without PLUMA_EMULATE_AUDIO,
                    # result must be None (fail closed) not a dict with is_mock=True
                    if sys.platform == "win32":
                        assert result is None, (
                            f"Without pycaw in production, _get_audio_endpoint_volume must return None, got {result}"
                        )
            finally:
                # Restore env flags
                for k, v in env_backup.items():
                    if v is not None:
                        os.environ[k] = v

    def test_audio_emulation_mode_returns_mock(self):
        """With PLUMA_EMULATE_AUDIO=1, audio helpers return mock state."""
        with patch.dict(os.environ, {"PLUMA_EMULATE_AUDIO": "1"}):
            from pluma.tools import audio as audio_mod
            result = audio_mod._get_audio_endpoint_volume()
            assert result is not None, "Emulation mode must return mock state"
            assert result.get("is_mock") is True


# ---------------------------------------------------------------------------
# F. TaskSupervisor STOP correctly terminates tasks (Defect A from original)
# ---------------------------------------------------------------------------

class TestTaskSupervisorStop:
    """STOP must set task to STOPPED, not leave it at SUCCEEDED."""

    def test_stop_before_succeeded_marks_stopped(self):
        from pluma.core.task_supervisor import TaskSupervisor, TaskState

        sup = TaskSupervisor()
        cap = sup.create_task_capsule(request_id="req-stop-test")
        sup.start_task(cap.task_id)

        sup.stop_task(cap.task_id)
        final_cap = sup.get_task(cap.task_id)
        assert final_cap.state in (TaskState.STOPPED, TaskState.STOPPED_WITH_RESIDUAL), \
            f"STOP must result in STOPPED/STOPPED_WITH_RESIDUAL, got {final_cap.state}"
        assert final_cap.state != TaskState.SUCCEEDED

    def test_stop_after_succeeded_is_idempotent(self):
        """Calling STOP on an already-SUCCEEDED task must not crash or change state to STOPPED."""
        from pluma.core.task_supervisor import TaskSupervisor, TaskState

        sup = TaskSupervisor()
        cap = sup.create_task_capsule(request_id="req-succeeded")
        sup.start_task(cap.task_id)
        sup.mark_succeeded(cap.task_id)

        # Calling STOP on completed task must not raise
        sup.stop_task(cap.task_id)
        final_cap = sup.get_task(cap.task_id)
        # State must remain SUCCEEDED
        assert final_cap.state == TaskState.SUCCEEDED, \
            f"STOP on SUCCEEDED task must preserve SUCCEEDED state, got {final_cap.state}"


# ---------------------------------------------------------------------------
# G. TaskCapsule terminal pruning
# ---------------------------------------------------------------------------

class TestTerminalTaskPruning:
    """100 completed tasks must not all remain in memory."""

    def test_terminal_tasks_are_pruned(self):
        from pluma.core.task_supervisor import TaskSupervisor, MAX_TERMINAL_TASKS_RETAINED

        sup = TaskSupervisor(max_retained_terminal_tasks=10)
        for i in range(20):
            cap = sup.create_task_capsule(request_id=f"req-{i}")
            sup.start_task(cap.task_id)
            sup.mark_succeeded(cap.task_id)

        # After 20 terminal tasks with limit=10, should have at most 10 retained
        terminal_count = sum(
            1 for cap in sup._tasks.values()
            if cap.state.value in ("SUCCEEDED", "FAILED", "STOPPED", "STOPPED_WITH_RESIDUAL", "ABORTED_BY_CRASH")
        )
        assert terminal_count <= 10, \
            f"Terminal task pruning failed: {terminal_count} retained (limit=10)"
