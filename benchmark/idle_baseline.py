"""Measure an explicitly selected PLUMA process tree without claiming a pass.

The sampler process is not the PLUMA resident. Supply the installed resident's
PID (and preferably its creation time) to collect target CPU and RAM. This
script cannot inspect another process's Python modules or attribute global GPU
utilization to that process, so those gates remain unverified here.

Usage:
    python -m benchmark.idle_baseline --pid <resident-pid> \
        --install-root <PLUMA-install-dir> --duration 600
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
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
    print("WARNING: psutil is not installed.", file=sys.stderr)


def _target_processes(
    target_pid: Optional[int],
    expected_creation_time: Optional[float],
    installation_root: Optional[Path],
) -> tuple[list[Any], Optional[float], Optional[str]]:
    if not _PSUTIL_AVAILABLE:
        return [], None, "psutil_not_installed"
    if target_pid is None:
        return [], None, "target_pid_required"
    if installation_root is None:
        return [], None, "installation_root_required"

    try:
        root = psutil.Process(target_pid)
        actual_creation_time = root.create_time()
        if expected_creation_time is not None and abs(actual_creation_time - expected_creation_time) > 0.01:
            return [], actual_creation_time, "target_pid_creation_time_mismatch"
        root_executable = Path(root.exe()).resolve()
        canonical_installation = installation_root.resolve()
        try:
            root_executable.relative_to(canonical_installation)
        except ValueError:
            return [], actual_creation_time, "target_executable_outside_installation"
        processes = [root, *root.children(recursive=True)]
        unique = {process.pid: process for process in processes}
        return list(unique.values()), actual_creation_time, None
    except psutil.NoSuchProcess:
        return [], None, "target_process_absent"
    except psutil.AccessDenied:
        return [], None, "target_process_access_denied"


def _sample_cpu_ram(
    target_pid: Optional[int] = None,
    expected_creation_time: Optional[float] = None,
    installation_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Sample the selected resident and its current descendants by PID identity."""
    if not _PSUTIL_AVAILABLE:
        return {"target_error": "psutil_not_installed"}

    sample: Dict[str, Any] = {
        "system_cpu_percent": psutil.cpu_percent(interval=None),
        "system_ram_available_mb": psutil.virtual_memory().available / (1024 * 1024),
        "total_system_process_count": len(psutil.pids()),
    }
    processes, actual_creation_time, error = _target_processes(
        target_pid, expected_creation_time, installation_root
    )
    sample["target_pid"] = target_pid
    sample["target_creation_time"] = actual_creation_time
    sample["target_error"] = error
    if error is not None:
        sample.update(
            {
                "target_cpu_percent": None,
                "target_ram_rss_mb": None,
                "target_process_count": 0,
                "target_processes": [],
                "target_identity_stable": False,
                "target_process_tree_complete": False,
            }
        )
        return sample

    cpu_seconds_total = 0.0
    rss_bytes = 0
    identities: list[Dict[str, Any]] = []
    snapshot_complete = True
    for process in processes:
        try:
            creation_time = process.create_time()
            cpu_times = process.cpu_times()
            cpu_seconds = cpu_times.user + cpu_times.system
            cpu_seconds_total += cpu_seconds
            rss_bytes += process.memory_info().rss
            identities.append(
                {
                    "pid": process.pid,
                    "creation_time": creation_time,
                    "name": process.name(),
                    "executable": process.exe(),
                    "cpu_time_seconds": cpu_seconds,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # A descendant can exit during the snapshot. The root is checked again below.
            snapshot_complete = False
            continue

    try:
        current_root = psutil.Process(target_pid)
        current_creation_time = current_root.create_time()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        current_creation_time = None
    identity_stable = (
        current_creation_time is not None
        and actual_creation_time is not None
        and any(item["pid"] == target_pid for item in identities)
        and abs(current_creation_time - actual_creation_time) <= 0.01
    )
    sample.update(
        {
            "target_identity_stable": identity_stable,
            "target_process_tree_complete": identity_stable and snapshot_complete,
            "target_cpu_seconds_total": round(cpu_seconds_total, 6) if identity_stable else None,
            "target_ram_rss_mb": round(rss_bytes / (1024 * 1024), 3) if identity_stable else None,
            "target_process_count": len(identities) if identity_stable else 0,
            "target_processes": identities if identity_stable else [],
        }
    )
    if not identity_stable:
        sample["target_error"] = "target_process_identity_changed_or_exited"
    return sample


def _sample_gpu_utilization() -> Optional[float]:
    """Read global GPU utilization when available; this is not per-process proof."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().splitlines()
            if lines:
                return float(lines[0].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def _percentile(values: List[float], percentile: int) -> Optional[float]:
    if not values:
        return None
    sorted_values = sorted(values)
    index = max(0, int(len(sorted_values) * percentile / 100) - 1)
    return round(sorted_values[index], 2)


def run_baseline(
    duration_s: float = 600.0,
    sample_interval_s: float = 10.0,
    target_pid: Optional[int] = None,
    target_creation_time: Optional[float] = None,
    installation_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Collect measurements; missing target/GPU evidence is never a passing gate."""
    if not math.isfinite(duration_s) or not math.isfinite(sample_interval_s) or duration_s <= 0 or sample_interval_s <= 0:
        raise ValueError("duration and sample interval must be positive")
    if target_pid is not None and target_pid <= 0:
        raise ValueError("target PID must be positive")
    if target_creation_time is not None and (
        not math.isfinite(target_creation_time) or target_creation_time <= 0
    ):
        raise ValueError("target creation time must be a finite positive timestamp")
    if target_pid is None or installation_root is None:
        raise ValueError("an installed PLUMA resident PID and --install-root are required")
    if not _PSUTIL_AVAILABLE:
        raise RuntimeError("psutil is required to measure an installed PLUMA process tree")

    print(
        f"PLUMA resident baseline: target PID={target_pid}, install={installation_root}, "
        f"duration={duration_s:.0f}s, "
        f"interval={sample_interval_s:.0f}s"
    )
    _, captured_creation_time, identity_error = _target_processes(
        target_pid, target_creation_time, installation_root
    )
    if identity_error is not None:
        raise RuntimeError(f"Selected process is not a verified installed PLUMA resident: {identity_error}")
    if target_creation_time is None:
        target_creation_time = captured_creation_time

    samples: List[Dict[str, Any]] = []
    start = time.monotonic()
    sample_count = 0
    previous_cpu_times: Dict[tuple[int, float], float] = {}
    previous_sample_time: Optional[float] = None

    psutil.cpu_percent(interval=None) if _PSUTIL_AVAILABLE else None

    while (time.monotonic() - start) < duration_s:
        sample = _sample_cpu_ram(target_pid, target_creation_time, installation_root)
        sample_time = time.monotonic()
        cpu_records = sample.get("target_processes", [])
        current_cpu_times = {
            (item["pid"], item["creation_time"]): item["cpu_time_seconds"]
            for item in cpu_records
            if item.get("cpu_time_seconds") is not None
        }
        interval_complete = (
            sample.get("target_process_tree_complete") is True
            and previous_sample_time is not None
            and set(current_cpu_times) == set(previous_cpu_times)
        )
        if interval_complete:
            delta = sum(
                max(0.0, cpu_seconds - previous_cpu_times[identity])
                for identity, cpu_seconds in current_cpu_times.items()
            )
            elapsed = max(sample_time - previous_sample_time, 1e-6)
            sample["target_cpu_percent"] = round(delta / elapsed * 100.0, 3)
        else:
            sample["target_cpu_percent"] = None
        sample["target_cpu_interval_complete"] = interval_complete
        previous_cpu_times = current_cpu_times
        previous_sample_time = sample_time
        gpu = _sample_gpu_utilization()
        sample["global_gpu_utilization_percent"] = gpu
        sample["gpu_target_attribution"] = "unavailable"
        sample["elapsed_s"] = round(time.monotonic() - start, 1)
        sample["timestamp"] = datetime.now(timezone.utc).isoformat()
        samples.append(sample)
        sample_count += 1
        cpu = sample.get("target_cpu_percent")
        ram = sample.get("target_ram_rss_mb")
        print(
            f"  [{sample_count:03d}] elapsed={sample['elapsed_s']:.1f}s "
            f"target_cpu={cpu if cpu is not None else 'UNVERIFIED'} "
            f"target_ram_mb={ram if ram is not None else 'UNVERIFIED'} "
            f"gpu_attribution=UNVERIFIED"
        )
        remaining = duration_s - (time.monotonic() - start)
        if remaining > 0:
            time.sleep(min(sample_interval_s, remaining))

    cpu_values = [sample["target_cpu_percent"] for sample in samples if sample.get("target_cpu_percent") is not None]
    ram_values = [sample["target_ram_rss_mb"] for sample in samples if sample.get("target_ram_rss_mb") is not None]
    target_identity_pass = bool(samples) and all(
        sample.get("target_identity_stable") is True for sample in samples
    )
    target_tree_complete = bool(samples) and all(
        sample.get("target_process_tree_complete") is True for sample in samples
    )
    cpu_interval_samples = samples[1:]
    cpu_intervals_complete = bool(cpu_interval_samples) and all(
        sample.get("target_cpu_interval_complete") is True for sample in cpu_interval_samples
    )
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pluma_version": _get_pluma_version(),
        "duration_s": duration_s,
        "sample_count": len(samples),
        "target": {
            "pid": target_pid,
            "installation_root": str(installation_root.resolve()),
            "creation_time_bound": target_creation_time,
            "identity_verified_every_sample": target_identity_pass,
            "process_tree_complete_every_sample": target_tree_complete,
            "includes_current_descendants": True,
        },
        "cpu": {
            "target_process_tree_p50_percent": _percentile(cpu_values, 50),
            "target_process_tree_p95_percent": _percentile(cpu_values, 95),
            "target_process_tree_max_percent": max(cpu_values) if cpu_values else None,
        },
        "ram_mb": {
            "target_process_tree_p50": _percentile(ram_values, 50),
            "target_process_tree_p95": _percentile(ram_values, 95),
            "target_process_tree_max": max(ram_values) if ram_values else None,
        },
        "gpu": {
            "global_telemetry_available": any(
                sample.get("global_gpu_utilization_percent") is not None for sample in samples
            ),
            "target_attribution_available": False,
            "target_idle": None,
        },
        "remote_ml_module_inspection": "unavailable",
        "samples": samples,
    }
    report["gate_checks"] = {
        "target_identity_stable": target_identity_pass,
        "target_process_tree_complete": target_tree_complete,
        "target_cpu_low": (
            report["cpu"]["target_process_tree_p95_percent"] < 5.0
            if report["cpu"]["target_process_tree_p95_percent"] is not None and cpu_intervals_complete
            else None
        ),
        "target_cpu_intervals_complete": cpu_intervals_complete,
        "target_gpu_idle": None,
        "resident_ml_unloaded": None,
    }
    report["all_gates_pass"] = all(value is True for value in report["gate_checks"].values())
    print(f"\nGate checks: {report['gate_checks']}")
    print(f"Overall: {'PASS' if report['all_gates_pass'] else 'INCOMPLETE'}")
    return report


def _get_pluma_version() -> str:
    try:
        return importlib.metadata.version("pluma")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _report_path(requested: Optional[str]) -> Path:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parents[1] / candidate
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        candidate = Path(__file__).resolve().parents[1] / "output" / f"idle-baseline-{stamp}.json"
    candidate = candidate.resolve()
    repository_root = Path(__file__).resolve().parents[1]
    try:
        candidate.relative_to(repository_root)
    except ValueError as exc:
        raise ValueError("Benchmark output must stay inside the PLUMA checkout.") from exc
    if candidate == repository_root or candidate.exists():
        raise FileExistsError(f"Refusing to overwrite benchmark output: {candidate}")
    return candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure an installed PLUMA process tree")
    parser.add_argument("--pid", type=int, default=None, help="installed PLUMA resident PID")
    parser.add_argument("--install-root", type=Path, default=None, help="canonical PLUMA installation root")
    parser.add_argument(
        "--creation-time",
        type=float,
        default=None,
        help="psutil creation timestamp for the PID; use to reject PID reuse",
    )
    parser.add_argument("--duration", type=float, default=600.0, help="duration in seconds")
    parser.add_argument("--interval", type=float, default=10.0, help="sample interval in seconds")
    parser.add_argument("--output", type=str, default=None, help="output JSON path")
    args = parser.parse_args()

    report = run_baseline(
        duration_s=args.duration,
        sample_interval_s=args.interval,
        target_pid=args.pid,
        target_creation_time=args.creation_time,
        installation_root=args.install_root,
    )
    json_output = json.dumps(report, indent=2)
    out_path = _report_path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json_output, encoding="utf-8")
    print(f"\nReport written to: {out_path}")

    sys.exit(0 if report["all_gates_pass"] else 1)


if __name__ == "__main__":
    main()
