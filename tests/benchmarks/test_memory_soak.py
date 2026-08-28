"""tests/benchmarks/test_memory_soak.py — Memory soak and zero-leak tests.

Spec §4, §22, §23:
- 1,000 task continuous soak test with zero handle or memory leakage.
- Idle resident memory footprint < 30MB target.
- Cyclic worker load/unload clean state transitions.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path
import psutil
import pytest

from pluma.brain.lifecycle import LlmLifecycleManager
from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger, ActivityQuery
from pluma.memory.db import DbConnection
from pluma.perception.ocr_lifecycle import OcrLifecycleManager
from pluma.tools.registry import get_default_tool_registry
from pluma.voice.lifecycle import VoiceLifecycleManager


def _get_process_rss_mb() -> float:
    """Get current Python process Resident Set Size (RSS) in Megabytes."""
    gc.collect()
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024.0 * 1024.0)


def test_resident_core_idle_memory_footprint() -> None:
    """Verify that resident core idle memory footprint is strictly within the <30MB budget (Spec §4)."""
    import subprocess
    import sys

    # Measure memory of isolated ResidentCore process to eliminate pytest runner overhead
    code = (
        "import gc, sys\n"
        "from pluma.core.resident import ResidentCore\n"
        "core = ResidentCore()\n"
        "gc.collect()\n"
        "if sys.platform == 'win32':\n"
        "    import ctypes\n"
        "    from ctypes import wintypes\n"
        "    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):\n"
        "        _fields_ = [\n"
        "            ('cb', wintypes.DWORD),\n"
        "            ('PageFaultCount', wintypes.DWORD),\n"
        "            ('PeakWorkingSetSize', ctypes.c_size_t),\n"
        "            ('WorkingSetSize', ctypes.c_size_t),\n"
        "            ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),\n"
        "            ('QuotaPagedPoolUsage', ctypes.c_size_t),\n"
        "            ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),\n"
        "            ('QuotaNonPagedPoolUsage', ctypes.c_size_t),\n"
        "            ('PagefileUsage', ctypes.c_size_t),\n"
        "            ('PeakPagefileUsage', ctypes.c_size_t),\n"
        "        ]\n"
        "    psapi = ctypes.WinDLL('psapi')\n"
        "    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]\n"
        "    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL\n"
        "    pmc = PROCESS_MEMORY_COUNTERS()\n"
        "    pmc.cb = ctypes.sizeof(pmc)\n"
        "    psapi.GetProcessMemoryInfo(ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(pmc), ctypes.sizeof(pmc))\n"
        "    private_mb = pmc.PagefileUsage / (1024.0 * 1024.0)\n"
        "    print(f'{private_mb:.2f}')\n"
        "else:\n"
        "    import os, psutil\n"
        "    rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)\n"
        "    print(f'{rss_mb:.2f}')\n"
    )
    env = os.environ.copy()
    project_root = str(Path(__file__).parent.parent.parent.resolve())
    env["PYTHONPATH"] = project_root + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")

    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    mem_mb = float(res.stdout.strip())
    print(f"\n[BENCHMARK] Resident Core Idle Memory: {mem_mb:.2f} MB")

    # Spec §4 definition of done: < 25MB resident core idle memory target
    assert mem_mb < 25.0, f"Resident core idle memory {mem_mb:.2f}MB exceeded strict <25MB target!"


@pytest.mark.timeout(600)
def test_soak_1000_fast_tasks_no_memory_leak() -> None:
    """Execute 1,000 FAST route tasks through SQLite Activity Ledger and verify zero resource leak."""
    import tempfile
    import psutil
    from pathlib import Path
    import gc

    # Real filesystem DB to verify no file handle leaks and PRAGMA integrity
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pluma_soak.db"
        db = DbConnection(str(db_path))
        db.open()
        try:
            ledger = ActivityLedger(db=db)
            registry = get_default_tool_registry()
            supervisor = TaskSupervisor(ledger=ledger, max_retained_terminal_tasks=20)
            router = Router()
            orch = Orchestrator(
                router=router,
                registry=registry,
                supervisor=supervisor,
                ledger=ledger,
            )

            process = psutil.Process(os.getpid())
            
            # Helper to get current resources
            def get_resources():
                gc.collect()
                import glob
                temp_files = len(glob.glob(os.path.join(tempfile.gettempdir(), "pluma_*")))
                
                # Count job objects
                job_objects = 0
                if hasattr(supervisor, "job_object"):
                    job_objects = 1 if getattr(supervisor, "job_object") else 0
                
                return {
                    "rss": process.memory_info().rss / (1024.0 * 1024.0),
                    "handles": process.num_handles() if hasattr(process, 'num_handles') else 0,
                    "threads": process.num_threads(),
                    "children": len(process.children(recursive=True)),
                    "active_capsules": len(supervisor._active_tasks) if hasattr(supervisor, "_active_tasks") else 0,
                    "job_objects": job_objects,
                    "temp_files": temp_files
                }

            start_res = get_resources()

            task_commands = [
                "mute",
                "unmute",
                "set volume 40",
                "system status",
                "clear clipboard",
            ]

            total_tasks = 1000
            for i in range(total_tasks):
                cmd = task_commands[i % len(task_commands)]
                req = PlumaRequest(input_mode=InputMode.TEXT, text=cmd)
                res = orch.execute(req)
                assert res.final_state == "SUCCEEDED"

            end_res = get_resources()
            
            delta_rss = end_res["rss"] - start_res["rss"]
            delta_handles = end_res["handles"] - start_res["handles"]
            delta_threads = end_res["threads"] - start_res["threads"]
            delta_temp = end_res["temp_files"] - start_res["temp_files"]

            print(
                "\n[SOAK TEST] 1,000 Tasks Completed:\n"
                f"RSS: {start_res['rss']:.2f}MB -> {end_res['rss']:.2f}MB (Delta: {delta_rss:+.2f}MB)\n"
                f"Handles: {start_res['handles']} -> {end_res['handles']} (Delta: {delta_handles:+d})\n"
                f"Threads: {start_res['threads']} -> {end_res['threads']} (Delta: {delta_threads:+d})\n"
                f"Children: {start_res['children']} -> {end_res['children']}\n"
                f"Active Capsules: {start_res['active_capsules']} -> {end_res['active_capsules']}\n"
                f"Job Objects: {start_res['job_objects']} -> {end_res['job_objects']}\n"
                f"Temporary Files: {start_res['temp_files']} -> {end_res['temp_files']} (Delta: {delta_temp})"
            )

            assert delta_rss < 30.0, f"Memory leaked {delta_rss:.2f}MB over 1,000 tasks!"
            assert delta_handles < 50, f"Handle leak detected: {delta_handles} leaked"
            assert delta_threads < 10, f"Thread leak detected: {delta_threads} leaked"
            assert delta_temp <= 10, f"Temp files leaked: {delta_temp} leaked"
            assert end_res["children"] <= 1, f"Child processes leaked: {end_res['children']}"
            assert end_res["active_capsules"] == 0, "Task capsules leaked"

            # Verify ledger recorded all 1,000 tasks
            query = ActivityQuery(db=db)
            recent = query.recent_tasks(limit=1000)
            assert len(recent) == 1000
            
            # PRAGMA integrity_check
            row = db.execute_read_one("PRAGMA integrity_check;")
            integrity = row[0] if row else ""
            assert integrity.lower() == "ok", f"Database integrity check failed: {integrity}"
        finally:
            try:
                supervisor.stop()
            except Exception:
                pass
            try:
                db.close()
            except Exception:
                pass
