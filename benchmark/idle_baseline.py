"""benchmark.idle_baseline — Record PLUMA idle resource footprint.

Spec §23 performance targets:
  Resident idle GPU: 0% attributable ML workload.
  Resident idle CPU: near background noise.
  Resident idle RAM: keep small and regression-gated.

This script samples CPU, RAM, GPU (best-effort), and process count for
a configurable duration and writes a JSON report. No ML workers are started.
The report establishes the Phase 1 baseline against which later phases
must not regress.

Usage:
    python -m benchmark.idle_baseline [--duration <seconds>] [--output <path>]

Requires: psutil (in requirements-dev.txt). GPU sampling via optional
subprocess (nvidia-smi or wmic if available). Gracefully skips GPU if unavailable.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    print("WARNING: psutil not installed. Install requirements-dev.txt.", file=sys.stderr)


def _sample_cpu_ram() -> Dict[str, Any]:
    """Sample current process and system CPU/RAM."""
    if not _PSUTIL_AVAILABLE:
        return {"error": "psutil_not_installed"}

    proc = psutil.Process(os.getpid())
    return {
        "process_cpu_percent": proc.cpu_percent(interval=0.1),
        "process_ram_rss_mb": proc.memory_info().rss / (1024 * 1024),
        "system_cpu_percent": psutil.cpu_percent(interval=0.1),
        "system_ram_available_mb": psutil.virtual_memory().available / (1024 * 1024),
        "total_process_count": len(psutil.pids()),
    }


def _sample_gpu_utilization() -> Optional[float]:
    """Best-effort GPU sampling via nvidia-smi. Returns None if unavailable."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                return float(lines[0].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _verify_no_ml_loaded() -> List[str]:
    """Return list of any ML modules found in sys.modules (should be empty)."""
    ml_modules = {
        "whisper", "whisper_cpp", "llama_cpp", "llama", "paddle",
        "paddleocr", "onnxruntime", "torch", "tensorflow",
        "transformers", "sounddevice",
    }
    return sorted(ml_modules & set(sys.modules.keys()))


def run_baseline(duration_s: float = 600.0, sample_interval_s: float = 10.0) -> Dict[str, Any]:
    """Collect idle baseline samples over *duration_s* seconds.

    Returns a report dict suitable for JSON serialisation.
    """
    print(f"PLUMA idle baseline: sampling for {duration_s:.0f} s "
          f"(interval {sample_interval_s:.0f} s)...")

    # Verify no ML is loaded before sampling.
    ml_loaded = _verify_no_ml_loaded()
    if ml_loaded:
        print(f"WARNING: ML modules found in sys.modules: {ml_loaded!r}", file=sys.stderr)

    samples: List[Dict[str, Any]] = []
    start = time.monotonic()
    sample_count = 0

    while (time.monotonic() - start) < duration_s:
        sample = _sample_cpu_ram()
        gpu = _sample_gpu_utilization()
        if gpu is not None:
            sample["gpu_utilization_percent"] = gpu
        sample["elapsed_s"] = round(time.monotonic() - start, 1)
        sample["timestamp"] = datetime.now(timezone.utc).isoformat()
        samples.append(sample)
        sample_count += 1
        print(f"  [{sample_count:03d}] elapsed={sample['elapsed_s']:.1f}s "
              f"cpu={sample.get('process_cpu_percent', '?'):.1f}% "
              f"ram={sample.get('process_ram_rss_mb', '?'):.1f}MB "
              f"gpu={sample.get('gpu_utilization_percent', 'N/A')}")
        time.sleep(sample_interval_s)

    # Aggregate
    cpu_values = [s.get("process_cpu_percent", 0) for s in samples]
    ram_values = [s.get("process_ram_rss_mb", 0) for s in samples]
    gpu_values = [s.get("gpu_utilization_percent") for s in samples if "gpu_utilization_percent" in s]

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pluma_version": _get_pluma_version(),
        "duration_s": duration_s,
        "sample_count": len(samples),
        "ml_modules_loaded": ml_loaded,
        "ml_check_pass": len(ml_loaded) == 0,
        "cpu": {
            "p50_percent": _percentile(cpu_values, 50),
            "p95_percent": _percentile(cpu_values, 95),
            "max_percent": max(cpu_values) if cpu_values else None,
        },
        "ram_mb": {
            "p50": _percentile(ram_values, 50),
            "p95": _percentile(ram_values, 95),
            "max": max(ram_values) if ram_values else None,
        },
        "gpu": {
            "p95_percent": _percentile(gpu_values, 95) if gpu_values else None,
            "available": len(gpu_values) > 0,
        },
        "samples": samples,
    }

    # Gate checks (spec performance targets)
    report["gate_checks"] = {
        "no_ml_loaded": report["ml_check_pass"],
        "gpu_idle": (report["gpu"]["p95_percent"] == 0.0) if report["gpu"]["available"] else True,
        "cpu_low": (report["cpu"]["p95_percent"] < 5.0),  # Near background noise target.
    }
    all_gates = all(report["gate_checks"].values())
    report["all_gates_pass"] = all_gates
    print(f"\nGate checks: {report['gate_checks']}")
    print(f"Overall: {'PASS' if all_gates else 'FAIL'}")
    return report


def _percentile(values: List[float], p: int) -> Optional[float]:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = max(0, int(len(sorted_vals) * p / 100) - 1)
    return round(sorted_vals[idx], 2)


def _get_pluma_version() -> str:
    try:
        from pluma import __version__
        return __version__
    except ImportError:
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="PLUMA idle baseline measurement")
    parser.add_argument("--duration", type=float, default=600.0,
                        help="Sampling duration in seconds (default: 600)")
    parser.add_argument("--interval", type=float, default=10.0,
                        help="Sample interval in seconds (default: 10)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON file path (default: prints to stdout)")
    args = parser.parse_args()

    report = run_baseline(duration_s=args.duration, sample_interval_s=args.interval)

    json_output = json.dumps(report, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_output, encoding="utf-8")
        print(f"\nReport written to: {out_path}")
    else:
        print("\n--- Report ---")
        print(json_output)

    sys.exit(0 if report["all_gates_pass"] else 1)


if __name__ == "__main__":
    main()
