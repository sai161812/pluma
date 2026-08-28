import os
import re

with open('pluma/tools/registry.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Add grounded_ui_target to WorkerRequest and WorkerTaskContext
code = re.sub(
    r'    env_overrides: Dict\[str, str\] = field\(default_factory=dict\)',
    '    env_overrides: Dict[str, str] = field(default_factory=dict)\n    grounded_ui_target: Optional[Dict[str, Any]] = None',
    code
)

code = re.sub(
    r'        self\.undo_stack: List\[Dict\[str, Any\]\] = \[\]',
    '        self.undo_stack: List[Dict[str, Any]] = []\n        self.grounded_ui_target: Optional[Dict[str, Any]] = None',
    code
)

code = re.sub(
    r'        worker_ctx\.undo_stack = list\(worker_req\.undo_stack\)',
    '        worker_ctx.undo_stack = list(worker_req.undo_stack)\n        worker_ctx.grounded_ui_target = worker_req.grounded_ui_target',
    code
)

# In ToolRegistry.execute
code = re.sub(
    r'''        env_flags = \{
            k: v for k, v in os\.environ\.items\(\)
            if k\.startswith\("PLUMA_"\)
        \}''',
    '''        env_flags = {
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
                            "auto_id": element.uia_automation_id,
                            "name": element.label,
                            "control_type": element.control_type,
                        }
                    except Exception as e:
                        # Fail early in parent
                        return ToolResult.failure(tool_name, f"Parent UI Grounding failed: {e}")
                else:
                    return ToolResult.failure(tool_name, "Parent UI Grounding rejected: no snapshot registry on task_context.")
''',
    code
)

code = re.sub(
    r'            env_overrides=env_flags,',
    '            env_overrides=env_flags,\n            grounded_ui_target=grounded_ui_target,',
    code
)

# After execute, register snapshot from inspect_active_window
code = re.sub(
    r'''                    # Propagate worker undo stack sync''',
    '''                    # Propagate snapshot
                    if tool_name == "inspect_active_window" and result.ok and task_context:
                        registry = getattr(task_context, "snapshot_registry", None)
                        if registry and "raw_snapshot" in result.data:
                            try:
                                from pluma.perception.element_refs import ScreenSnapshot
                                raw = result.data.pop("raw_snapshot")
                                registry.register(ScreenSnapshot.model_validate(raw))
                            except Exception:
                                pass
                    # Propagate worker undo stack sync''',
    code
)


with open('pluma/tools/registry.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Replacement done')
