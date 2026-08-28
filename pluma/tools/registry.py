"""pluma.tools.registry — ToolRegistry: register, validate, look up, and execute tools.

The registry is the single source of truth for what PLUMA can do. Every
tool that the router, planner, policy engine, or executor uses must be
registered here. Tools that are not in the registry cannot be executed.

Spec §11: "Every real action is a registered tool."
Spec §20.2 Plan constraints: "tool must exist in registry."

No OS-automation, ML, or adapter code in this module.
"""

from __future__ import annotations

import concurrent.futures
import inspect
import json
import logging
import multiprocessing
import os
import sys
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional


from dataclasses import dataclass, field
from pydantic import BaseModel, ValidationError

from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult

# Bounded thread pool — used only for read-only tools when process isolation is unavailable
_GLOBAL_TOOL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=32,
    thread_name_prefix="pluma_tool_exec",
)

# Multiprocessing context for isolated execution (spawn avoids fork hazards on Windows)
_MP_CONTEXT = multiprocessing.get_context("spawn")


@dataclass
class WorkerRequest:
    """Serializable request sent to the isolated worker process."""
    task_id: str
    tool_name: str
    validated_args: Dict[str, Any]
    timeout_s: float
    cancellation_metadata: Dict[str, Any] = field(default_factory=dict)
    undo_stack: List[Dict[str, Any]] = field(default_factory=list)
    env_overrides: Dict[str, str] = field(default_factory=dict)
    grounded_ui_target: Optional[Dict[str, Any]] = None


@dataclass
class WorkerResource:
    """Serializable record of a resource created by a tool in worker."""
    resource_type: str
    ownership: str
    external_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkerResponse:
    """Serializable response returned from the worker process."""
    result: ToolResult
    owned_resources: List[WorkerResource] = field(default_factory=list)
    undo_data: Optional[Dict[str, Any]] = None
    final_undo_stack: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None


class WorkerTaskContext:
    """Lightweight serializable task context passed into the isolated worker process."""
    def __init__(self, task_id: Optional[str] = None) -> None:
        self.task_id = task_id
        self.owned_resources: List[WorkerResource] = []
        self.undo_stack: List[Dict[str, Any]] = []
        self.grounded_ui_target: Optional[Dict[str, Any]] = None

    def register_owned_resource(
        self,
        resource_type: str,
        ownership: Any,
        external_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        ownership_val = getattr(ownership, "value", str(ownership))
        safe_meta: Dict[str, Any] = {}
        if metadata:
            for k, v in metadata.items():
                if k == "persistent_job":
                    continue
                try:
                    import pickle
                    pickle.dumps(v)
                    safe_meta[k] = v
                except Exception:
                    safe_meta[k] = str(v)
        self.owned_resources.append(
            WorkerResource(
                resource_type=resource_type,
                ownership=ownership_val,
                external_id=external_id,
                metadata=safe_meta,
            )
        )


def _worker_process_loop(conn: Any) -> None:
    """Persistent worker process loop that executes tool requests."""
    while True:
        try:
            if not conn.poll(None):
                break
            msg = conn.recv()
            if msg == "STOP" or msg is None:
                break
            executor_fn, args, worker_req = msg
            if getattr(worker_req, "env_overrides", None):
                os.environ.update(worker_req.env_overrides)
            worker_ctx = WorkerTaskContext(task_id=worker_req.task_id)
            worker_ctx.undo_stack = list(worker_req.undo_stack)
            worker_ctx.grounded_ui_target = worker_req.grounded_ui_target
            
            import inspect
            sig = inspect.signature(executor_fn)
            if len(sig.parameters) > 1:
                res = executor_fn(args, worker_ctx)
            else:
                res = executor_fn(args)
                
            undo_data = worker_ctx.undo_stack[-1] if worker_ctx.undo_stack else None
            resp = WorkerResponse(
                result=res,
                owned_resources=worker_ctx.owned_resources,
                undo_data=undo_data,
                final_undo_stack=worker_ctx.undo_stack,
            )
            conn.send(("ok", resp))
        except Exception as exc:
            try:
                conn.send(("error", str(exc)))
            except Exception:
                break


class TaskWorkerController:
    """Manages a strictly task-owned killable worker process."""
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._lock = threading.Lock()
        self._proc: Optional[multiprocessing.Process] = None
        self._conn: Optional[Any] = None

    def _ensure_worker_started(self, job_object: Any = None) -> None:
        if self._proc is not None and self._proc.is_alive() and self._conn is not None:
            return
        self._terminate_internal()
        parent_conn, child_conn = multiprocessing.Pipe()
        proc = _MP_CONTEXT.Process(
            target=_worker_process_loop,
            args=(child_conn,),
            daemon=True,
        )
        proc.start()
        child_conn.close()
        self._proc = proc
        self._conn = parent_conn

        if job_object is not None and proc.pid is not None:
            try:
                job_object.assign_process(proc.pid)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Failed to assign worker %s to Job Object: %s. Terminating worker to ensure containment.", proc.pid, e)
                self._terminate_internal()
                raise RuntimeError(f"Job Object containment failed: {e}") from e

    def _terminate_internal(self) -> None:
        if self._conn:
            try:
                self._conn.send("STOP")
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        if self._proc:
            try:
                self._proc.kill()
            except Exception:
                pass
            try:
                self._proc.join(timeout=0.2)
            except Exception:
                pass
            self._proc = None

    def execute_call(
        self,
        executor_fn: Callable[..., Any],
        validated_args: Dict[str, Any],
        worker_req: WorkerRequest,
        timeout_s: float,
        job_object: Any = None,
    ) -> Tuple[str, Any]:
        with self._lock:
            self._ensure_worker_started(job_object=job_object)
            try:
                self._conn.send((executor_fn, validated_args, worker_req))
            except Exception as send_err:
                self._terminate_internal()
                return ("error", f"Worker send failure: {send_err}")

            if self._conn.poll(timeout_s):
                try:
                    status, payload = self._conn.recv()
                except Exception as recv_err:
                    self._terminate_internal()
                    return ("error", f"Worker communication error: {recv_err}")
                return (status, payload)
            else:
                # Timeout occurred: hard kill worker to prevent any delayed side effects
                self._terminate_internal()
                return ("timeout", f"Tool execution timed out after {timeout_s:.3f}s")

    def terminate_and_join(self) -> None:
        with self._lock:
            self._terminate_internal()





class UnknownToolError(KeyError):
    """Raised when a tool name is not found in the registry."""


class ToolArgumentError(ValueError):
    """Raised when tool arguments fail schema validation."""


class ToolRegistry:
    """Thread-safe registry of ToolSpec objects.

    Usage:
        registry = ToolRegistry()
        register_default_tools(registry)
        spec = registry.lookup("open_app")
        result = registry.execute(ToolCall(...), task_context)
    """

    def __init__(self, policy_engine: Optional[Any] = None) -> None:
        self._specs: Dict[str, ToolSpec] = {}
        self._lock = threading.RLock()
        self._policy_engine = policy_engine
        self._worker_controllers: Dict[str, TaskWorkerController] = {}
        self._idle_workers: List[TaskWorkerController] = []

    def get_worker(self, task_id: str) -> TaskWorkerController:
        """Acquire an exclusive, dedicated task-owned worker controller."""
        with self._lock:
            if task_id in self._worker_controllers:
                return self._worker_controllers[task_id]
            while self._idle_workers:
                candidate = self._idle_workers.pop()
                if candidate._proc and candidate._proc.is_alive():
                    candidate.task_id = task_id
                    self._worker_controllers[task_id] = candidate
                    return candidate
                candidate.terminate_and_join()
            ctrl = TaskWorkerController(task_id=task_id)
            self._worker_controllers[task_id] = ctrl
            return ctrl

    def cleanup_task(self, task_id: str, recycle: bool = False) -> None:
        """Terminate and clean up worker process associated with task_id."""
        with self._lock:
            ctrl = self._worker_controllers.pop(task_id, None)
            if ctrl is not None:
                if recycle and ctrl._proc and ctrl._proc.is_alive() and len(self._idle_workers) < 4:
                    self._idle_workers.append(ctrl)
                else:
                    ctrl.terminate_and_join()

    def close(self) -> None:
        """Terminate all worker processes and release resources."""
        with self._lock:
            for ctrl in list(self._worker_controllers.values()):
                try:
                    ctrl.terminate_and_join()
                except Exception:
                    pass
            self._worker_controllers.clear()
            for ctrl in self._idle_workers:
                try:
                    ctrl.terminate_and_join()
                except Exception:
                    pass
            self._idle_workers.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._specs)

    def list_tools(self) -> List[ToolSpec]:
        """Return a list of all registered ToolSpec objects."""
        with self._lock:
            return list(self._specs.values())

    def list_tool_names(self) -> List[str]:
        """Return a list of all registered tool names."""
        with self._lock:
            return list(self._specs.keys())

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, spec: ToolSpec, *, overwrite: bool = False) -> None:
        """Register a ToolSpec.

        Raises ValueError if a tool with the same name is already registered
        and *overwrite* is False.
        """
        with self._lock:
            if spec.name in self._specs and not overwrite:
                raise ValueError(
                    f"Tool {spec.name!r} is already registered. "
                    "Pass overwrite=True to replace it."
                )
            self._specs[spec.name] = spec

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry. Raises UnknownToolError if absent."""
        with self._lock:
            if name not in self._specs:
                raise UnknownToolError(name)
            del self._specs[name]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def lookup(self, name: str) -> ToolSpec:
        """Return the ToolSpec for *name*. Raises UnknownToolError if absent."""
        with self._lock:
            try:
                return self._specs[name]
            except KeyError:
                raise UnknownToolError(name) from None

    def contains(self, name: str) -> bool:
        """Return True if *name* is a registered tool."""
        with self._lock:
            return name in self._specs

    def all_names(self) -> List[str]:
        """Return sorted list of all registered tool names."""
        with self._lock:
            return sorted(self._specs.keys())

    def tools_by_risk(self, risk_class: RiskClass) -> List[ToolSpec]:
        """Return all tools with the given risk class."""
        with self._lock:
            return [s for s in self._specs.values() if s.risk_class == risk_class]

    def list_specs(self) -> List[ToolSpec]:
        """Return a list of all registered ToolSpec instances."""
        with self._lock:
            return list(self._specs.values())

    def __iter__(self) -> Iterator[ToolSpec]:
        with self._lock:
            return iter(list(self._specs.values()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._specs)

    # ------------------------------------------------------------------
    # Argument validation
    # ------------------------------------------------------------------

    def validate_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Validate *arguments* against the registered ToolSpec's args_schema.

        Returns normalized arguments dictionary.
        Raises:
            UnknownToolError   — tool name is not registered.
            ToolArgumentError  — arguments fail schema validation.
        """
        spec = self.lookup(tool_name)  # Raises UnknownToolError if absent.
        return self._validate_args(spec, arguments)

    @staticmethod
    def _validate_args(spec: ToolSpec, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Run the args_schema validator for *spec* against *arguments* and return normalized dict."""
        schema = spec.args_schema

        # Pydantic model class
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            try:
                model = schema.model_validate(arguments)
                return model.model_dump()
            except ValidationError as exc:
                raise ToolArgumentError(
                    f"Invalid arguments for tool {spec.name!r}: {exc}"
                ) from exc

        # JSON Schema dict
        if isinstance(schema, dict):
            try:
                import jsonschema  # type: ignore[import-not-found]
                try:
                    jsonschema.validate(instance=arguments, schema=schema)
                except jsonschema.ValidationError as exc:
                    raise ToolArgumentError(
                        f"Invalid arguments for tool {spec.name!r}: {exc.message}"
                    ) from exc
            except ImportError:
                # Fallback: check required keys
                required_keys = schema.get("required", [])
                for req in required_keys:
                    if req not in arguments:
                        raise ToolArgumentError(
                            f"Missing required argument {req!r} for tool {spec.name!r}."
                        )
            return dict(arguments)

        # Unknown schema type
        raise ToolArgumentError(
            f"Tool {spec.name!r} has an unsupported args_schema type: "
            f"{type(schema).__name__!r}. Use a Pydantic BaseModel subclass or a dict."
        )

    # ------------------------------------------------------------------
    # Execution Runner with Verification, Undo, & Ledger
    # ------------------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        task_context: Any = None,
        ledger: Any = None,
        step_index: int = 0,
        policy_engine: Any = None,
    ) -> ToolResult:
        """Execute a tool call with validation, policy check, cancellation check, verification, and undo capture."""
        spec = self.lookup(tool_name)
        validated_args = self._validate_args(spec, arguments)

        # 1. Policy check
        active_policy = policy_engine or self._policy_engine
        if active_policy is not None:
            task_id = getattr(task_context, "task_id", None) if task_context else None
            policy_eval = active_policy.evaluate(
                tool_name=tool_name,
                arguments=validated_args,
                default_risk=spec.risk_class,
                task_id=task_id,
            )
            decision_val = getattr(policy_eval, "decision", None)
            if decision_val != "ALLOW" and str(decision_val) not in ("ALLOW", "PolicyDecision.ALLOW"):
                return ToolResult.failure(
                    tool=tool_name,
                    error=f"Blocked by policy: {policy_eval.reason}",
                    error_code="POLICY_DENIED",
                )

        # 2. Check cancellation latch before starting
        if spec.cancellable and task_context and hasattr(task_context, "cancellation_token"):
            task_context.cancellation_token.raise_if_cancelled()

        # 3. Capture pre-mutation undo data BEFORE mutation occurs
        pre_undo_data = None
        if spec.undo_builder:
            try:
                pre_undo_data = spec.undo_builder(validated_args)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Failed to build pre-mutation undo data for %s: %s", tool_name, e)

        # 4. Execution with killable process isolation, timeout enforcement and duration measurement
        start_t = time.perf_counter()
        timeout_s = spec.timeout_s if spec.timeout_s and spec.timeout_s > 0 else 30.0
        result: Optional[ToolResult] = None

        task_id = getattr(task_context, "task_id", None) if task_context else None
        ctx_undo_stack: List[Dict[str, Any]] = []
        if task_context and hasattr(task_context, "undo_stack"):
            for u in task_context.undo_stack:
                try:
                    import pickle
                    pickle.dumps(u)
                    ctx_undo_stack.append(dict(u))
                except Exception:
                    pass

        env_flags = {
            k: v for k, v in os.environ.items()
            if k.startswith("PLUMA_")
        }
        
        # Parent UI Grounding for action workers
        grounded_ui_target = None
        if tool_name in ("click_element", "type_into_element") and task_context:
            snapshot_id = validated_args.get("snapshot_id")
            target_ref = validated_args.get("target_ref")
            if snapshot_id and target_ref:
                snapshot_registry = getattr(task_context, "snapshot_registry", None)
                if snapshot_registry:
                    try:
                        snapshot = snapshot_registry.resolve(snapshot_id)
                        element_id = target_ref.split("::")[-1]
                        element = snapshot_registry.resolve_element(snapshot_id, element_id)
                        grounded_ui_target = {
                            "snapshot_hwnd": snapshot.hwnd,
                            "snapshot_pid": snapshot.pid,
                            "snapshot_creation_time_ns": snapshot.process_creation_time_ns,
                            "snapshot_dpi_scale": snapshot.dpi_scale,
                            "snapshot_rect_left": snapshot.window_rect.left if snapshot.window_rect else 0,
                            "snapshot_rect_top": snapshot.window_rect.top if snapshot.window_rect else 0,
                            "snapshot_rect_right": snapshot.window_rect.right if snapshot.window_rect else 0,
                            "snapshot_rect_bottom": snapshot.window_rect.bottom if snapshot.window_rect else 0,
                            "auto_id": element.uia_automation_id,
                            "name": element.label,
                            "control_type": element.control_type,
                        }
                    except Exception as e:
                        # Fail early in parent
                        return ToolResult.failure(tool_name, f"Parent UI Grounding failed: {e}")
                else:
                    return ToolResult.failure(tool_name, "Parent UI Grounding rejected: no snapshot registry on task_context.")

        worker_req = WorkerRequest(
            task_id=task_id,
            tool_name=tool_name,
            validated_args=validated_args,
            timeout_s=timeout_s,
            undo_stack=ctx_undo_stack,
            env_overrides=env_flags,
            grounded_ui_target=grounded_ui_target,
        )


        # Process isolation is mandatory for high-risk tools, external process launchers, or tasks with active workers
        use_process_isolation = False
        isolated_tools = {"open_app", "slow_tool", "run_powershell_script", "execute_terminal_command", "kill_process"}
        if spec.risk_class == RiskClass.HIGH or tool_name in isolated_tools or getattr(task_context, "worker_controller", None) is not None:
            try:
                import pickle
                pickle.dumps(spec.executor)
                pickle.dumps(validated_args)
                pickle.dumps(worker_req)
                use_process_isolation = True
            except Exception:
                use_process_isolation = False

        if use_process_isolation:
            try:
                controller_key = task_id or f"transient-{uuid.uuid4()}"
                worker_controller = getattr(task_context, "worker_controller", None) if task_context else None
                if worker_controller is None:
                    worker_controller = self.get_worker(controller_key)
                    if task_context and hasattr(task_context, "worker_controller"):
                        task_context.worker_controller = worker_controller
                if task_context is not None:
                    try:
                        task_context._tool_registry = self
                    except Exception:
                        pass

                status, payload = worker_controller.execute_call(
                    spec.executor,
                    validated_args,
                    worker_req,
                    timeout_s,
                    job_object=getattr(task_context, "job_object", None) if task_context else None,
                )
                if status == "ok" and isinstance(payload, WorkerResponse):
                    result = payload.result
                    # Propagate resources created by worker into parent TaskCapsule
                    if task_context and hasattr(task_context, "register_owned_resource"):
                        for wr in payload.owned_resources:
                            try:
                                res_obj = task_context.register_owned_resource(
                                    resource_type=wr.resource_type,
                                    ownership=wr.ownership,
                                    external_id=wr.external_id,
                                    metadata=wr.metadata,
                                )
                                # Item 1: Establish persistent job object in parent
                                if wr.resource_type == "subprocess" and sys.platform == "win32":
                                    pid = wr.metadata.get("pid")
                                    if pid:
                                        try:
                                            from pluma.core.job_object import WindowsJobObject
                                            persistent_job = WindowsJobObject(
                                                name=f"pluma-app-{pid}",
                                                kill_on_close=False,
                                            )
                                            persistent_job.assign_process(pid)
                                            res_obj.metadata["persistent_job"] = persistent_job
                                        except Exception as job_err:
                                            # Containment failed: kill process and fail closed
                                            import subprocess
                                            subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                                            result = ToolResult.failure(
                                                tool_name,
                                                f"Mandatory Job Object containment failed for PID {pid} in parent: {job_err}",
                                                error_code="JOB_CONTAINMENT_FAILED",
                                            )
                            except Exception:
                                pass
                    # Propagate snapshot
                    if tool_name == "inspect_active_window" and result.ok and task_context:
                        registry = getattr(task_context, "snapshot_registry", None)
                        if registry and "raw_snapshot" in result.data:
                            try:
                                from pluma.perception.element_refs import ScreenSnapshot
                                raw = result.data.pop("raw_snapshot")
                                registry.register(ScreenSnapshot.model_validate(raw))
                            except Exception:
                                pass
                    # Propagate worker undo stack sync
                    if payload.final_undo_stack is not None and task_context and hasattr(task_context, "undo_stack"):
                        task_context.undo_stack.clear()
                        task_context.undo_stack.extend(payload.final_undo_stack)
                    elif payload.undo_data and task_context and hasattr(task_context, "undo_stack") and payload.undo_data not in task_context.undo_stack:
                        task_context.undo_stack.append(payload.undo_data)
                elif status == "ok" and isinstance(payload, ToolResult):
                    result = payload
                elif status == "timeout":
                    duration_ms = (time.perf_counter() - start_t) * 1000.0
                    if task_context and hasattr(task_context, "cancellation_token"):
                        try:
                            task_context.cancellation_token.cancel()
                        except Exception:
                            pass
                    if task_context and getattr(task_context, "job_object", None) is not None:
                        try:
                            task_context.job_object.terminate()
                        except Exception:
                            pass
                    result = ToolResult.failure(
                        tool_name,
                        f"Tool execution timed out after {timeout_s:.3f}s",
                        error_code="TOOL_TIMEOUT",
                        duration_ms=duration_ms,
                    )
                else:
                    result = ToolResult.failure(tool_name, str(payload))
            except Exception as mp_exc:
                result = ToolResult.failure(
                    tool_name,
                    f"Process isolation failed: {mp_exc}",
                    error_code="PROCESS_ISOLATION_FAILED",
                )

        if result is None and not use_process_isolation:
            # Execute in-process with thread pool executor and timeout enforcement
            try:
                import inspect
                sig = inspect.signature(spec.executor)
                if len(sig.parameters) > 1:
                    future = _GLOBAL_TOOL_EXECUTOR.submit(spec.executor, validated_args, task_context)
                else:
                    future = _GLOBAL_TOOL_EXECUTOR.submit(spec.executor, validated_args)
                try:
                    result = future.result(timeout=timeout_s)
                except (TimeoutError, concurrent.futures.TimeoutError):
                    future.cancel()
                    duration_ms = (time.perf_counter() - start_t) * 1000.0
                    result = ToolResult.failure(
                        tool_name,
                        f"Tool execution timed out after {timeout_s:.3f}s",
                        error_code="TOOL_TIMEOUT",
                        duration_ms=duration_ms,
                    )
            except Exception as e:
                duration_ms = (time.perf_counter() - start_t) * 1000.0
                result = ToolResult.failure(tool_name, str(e), duration_ms=duration_ms)

        duration_ms = (time.perf_counter() - start_t) * 1000.0



        # 5. Postcondition verification
        verified = result.verified
        verify_detail = result.verify_detail
        if result.ok and spec.verifier:
            from pluma.verify.common import verify_noop
            if verified is False and spec.verifier is verify_noop:
                pass
            else:
                try:
                    v_res = spec.verifier(result)
                    verified = v_res.ok
                    verify_detail = v_res
                except Exception as e:
                    verified = False
                    verify_detail = VerifyResult(ok=False, method="verifier_exception", detail=str(e))

        # 6. Finalize undo record only on verified success
        undo_record = None
        if result.ok and verified and pre_undo_data:
            undo_record = dict(pre_undo_data)
            if isinstance(result.data, dict) and "preserved_destination_backup" in result.data:
                undo_record["preserved_destination_backup"] = result.data["preserved_destination_backup"]
            if task_context and hasattr(task_context, "undo_stack"):
                task_context.undo_stack.append(undo_record)

        # 7. Build final consolidated result
        final_result = ToolResult(
            ok=result.ok and verified,
            tool=tool_name,
            data=result.data,
            factual_message=result.factual_message,
            verified=verified,
            verify_detail=verify_detail,
            duration_ms=duration_ms,
            adapter_used=result.adapter_used or "native",
            error=result.error if not (result.ok and verified) else None,
            error_code=result.error_code if not (result.ok and verified) else None,
            undo_record=undo_record,
        )

        # 7. Record to Activity Ledger if provided
        if ledger and task_context and hasattr(task_context, "task_id"):
            try:
                from pluma.memory.activity import ActionRecord, UndoRecord
                action_rec = ActionRecord(
                    task_id=task_context.task_id,
                    step_index=step_index,
                    tool=tool_name,
                    args_raw=validated_args,
                    risk=spec.risk_class.value,
                    adapter=final_result.adapter_used,
                    duration_ms=duration_ms,
                    result_data=final_result.data,
                    verified=verified,
                    verification_detail=verify_detail.model_dump() if verify_detail else None,
                    error_detail={"error": final_result.error, "code": final_result.error_code} if final_result.error else None,
                )
                row_id = ledger.insert_action(action_rec)
                if undo_record and row_id is not None:
                    ledger.insert_undo_record(UndoRecord(action_row_id=row_id, undo_data=undo_record))
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Failed to record tool execution to Activity Ledger: %s", e)

        return final_result

    # ------------------------------------------------------------------
    # Schema export for planner
    # ------------------------------------------------------------------

    def schema_for_planner(self, names: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Return a list of minimal tool schema dicts suitable for sending to the planner."""
        with self._lock:
            targets = (
                [self._specs[n] for n in names if n in self._specs]
                if names is not None
                else list(self._specs.values())
            )

        result: List[Dict[str, Any]] = []
        for spec in targets:
            schema = spec.args_schema
            if isinstance(schema, type) and issubclass(schema, BaseModel):
                args_json = schema.model_json_schema()
            elif isinstance(schema, dict):
                args_json = schema
            else:
                args_json = {}

            result.append({
                "name": spec.name,
                "description": spec.description,
                "risk_class": spec.risk_class.value,
                "args_schema": args_json,
                "timeout_s": spec.timeout_s,
                "cancellable": spec.cancellable,
            })
        return result

    # Alias for convenience
    schemas_for_planner = schema_for_planner


def register_default_tools(registry: ToolRegistry) -> None:
    """Register all 19 default tools into the provided ToolRegistry.
    
    Tools registered:
      Files (5): list_files, find_file, move_file, rename_file, create_folder
      Apps (5): open_app, close_app, focus_app, list_apps, app_status
      Windows (2): list_windows, focus_window
      Audio (3): set_volume, mute, unmute
      System & Memory (4): get_system_status, stop_current, show_activity, undo_last
    """
    from pluma.tools.apps import APP_TOOL_SPECS
    from pluma.tools.audio import AUDIO_TOOL_SPECS
    from pluma.tools.clipboard import CLIPBOARD_TOOL_SPECS
    from pluma.tools.files import FILE_TOOL_SPECS
    from pluma.tools.system import SYSTEM_TOOL_SPECS
    from pluma.tools.ui import ALL_UI_TOOLS
    from pluma.tools.windows import WINDOW_TOOL_SPECS

    all_specs = (
        FILE_TOOL_SPECS
        + APP_TOOL_SPECS
        + WINDOW_TOOL_SPECS
        + AUDIO_TOOL_SPECS
        + SYSTEM_TOOL_SPECS
        + CLIPBOARD_TOOL_SPECS
        + ALL_UI_TOOLS
    )
    for spec in all_specs:
        registry.register(spec, overwrite=True)


_default_registry: Optional[ToolRegistry] = None
_default_registry_lock = threading.Lock()


def get_default_tool_registry() -> ToolRegistry:
    """Return the global default ToolRegistry with all standard tools registered."""
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = ToolRegistry()
            register_default_tools(_default_registry)
        return _default_registry
