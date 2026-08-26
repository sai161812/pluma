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
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

from pydantic import BaseModel, ValidationError

from pluma.tools.base import RiskClass, ToolResult, ToolSpec, VerifyResult

_GLOBAL_TOOL_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=16,
    thread_name_prefix="pluma_tool_exec",
)


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

        # 4. Execution with timeout enforcement and duration measurement
        start_t = time.perf_counter()
        timeout_s = spec.timeout_s if spec.timeout_s and spec.timeout_s > 0 else 30.0
        try:
            future = _GLOBAL_TOOL_EXECUTOR.submit(spec.executor, validated_args, task_context)
            try:
                result = future.result(timeout=timeout_s)
            except (TimeoutError, concurrent.futures.TimeoutError):
                future.cancel()
                duration_ms = (time.perf_counter() - start_t) * 1000.0

                # Abort any further side-effects by cancelling the task token
                if task_context and hasattr(task_context, "cancellation_token"):
                    try:
                        task_context.cancellation_token.cancel()
                    except Exception:
                        pass

                # Terminate any job object processes associated with this task
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
        except Exception as e:
            duration_ms = (time.perf_counter() - start_t) * 1000.0
            result = ToolResult.failure(tool_name, str(e), duration_ms=duration_ms)

        duration_ms = (time.perf_counter() - start_t) * 1000.0

        # 5. Postcondition verification
        verified = result.verified
        verify_detail = result.verify_detail
        if result.ok and spec.verifier:
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
