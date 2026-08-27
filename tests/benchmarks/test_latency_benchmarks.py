"""tests/benchmarks/test_latency_benchmarks.py — Latency benchmarks for PLUMA routes and subsystems.

Spec §3, §22, §23:
- FAST route commands MUST complete in <50ms median.
- Router classification must be sub-millisecond (<1ms).
- VAD audio buffer energy calculation must be sub-5ms.
"""

from __future__ import annotations

import statistics
import time
from typing import List
import pytest

from pluma.core.orchestrator import Orchestrator
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import Router
from pluma.core.task_supervisor import TaskSupervisor
from pluma.memory.activity import ActivityLedger
from pluma.memory.db import DbConnection
from pluma.tools.registry import get_default_tool_registry
from pluma.voice.vad import EnergyVAD


@pytest.fixture
def benchmark_orchestrator():
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
    yield orch
    db.close()


def test_fast_route_latency_under_50ms(benchmark_orchestrator: Orchestrator) -> None:
    """Benchmark end-to-end latency for FAST route commands (Spec §3 Law 1: <50ms median)."""
    commands = [
        "mute",
        "unmute",
        "set volume 50",
        "system status",
        "clear clipboard",
    ]

    # Warmup
    for cmd in commands:
        benchmark_orchestrator.execute(PlumaRequest(input_mode=InputMode.TEXT, text=cmd))

    latencies_ms: List[float] = []
    iterations = 20  # 20 * 5 = 100 executions

    for _ in range(iterations):
        for cmd in commands:
            req = PlumaRequest(input_mode=InputMode.TEXT, text=cmd)
            t0 = time.perf_counter()
            res = benchmark_orchestrator.execute(req)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert res.final_state == "SUCCEEDED"
            latencies_ms.append(elapsed_ms)

    median_latency = statistics.median(latencies_ms)
    p95_latency = statistics.quantiles(latencies_ms, n=20)[18]  # 95th percentile
    min_latency = min(latencies_ms)
    max_latency = max(latencies_ms)

    print(
        f"\n[BENCHMARK] FAST Route Latency ({len(latencies_ms)} runs): "
        f"Median={median_latency:.2f}ms, P95={p95_latency:.2f}ms, "
        f"Min={min_latency:.2f}ms, Max={max_latency:.2f}ms"
    )

    # Spec §3 requirement: < 50ms median
    assert median_latency < 50.0, f"Median latency {median_latency:.2f}ms exceeded 50ms threshold!"


def test_router_classification_latency_sub_millisecond() -> None:
    """Benchmark Router regex classification speed (Target: < 1.0ms median)."""
    router = Router()
    test_commands = [
        "mute",
        "unmute",
        "set volume to 60%",
        "get system status",
        "clear clipboard",
        "open notepad",
        "focus chrome",
        "find all pdf files in downloads",
    ]

    latencies_ms: List[float] = []
    iterations = 100

    for _ in range(iterations):
        for cmd in test_commands:
            req = PlumaRequest(input_mode=InputMode.TEXT, text=cmd)
            t0 = time.perf_counter()
            res = router.route(req)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            assert res.route is not None
            latencies_ms.append(elapsed_ms)

    median_latency = statistics.median(latencies_ms)
    print(f"\n[BENCHMARK] Router Classification Latency: Median={median_latency:.4f}ms")
    assert median_latency < 1.0, f"Router median latency {median_latency:.4f}ms exceeded 1ms threshold!"


def test_vad_audio_processing_latency() -> None:
    """Benchmark Voice Activity Detection RMS energy calculation latency (Target: < 5.0ms)."""
    vad = EnergyVAD(energy_threshold=350.0, frame_duration_ms=30)

    # 1 second of mock 16kHz 16-bit PCM audio (32,000 bytes)
    sample_audio = bytes([0x10, 0x00] * 16000)

    latencies_ms: List[float] = []
    for _ in range(200):
        t0 = time.perf_counter()
        _ = vad.is_speech_present(sample_audio)
        _ = vad.trim_silence(sample_audio)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(elapsed_ms)

    median_latency = statistics.median(latencies_ms)
    print(f"\n[BENCHMARK] VAD Processing Latency: Median={median_latency:.4f}ms")
    assert median_latency < 5.0, f"VAD median latency {median_latency:.4f}ms exceeded 5ms threshold!"
