"""Opt-in P13 acceptance against an actual local llama.cpp GGUF runtime.

Run from the repository root with the isolated llama-cpp-python environment:
  output/p13-native-env/Scripts/python.exe tests/windows/p13_native_runtime_acceptance.py \
      --model output/p13-native/model/Qwen3-4B-Q4_K_M.gguf --cycles 50

All files and SQLite state are created under ignored output/p13-native. Planner
actions read only the script's own fixture directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time

import psutil

from pluma.app import PlumaApplicationRuntime
from pluma.config.loader import load_config
from pluma.config.paths import PlumaPaths
from pluma.core.cancellation import StopReason
from pluma.core.request import InputMode, PlumaRequest
from pluma.core.router import RouteMode
from pluma.core.task_supervisor import TaskState
from pluma.memory.activity import ActivityQuery


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _runtime(model_path: Path, root: Path) -> PlumaApplicationRuntime:
    # Isolate acceptance from the developer's %APPDATA% user settings.
    config = load_config(user_config_path=root / "acceptance-user-settings.json")
    config["brain"]["model_path"] = str(model_path)
    config["agent"]["max_plan_steps"] = 8
    config["runtime"]["model_idle_unload_seconds"] = 30
    config["voice"]["required"] = False
    paths = PlumaPaths(
        local_app_data=str(root / "local"),
        roaming_app_data=str(root / "roaming"),
    )
    return PlumaApplicationRuntime(paths=paths, config=config)


def _planner_task(
    runtime: PlumaApplicationRuntime,
    directory: Path,
    label: str,
    *,
    secret_context: bool = False,
) -> str:
    secret_marker = "sk-pluma-p13-context-fixture-7d31f0"
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=f"List the files in this exact directory: {directory}",
        active_window_title=(f"Settings api_key={secret_marker}" if secret_context else None),
    )
    result = runtime.orchestrator.execute(request)
    _assert(result.route == RouteMode.SMART, f"{label}: expected SMART, got {result.route}.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"{label} ({result.task_id}): real planner/task failed: "
            f"{result.error or result.factual_summary}; cleanup={result.cleanup_evidence}")
    _assert(len(result.steps) == 1, f"{label}: expected one read-only list_files action.")
    _assert(result.steps[0].tool in {"list_files", "list_folder"},
            f"{label}: unexpected non-read-only file tool {result.steps[0].tool!r}.")
    _assert(runtime.llm_lifecycle.state.value == "COLD", f"{label}: native planner was not cold after task.")
    _assert(runtime.llm_lifecycle.adapter.is_loaded is False,
            f"{label}: parent process retained native model weights.")
    _assert("llama_cpp" not in __import__("sys").modules,
            f"{label}: llama_cpp was imported into the resident process.")

    task = ActivityQuery(runtime.db).task_by_id(result.task_id)
    _assert(task is not None and task["final_state"] == "SUCCEEDED",
            f"{label}: successful task was not read back from SQLite.")
    actions = ActivityQuery(runtime.db).actions_for_task(result.task_id)
    _assert(len(actions) == 1 and actions[0]["tool"] in {"list_files", "list_folder"},
            f"{label}: action history did not read back the registered tool.")
    stored_history = json.dumps({"task": task, "actions": actions}, default=str).lower()
    _assert(not any(marker in stored_history for marker in (
        "chain_of_thought", "hidden_reasoning", "planner_reasoning", "raw_model_output",
    )), f"{label}: planner reasoning/raw output was persisted in activity history.")
    if secret_context:
        _assert(secret_marker not in stored_history,
                f"{label}: sensitive active-window context reached persisted history.")
    action_args = json.loads(actions[0]["args_json_sanitized"])["args"]
    _assert(Path(action_args["path"]).resolve() == directory.resolve(),
            f"{label}: planner selected a different path than its task fixture.")
    evidence = result.cleanup_evidence
    _assert(any(item.get("code") == "WORKER_ABSENCE_VERIFIED" for item in evidence),
            f"{label}: task-owned planner worker absence was not verified.")
    _assert(result.completion_verified and result.terminal_persisted is True,
            f"{label}: task terminal/history readback was incomplete.")
    return result.task_id


def _native_multistep_task(runtime: PlumaApplicationRuntime, directory: Path) -> dict:
    """Require a bounded native plan to complete both fixture-only observations."""
    fixture_file = directory / "fixture.txt"
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=("Use exactly two read-only registered file tools in this order: "
              f"first list_folder for {directory}, then file_info for {fixture_file}. "
              "Do not open or change anything."),
    )
    result = runtime.orchestrator.execute(request)
    _assert(result.route == RouteMode.SMART, "Native multi-step request did not use SMART planning.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"Native multi-step plan failed: {result.error or result.factual_summary}")
    tools = [step.tool for step in result.steps]
    max_steps = runtime.config.get("agent", {}).get("max_plan_steps", 8)
    _assert(2 <= len(result.steps) <= max_steps,
            f"Native multi-step plan exceeded its configured bound or was not multi-step: "
            f"{len(result.steps)} steps (maximum {max_steps}).")
    _assert(set(tools) == {"list_folder", "file_info"},
            f"Native model selected an unexpected or incomplete read-only tool set: {tools!r}.")
    _assert(all(step.result.ok for step in result.steps),
            "A native fixture-only observation failed or lacked a verified result.")
    history = ActivityQuery(runtime.db)
    task = history.task_by_id(result.task_id)
    actions = history.actions_for_task(result.task_id)
    _assert(task is not None and task["final_state"] == TaskState.SUCCEEDED.value,
            "Native multi-step task state was not read back from SQLite.")
    _assert([action["tool"] for action in actions] == tools,
            "Native multi-step action sequence was not read back from SQLite.")
    for action in actions:
        expected_path = directory if action["tool"] == "list_folder" else fixture_file
        actual_path = json.loads(action["args_json_sanitized"])["args"]["path"]
        _assert(Path(actual_path).resolve() == expected_path.resolve(),
                "Native multi-step SQLite readback escaped its owned fixture directory.")
    _assert(result.completion_verified and result.terminal_persisted is True,
            "Native multi-step completion/history readback was incomplete.")
    _assert(runtime.llm_lifecycle.state.value == "COLD",
            "Native multi-step task left the planner warm.")
    _assert(not runtime.tool_registry._worker_controllers,
            "Native multi-step task retained a worker controller.")
    return {"task_id": result.task_id, "tools": tools, "step_count": len(tools),
            "configured_step_limit": max_steps,
            "ledger_verified": True, "final_state": task["final_state"]}


def _native_failure_replan_task(runtime: PlumaApplicationRuntime, directory: Path) -> dict:
    """Exercise real model re-observation after a guaranteed read-only failure."""
    missing_file = directory / "absent-fixture-file.txt"
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=("The first registered read-only action must be file_info on this exact "
              f"nonexistent path: {missing_file}. After that action reports not found, "
              f"re-observe and recover by listing this existing directory: {directory}. "
              "Do not change files or use a shell."),
    )
    result = runtime.orchestrator.execute(request)
    _assert(result.route == RouteMode.SMART, "Native replan request did not use SMART planning.")
    _assert(result.final_state == TaskState.SUCCEEDED.value,
            f"Native failure/replan task did not recover: {result.error or result.factual_summary}")
    _assert(result.replan_count >= 1,
            "Native failure/replan task completed without a post-failure planner observation.")
    _assert(any(step.tool == "file_info" and not step.result.ok for step in result.steps),
            "Native plan did not record the expected read-only missing-file failure.")
    _assert(any(step.tool in {"list_folder", "list_files"} and step.result.ok
                for step in result.steps),
            "Native replan did not recover with a successful fixture directory read.")
    history = ActivityQuery(runtime.db)
    task = history.task_by_id(result.task_id)
    actions = history.actions_for_task(result.task_id)
    _assert(task is not None and task["final_state"] == TaskState.SUCCEEDED.value,
            "Native recovery terminal state was not read back from SQLite.")
    _assert(any(action["tool"] == "file_info" for action in actions)
            and any(action["tool"] in {"list_folder", "list_files"} for action in actions),
            "Native failure and recovery actions were not read back from SQLite.")
    _assert(result.completion_verified and result.terminal_persisted is True,
            "Native recovery completion/history readback was incomplete.")
    _assert(runtime.llm_lifecycle.state.value == "COLD",
            "Native recovery left the planner warm.")
    _assert(not runtime.tool_registry._worker_controllers,
            "Native recovery retained a worker controller.")
    return {"task_id": result.task_id, "replan_count": result.replan_count,
            "tools": [a["tool"] for a in actions], "ledger_verified": True,
            "final_state": task["final_state"]}


def _native_rejects_unregistered_tool(runtime: PlumaApplicationRuntime, directory: Path) -> dict:
    """Use native generation to propose a fixture-only name absent from the registry."""
    tool_name = "p13_unregistered_tool_fixture"
    adapter = runtime.llm_lifecycle.adapter
    original_resolver = adapter.get_permitted_tool_specs
    adapter.get_permitted_tool_specs = lambda _command, _route: [{
        "name": tool_name,
        "description": "Fixture tool returning a directory listing; it is not registered.",
        "args_schema": {"type": "object", "properties": {}, "required": []},
    }]
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=(f"Use the only permitted tool {tool_name} with an empty arguments object "
              f"to list this fixture directory: {directory}. Do not use a different tool."),
    )
    try:
        result = runtime.orchestrator.execute(request)
    finally:
        adapter.get_permitted_tool_specs = original_resolver
    _assert(result.route == RouteMode.SMART, "Unregistered-tool probe did not use SMART planning.")
    _assert(result.final_state == TaskState.FAILED.value,
            "Native planner's unregistered tool proposal was not rejected.")
    _assert("Unknown or unpermitted tool" in (result.error or ""),
            "Native planner failed for a reason other than registry rejection.")
    _assert(not result.steps, "An unregistered native planner call reached execution.")
    history = ActivityQuery(runtime.db)
    task = history.task_by_id(result.task_id)
    _assert(task is not None and task["final_state"] == TaskState.FAILED.value,
            "Unregistered-tool rejection terminal state was not read back from SQLite.")
    _assert(not history.actions_for_task(result.task_id),
            "Unregistered native planner call was recorded as an executed action.")
    _assert(any(item.get("code") == "WORKER_ABSENCE_VERIFIED"
                for item in result.cleanup_evidence),
            "Unregistered-tool rejection did not verify worker absence.")
    _assert(runtime.llm_lifecycle.state.value == "COLD"
            and runtime.llm_lifecycle.adapter.is_loaded is False,
            "Rejected native plan left the resident planner warm.")
    return {"task_id": result.task_id, "proposed_tool": tool_name,
            "rejected_before_execution": True, "ledger_verified": True,
            "final_state": task["final_state"]}


def _interrupt_loaded_native_worker(
    runtime: PlumaApplicationRuntime,
    directory: Path,
    *,
    timeout: bool = False,
    crash: bool = False,
) -> dict:
    request = PlumaRequest(
        input_mode=InputMode.TEXT,
        text=(f"List files in this exact directory and carefully report every result: {directory}. "
              "Do not change files or settings."),
    )
    capsule = runtime.supervisor.create_task_capsule(request_id=request.request_id)
    result_box: dict = {}

    def execute() -> None:
        try:
            result_box["result"] = runtime.orchestrator.execute(request, capsule=capsule)
        except BaseException as exc:  # Captured in the acceptance harness, not production history.
            result_box["error"] = type(exc).__name__

    thread = threading.Thread(target=execute, name="p13-native-stop-fixture", daemon=True)
    thread.start()
    deadline = time.monotonic() + 120
    worker_pid = None
    loaded_rss = 1_500 * 1024 * 1024
    loaded_rss_observed = 0
    loaded_cpu_delta = 0.0
    while time.monotonic() < deadline:
        controller = capsule.worker_controller
        process = getattr(controller, "_proc", None) if controller is not None else None
        if process is not None and process.pid is not None:
            worker_pid = process.pid
            if psutil.pid_exists(worker_pid):
                try:
                    observed = psutil.Process(worker_pid)
                    if observed.memory_info().rss >= loaded_rss:
                        cpu_before = observed.cpu_times().user + observed.cpu_times().system
                        time.sleep(0.2)
                        cpu_after = observed.cpu_times().user + observed.cpu_times().system
                        if psutil.pid_exists(worker_pid) and cpu_after > cpu_before:
                            loaded_rss_observed = observed.memory_info().rss
                            loaded_cpu_delta = cpu_after - cpu_before
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        if not thread.is_alive():
            raise AssertionError("Native model returned before the loaded-worker STOP checkpoint.")
        time.sleep(0.05)
    else:
        raise AssertionError("Actual llama.cpp worker did not reach the loaded-memory checkpoint.")

    stop_reply = None
    if crash:
        # Kill only the child created and owned by this task. This is a
        # deliberate transport-crash injection, not a user-process operation.
        controller = capsule.worker_controller
        process = getattr(controller, "_proc", None) if controller is not None else None
        _assert(process is not None and process.pid == worker_pid,
                "Crash injection could not identify the task-owned model worker.")
        process.terminate()
    elif timeout:
        capsule.cancellation_token.cancel(StopReason.TASK_TIMEOUT)
    else:
        stop_reply = runtime.supervisor.request_stop(capsule.task_id, wait_s=1.0)
    thread.join(timeout=30)
    _assert(not thread.is_alive(), "STOP did not release the native planner request thread.")
    _assert("error" not in result_box, f"Orchestrator failed during native STOP: {result_box.get('error')}")
    expected_reason = (StopReason.INTERNAL_ERROR if crash else
                       StopReason.TASK_TIMEOUT if timeout else StopReason.USER_STOP)
    expected_state = TaskState.FAILED if (timeout or crash) else TaskState.STOPPED
    _assert(capsule.cancellation_token.reason == expected_reason,
            f"Native cancellation/crash did not preserve {getattr(expected_reason, 'value', 'no cancellation')}.")
    _assert(capsule.terminal_ready.is_set(), "STOP terminal outcome was not finalized.")
    _assert(capsule.state == expected_state,
            f"Native cancellation ended in {capsule.state.value}, expected {expected_state.value}.")
    _assert(capsule.worker_controller is None, "Task capsule retained the native worker controller.")
    _assert(worker_pid is not None and not psutil.pid_exists(worker_pid),
            "Native llama.cpp worker process remains after STOP.")
    _assert(any(item.code == "WORKER_ABSENCE_VERIFIED" for item in capsule.cleanup_evidence),
            "STOP cleanup evidence did not verify worker absence.")
    if stop_reply is not None:
        _assert(stop_reply.tasks and stop_reply.tasks[0].latch_acknowledged,
                "STOP did not acknowledge its latched task.")

    history = ActivityQuery(runtime.db)
    task_row = history.task_by_id(capsule.task_id)
    report = history.cleanup_report_for_task(capsule.task_id)
    _assert(task_row is not None and task_row["final_state"] == expected_state.value,
            "Native cancellation final state was not read back from SQLite.")
    if expected_state == TaskState.FAILED:
        _assert(bool(task_row.get("error_code")),
                "Native timeout/crash failure code was not read back from SQLite.")
    _assert(not history.actions_for_task(capsule.task_id),
            "A tool action was admitted before native planning completed.")
    _assert(report is not None and "WORKER_ABSENCE_VERIFIED" in report.get("metadata_json", ""),
            "SQLite cleanup report did not record native worker absence.")
    _assert("llama_cpp" not in __import__("sys").modules,
            "Native llama.cpp runtime loaded in the resident process.")
    return {
        "task_id": capsule.task_id,
        "worker_pid": worker_pid,
        "loaded_rss_bytes": loaded_rss_observed,
        "loaded_cpu_delta_seconds": loaded_cpu_delta,
        "cancellation_reason": expected_reason.value if expected_reason is not None else None,
        "final_state": expected_state.value,
        "ledger_error_code": task_row.get("error_code"),
        "injected_worker_crash": crash,
        "cleanup_verified": True,
        "ledger_verified": True,
    }


def _measure_cold_idle(
    runtime: PlumaApplicationRuntime,
    duration_s: float,
    report_path: Path,
    report: dict,
) -> dict:
    """Measure the constructed runtime graph without starting resident hooks."""
    _assert(duration_s >= 600, "The P13 idle baseline must run for at least ten minutes.")
    _assert(runtime.llm_lifecycle.state.value == "COLD", "Idle baseline began with a warm planner.")
    _assert(runtime.llm_lifecycle.adapter.is_loaded is False,
            "Idle baseline began with planner weights loaded in the resident process.")
    _assert("llama_cpp" not in __import__("sys").modules,
            "Idle baseline imported llama_cpp into the resident process.")
    _assert(runtime.config.get("agent", {}).get("continuous_screen_polling") is False,
            "Idle baseline requires continuous screen polling to be disabled.")

    process = psutil.Process(os.getpid())
    cpu_before = process.cpu_times()
    rss_before = process.memory_info().rss
    handles_before = process.num_handles() if hasattr(process, "num_handles") else None
    children_before = len(process.children(recursive=True))
    thread_names_before = sorted(thread.name for thread in threading.enumerate())
    _assert(not any("screen" in name.lower() or "capture" in name.lower()
                    for name in thread_names_before),
            "A screen/capture loop thread was active at idle baseline start.")
    samples = []

    def sample_gpu() -> dict:
        """Record global utilization and whether this PID owns a compute context."""
        sample = {
            "system_utilization_percent": None,
            "system_memory_used_bytes": None,
            "current_pid_in_compute_apps": None,
            "available": False,
        }
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            first_line = result.stdout.strip().splitlines()[0]
            utilization, memory_mib = (part.strip() for part in first_line.split(",", 1))
            sample["system_utilization_percent"] = float(utilization)
            sample["system_memory_used_bytes"] = int(float(memory_mib) * 1024 * 1024)
            sample["available"] = True
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            return sample
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5, check=True,
            )
            pids = {int(line.strip()) for line in result.stdout.splitlines()
                    if line.strip().isdigit()}
            sample["current_pid_in_compute_apps"] = os.getpid() in pids
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        return sample

    started = time.monotonic()
    previous_elapsed = 0.0
    previous_cpu = cpu_before.user + cpu_before.system
    while time.monotonic() - started < duration_s:
        time.sleep(min(10.0, max(0.0, duration_s - (time.monotonic() - started))))
        _assert(runtime.llm_lifecycle.state.value == "COLD",
                "Planner lifecycle left COLD during idle measurement.")
        _assert(runtime.llm_lifecycle.adapter.is_loaded is False,
                "Planner model became resident during idle measurement.")
        _assert("llama_cpp" not in __import__("sys").modules,
                "llama_cpp became imported into the idle resident process.")
        _assert(not process.children(recursive=True),
                "An idle ML/worker child process appeared during measurement.")
        elapsed = time.monotonic() - started
        cpu_times = process.cpu_times()
        cpu_total = cpu_times.user + cpu_times.system
        sample = {
            "elapsed_s": round(elapsed, 1),
            "process_cpu_percent": round(
                (cpu_total - previous_cpu) / max(0.001, elapsed - previous_elapsed) * 100,
                2,
            ),
            "rss_bytes": process.memory_info().rss,
            "handles": process.num_handles() if hasattr(process, "num_handles") else None,
            "threads": len(threading.enumerate()),
            "gpu": sample_gpu(),
        }
        previous_elapsed = elapsed
        previous_cpu = cpu_total
        samples.append(sample)
        report["idle_baseline"] = {
            "status": "RUNNING",
            "requested_seconds": duration_s,
            "sample_count": len(samples),
            "samples": samples,
        }
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"P13 cold idle sample {len(samples)} passed at {sample['elapsed_s']:.0f}s.", flush=True)

    cpu_after = process.cpu_times()
    rss_after = process.memory_info().rss
    handles_after = process.num_handles() if hasattr(process, "num_handles") else None
    children_after = len(process.children(recursive=True))
    thread_names_after = sorted(thread.name for thread in threading.enumerate())
    compute_pid_samples = [sample["gpu"]["current_pid_in_compute_apps"]
                           for sample in samples
                           if sample["gpu"]["current_pid_in_compute_apps"] is not None]
    _assert(not any("screen" in name.lower() or "capture" in name.lower()
                    for name in thread_names_after),
            "A screen/capture loop thread appeared during idle measurement.")
    return {
        "measured_seconds": round(time.monotonic() - started, 1),
        "sample_count": len(samples),
        "process_cpu_percent_max": max((sample["process_cpu_percent"] for sample in samples), default=0),
        "process_cpu_percent_p95": sorted(
            sample["process_cpu_percent"] for sample in samples
        )[max(0, int(len(samples) * 0.95) - 1)] if samples else 0,
        "process_cpu_seconds": round(
            cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system, 3
        ),
        "rss_delta_bytes": rss_after - rss_before,
        "handle_delta": handles_after - handles_before
        if handles_after is not None and handles_before is not None else None,
        "children_before": children_before,
        "children_after": children_after,
        "thread_names_before": thread_names_before,
        "thread_names_after": thread_names_after,
        "gpu_sample_count": sum(bool(sample["gpu"]["available"]) for sample in samples),
        "system_gpu_utilization_percent_max": max(
            (sample["gpu"]["system_utilization_percent"] for sample in samples
             if sample["gpu"]["system_utilization_percent"] is not None), default=None
        ),
        "system_gpu_memory_used_bytes_max": max(
            (sample["gpu"]["system_memory_used_bytes"] for sample in samples
             if sample["gpu"]["system_memory_used_bytes"] is not None), default=None
        ),
        "compute_pid_sample_count": len(compute_pid_samples),
        "current_pid_in_compute_apps": any(compute_pid_samples) if compute_pid_samples else None,
        "samples": samples,
        "continuous_screen_polling": False,
        "screen_capture_loop_thread": False,
        "llama_cpp_imported": False,
        "model_cold_for_entire_interval": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=50)
    parser.add_argument("--skip-stop", action="store_true")
    parser.add_argument("--unregistered-tool-only", action="store_true",
                        help="Run only the native-model unregistered-tool rejection scenario.")
    parser.add_argument("--idle-seconds", type=int, default=0,
                        help="Also measure a cold idle interval (minimum 600 seconds).")
    parser.add_argument("--report", type=Path, default=None,
                        help="Write acceptance JSON to this path (default: output/p13-native/acceptance-report.json).")
    args = parser.parse_args()
    model_path = args.model.resolve()
    _assert(model_path.is_file(), f"GGUF model not found: {model_path}")
    _assert(0 <= args.cycles <= 50, "--cycles must be from 0 through 50.")
    _assert(args.cycles > 0 or args.idle_seconds >= 600 or args.unregistered_tool_only,
            "--cycles 0 requires a ten-minute idle measurement or the unregistered-tool-only scenario.")

    base = Path.cwd() / "output" / "p13-native"
    base.mkdir(parents=True, exist_ok=True)
    report_path = args.report or base / "acceptance-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    root_path = Path(tempfile.mkdtemp(prefix="run-", dir=base))
    fixture_dir = root_path / "read-only-fixture"
    fixture_dir.mkdir()
    (fixture_dir / "fixture.txt").write_text("PLUMA owned planner fixture\n", encoding="utf-8")

    runtime = _runtime(model_path, root_path)
    report = {
        "model_path": str(model_path),
        "model_bytes": model_path.stat().st_size,
        "python": __import__("sys").version,
        "cycles_requested": args.cycles,
        "cycles_completed": 0,
        "fast_route": None,
        "native_stop": None,
        "native_crash": None,
        "cycle_samples": [],
    }
    try:
        parent = psutil.Process(os.getpid())
        report["fast_parent_children_before"] = len(parent.children(recursive=True))
        fast = runtime.orchestrator.execute(PlumaRequest(
            input_mode=InputMode.TEXT,
            text="show activity",
        ))
        _assert(fast.route == RouteMode.FAST, "FAST acceptance command did not remain FAST.")
        _assert("llama_cpp" not in __import__("sys").modules,
                "FAST acceptance imported llama_cpp in the resident process.")
        _assert(not runtime.tool_registry._worker_controllers,
                "FAST acceptance created a task-owned model/tool worker.")
        report["fast_route"] = {
            "route": fast.route.value,
            "state": fast.final_state,
            "llama_cpp_in_parent": False,
            "owned_worker_count": len(runtime.tool_registry._worker_controllers),
        }

        if args.unregistered_tool_only:
            report["native_unregistered_tool"] = _native_rejects_unregistered_tool(
                runtime, fixture_dir
            )
        elif not args.skip_stop:
            report["native_stop"] = _interrupt_loaded_native_worker(runtime, fixture_dir)
            report["native_timeout"] = _interrupt_loaded_native_worker(
                runtime, fixture_dir, timeout=True
            )
            report["native_crash"] = _interrupt_loaded_native_worker(
                runtime, fixture_dir, crash=True
            )
            report["native_sensitive_context"] = {
                "task_id": _planner_task(
                    runtime, fixture_dir, "native-sensitive-context", secret_context=True
                ),
                "fake_secret_redacted_from_history": True,
                "redaction_path_exercised": True,
            }
            report["native_multistep"] = _native_multistep_task(runtime, fixture_dir)
            report["native_failure_replan"] = _native_failure_replan_task(runtime, fixture_dir)

        process = psutil.Process(os.getpid())
        baseline_rss = process.memory_info().rss
        baseline_handles = process.num_handles() if hasattr(process, "num_handles") else None
        baseline_children = len(process.children(recursive=True))
        for cycle in range(1, args.cycles + 1):
            task_id = _planner_task(runtime, fixture_dir, f"cycle-{cycle}")
            _assert(task_id not in runtime.tool_registry._worker_controllers,
                    f"cycle-{cycle}: registry retained the task worker.")
            _assert(not process.children(recursive=True),
                    f"cycle-{cycle}: a child worker remained after the task.")
            _assert(runtime.llm_lifecycle.state.value == "COLD",
                    f"cycle-{cycle}: model lifecycle did not return to COLD.")
            report["cycle_samples"].append({
                "cycle": cycle,
                "rss_bytes": process.memory_info().rss,
                "handles": process.num_handles() if hasattr(process, "num_handles") else None,
            })
            report["cycles_completed"] = cycle
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(f"P13 native lifecycle cycle {cycle}/{args.cycles} passed.", flush=True)

        final_rss = process.memory_info().rss
        final_handles = process.num_handles() if hasattr(process, "num_handles") else None
        final_children = len(process.children(recursive=True))
        report["resource_delta"] = {
            "rss_bytes": final_rss - baseline_rss,
            "handles": final_handles - baseline_handles if baseline_handles is not None else None,
            "children_before": baseline_children,
            "children_after": final_children,
        }
        _assert(final_children == baseline_children,
                "Repeated native cycles left an additional child process.")
        _assert(final_handles is None or final_handles <= baseline_handles + 8,
                "Repeated native cycles left additional process handles.")
        _assert(final_rss <= baseline_rss + 256 * 1024 * 1024,
                "Repeated native cycles retained more than 256 MiB in the resident process.")
        report["idle_unload_verified"] = runtime.llm_lifecycle.state.value == "COLD"
        report["resident_model_loaded"] = runtime.llm_lifecycle.adapter.is_loaded
        if args.idle_seconds:
            report["idle_baseline"] = _measure_cold_idle(
                runtime, args.idle_seconds, report_path, report
            )
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 0
    except BaseException as exc:
        report["failure"] = type(exc).__name__
        report["failure_detail"] = str(exc)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 1
    finally:
        runtime.close(timeout_s=30.0)


if __name__ == "__main__":
    raise SystemExit(main())
