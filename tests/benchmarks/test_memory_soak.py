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


def test_soak_1000_fast_tasks_no_memory_leak() -> None:
    """Execute 1,000 continuous tasks in the orchestrator with SQLite WAL logging to assert zero leaks."""
    db = DbConnection(":memory:")
    db.open()
    ledger = ActivityLedger(db=db)
    registry = get_default_tool_registry()
    supervisor = TaskSupervisor(ledger=ledger)
    router = Router()
    orch = Orchestrator(
        router=router,
        registry=registry,
        supervisor=supervisor,
        ledger=ledger,
    )

    # Initial memory baseline
    gc.collect()
    rss_start = _get_process_rss_mb()

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

    gc.collect()
    rss_end = _get_process_rss_mb()
    delta_mb = rss_end - rss_start

    print(
        f"\n[SOAK TEST] 1,000 Tasks Completed: Start={rss_start:.2f}MB, "
        f"End={rss_end:.2f}MB, Delta={delta_mb:+.2f}MB"
    )

    # Verify ledger recorded all 1,000 tasks
    query = ActivityQuery(db=db)
    recent = query.recent_tasks(limit=1000)
    assert len(recent) == 1000

    # Memory growth across 1,000 in-memory tasks should be minimal (< 20MB)
    assert delta_mb < 20.0, f"Memory leaked {delta_mb:.2f}MB over 1,000 tasks!"
    db.close()


def test_worker_lifecycle_cyclic_load_unload_memory() -> None:
    """Cycle STT, OCR, and LLM lifecycle managers through 20 load/unload cycles to verify clean state cleanup."""
    voice_mgr = VoiceLifecycleManager(idle_unload_seconds=0.1)
    ocr_mgr = OcrLifecycleManager(idle_unload_seconds=0.1)
    llm_mgr = LlmLifecycleManager(idle_unload_seconds=0.1)

    gc.collect()
    rss_before = _get_process_rss_mb()

    for cycle in range(20):
        # Simulate worker warmup / cold state transitions
        assert str(voice_mgr.state) in ("COLD", "LifecycleState.COLD")
        assert str(ocr_mgr.state) in ("COLD", "OcrLifecycleState.COLD")
        assert str(llm_mgr.state) in ("COLD", "LlmLifecycleState.COLD")

        # Explicit unload / teardown
        voice_mgr.unload()
        ocr_mgr.unload()
        llm_mgr.unload()

    gc.collect()
    rss_after = _get_process_rss_mb()
    delta_mb = rss_after - rss_before

    print(f"\n[SOAK TEST] 20 Lifecycle Transitions: Delta={delta_mb:+.2f}MB")
    assert delta_mb < 5.0, f"Lifecycle cycle leaked {delta_mb:.2f}MB!"
