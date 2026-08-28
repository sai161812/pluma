import os
import re

with open('pluma/tools/ui.py', 'r', encoding='utf-8') as f:
    code = f.read()

# inspect_active_window
code = re.sub(
    r'''        # Register snapshot in task-scoped registry for downstream UI action grounding
        snapshot_id: Optional\[str\] = None
        if task_context is not None:
            registry = getattr\(task_context, "snapshot_registry", None\)
            if registry is not None:
                try:
                    from pluma.perception.snapshot_registry import SnapshotRegistry
                    if isinstance\(registry, SnapshotRegistry\):
                        registry.register\(snapshot\)
                        snapshot_id = snapshot.snapshot_id
                except Exception as reg_err:
                    logger.warning\("Failed to register snapshot in registry: %s", reg_err\)''',
    '''        snapshot_id = snapshot.snapshot_id''',
    code
)

code = re.sub(
    r'''            "controls": controls_summary,
        \}
        if snapshot_id:
            result_data\["snapshot_id"\] = snapshot_id''',
    '''            "controls": controls_summary,
            "snapshot_id": snapshot_id,
            "raw_snapshot": snapshot.model_dump(mode="json"),
        }''',
    code
)

# click_element
code = re.sub(
    r'''    snapshot_registry = getattr\(task_context, "snapshot_registry", None\)
    if snapshot_registry is None:
        return ToolResult\(
            ok=False, tool="click_element", data=args,
            factual_message="Snapshot grounding rejected: no snapshot registry on task_context\.",
            verified=False, error="NO_SNAPSHOT_REGISTRY",
        \)

    from pluma\.perception\.snapshot_registry import SnapshotNotFoundError, ElementNotFoundInSnapshotError
    from pluma\.perception\.element_refs import StaleSnapshotError

    try:
        snapshot = snapshot_registry\.resolve\(snapshot_id\)
    except SnapshotNotFoundError as e:
        return ToolResult\(ok=False, tool="click_element", data=args, factual_message=f"Snapshot grounding failed: \{e\}", verified=False, error=str\(e\)\)
    except StaleSnapshotError as e:
        return ToolResult\(ok=False, tool="click_element", data=args, factual_message=f"Snapshot grounding failed: \{e\}", verified=False, error=str\(e\)\)

    element_id = target_ref\.split\("::"\)\[-1\]
    try:
        element = snapshot_registry\.resolve_element\(snapshot_id, element_id\)
    except \(ElementNotFoundInSnapshotError, Exception\) as e:
        return ToolResult\(ok=False, tool="click_element", data=args, factual_message=f"Element target_ref resolution failed: \{e\}", verified=False, error=str\(e\)\)''',
    '''    grounded_ui_target = getattr(task_context, "grounded_ui_target", None)
    if not grounded_ui_target:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message="UI Grounding rejected: no grounded_ui_target provided by parent.",
            verified=False, error="NO_GROUNDED_UI_TARGET",
        )''',
    code
)

code = re.sub(
    r'''    # Revalidate active window identity against snapshot
    if snapshot.hwnd and active.hwnd != snapshot.hwnd:
        return ToolResult\(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window HWND changed from \{snapshot.hwnd\} to \{active.hwnd\}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        \)
    if snapshot.pid and active.pid and active.pid != snapshot.pid:
        return ToolResult\(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window PID changed from \{snapshot.pid\} to \{active.pid\}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        \)
    if snapshot.process_creation_time_ns and active.pid:
        cur_t = context.get_process_creation_time_ns\(active.pid\)
        if cur_t and cur_t != snapshot.process_creation_time_ns:
            return ToolResult\(
                ok=False, tool="click_element", data=args,
                factual_message="Process creation timestamp mismatch \(recycled PID\)\.",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            \)
    if snapshot.dpi_scale and abs\(active.dpi_scale - snapshot.dpi_scale\) > 0.05:
        return ToolResult\(
            ok=False, tool="click_element", data=args,
            factual_message=f"DPI scaling changed from \{snapshot.dpi_scale\} to \{active.dpi_scale\}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        \)

    hwnd = active.hwnd
    auto_id = element.uia_automation_id or args.get\("auto_id"\)
    name = element.label or args.get\("name"\)
    control_type = element.control_type or args.get\("control_type"\)''',
    '''    # Revalidate active window identity against snapshot
    if grounded_ui_target["snapshot_hwnd"] and active.hwnd != grounded_ui_target["snapshot_hwnd"]:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window HWND changed from {grounded_ui_target['snapshot_hwnd']} to {active.hwnd}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        )
    if grounded_ui_target["snapshot_pid"] and active.pid and active.pid != grounded_ui_target["snapshot_pid"]:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"Active window PID changed from {grounded_ui_target['snapshot_pid']} to {active.pid}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        )
    if grounded_ui_target["snapshot_creation_time_ns"] and active.pid:
        cur_t = context.get_process_creation_time_ns(active.pid)
        if cur_t and cur_t != grounded_ui_target["snapshot_creation_time_ns"]:
            return ToolResult(
                ok=False, tool="click_element", data=args,
                factual_message="Process creation timestamp mismatch (recycled PID).",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            )
    if grounded_ui_target["snapshot_dpi_scale"] and abs(active.dpi_scale - grounded_ui_target["snapshot_dpi_scale"]) > 0.05:
        return ToolResult(
            ok=False, tool="click_element", data=args,
            factual_message=f"DPI scaling changed from {grounded_ui_target['snapshot_dpi_scale']} to {active.dpi_scale}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        )

    hwnd = active.hwnd
    auto_id = grounded_ui_target["auto_id"]
    name = grounded_ui_target["name"]
    control_type = grounded_ui_target["control_type"]''',
    code
)

# type_into_element
code = re.sub(
    r'''    snapshot_registry = getattr\(task_context, "snapshot_registry", None\)
    if snapshot_registry is None:
        return ToolResult\(
            ok=False, tool="type_into_element", data=args,
            factual_message="Snapshot grounding rejected: no snapshot registry on task_context\.",
            verified=False, error="NO_SNAPSHOT_REGISTRY", error_code="NO_SNAPSHOT_REGISTRY",
        \)

    from pluma\.perception\.snapshot_registry import SnapshotNotFoundError, ElementNotFoundInSnapshotError
    from pluma\.perception\.element_refs import StaleSnapshotError

    try:
        snapshot = snapshot_registry\.resolve\(snapshot_id\)
    except SnapshotNotFoundError as e:
        return ToolResult\(ok=False, tool="type_into_element", data=args, factual_message=f"Snapshot grounding failed: \{e\}", verified=False, error=str\(e\), error_code="SNAPSHOT_NOT_FOUND"\)
    except StaleSnapshotError as e:
        return ToolResult\(ok=False, tool="type_into_element", data=args, factual_message=f"Snapshot grounding failed: \{e\}", verified=False, error=str\(e\), error_code="STALE_SNAPSHOT"\)

    element_id = target_ref\.split\("::"\)\[-1\]
    try:
        element = snapshot_registry\.resolve_element\(snapshot_id, element_id\)
    except \(ElementNotFoundInSnapshotError, Exception\) as e:
        return ToolResult\(ok=False, tool="type_into_element", data=args, factual_message=f"Element target_ref resolution failed: \{e\}", verified=False, error=str\(e\), error_code="ELEMENT_NOT_FOUND"\)''',
    '''    grounded_ui_target = getattr(task_context, "grounded_ui_target", None)
    if not grounded_ui_target:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message="UI Grounding rejected: no grounded_ui_target provided by parent.",
            verified=False, error="NO_GROUNDED_UI_TARGET", error_code="NO_GROUNDED_UI_TARGET",
        )''',
    code
)

code = re.sub(
    r'''    # Revalidate active window identity against snapshot
    if snapshot.hwnd and active.hwnd != snapshot.hwnd:
        return ToolResult\(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window HWND changed from \{snapshot.hwnd\} to \{active.hwnd\}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        \)
    if snapshot.pid and active.pid and active.pid != snapshot.pid:
        return ToolResult\(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window PID changed from \{snapshot.pid\} to \{active.pid\}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        \)
    if snapshot.process_creation_time_ns and active.pid:
        cur_t = context.get_process_creation_time_ns\(active.pid\)
        if cur_t and cur_t != snapshot.process_creation_time_ns:
            return ToolResult\(
                ok=False, tool="type_into_element", data=args,
                factual_message="Process creation timestamp mismatch \(recycled PID\)\.",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            \)
    if snapshot.dpi_scale and abs\(active.dpi_scale - snapshot.dpi_scale\) > 0.05:
        return ToolResult\(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"DPI scaling changed from \{snapshot.dpi_scale\} to \{active.dpi_scale\}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        \)


    hwnd = active.hwnd
    auto_id = element.uia_automation_id or args.get\("auto_id"\)
    name = element.label or args.get\("name"\)''',
    '''    # Revalidate active window identity against snapshot
    if grounded_ui_target["snapshot_hwnd"] and active.hwnd != grounded_ui_target["snapshot_hwnd"]:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window HWND changed from {grounded_ui_target['snapshot_hwnd']} to {active.hwnd}",
            verified=False, error="WINDOW_MISMATCH", error_code="WINDOW_MISMATCH",
        )
    if grounded_ui_target["snapshot_pid"] and active.pid and active.pid != grounded_ui_target["snapshot_pid"]:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"Active window PID changed from {grounded_ui_target['snapshot_pid']} to {active.pid}",
            verified=False, error="PROCESS_MISMATCH", error_code="PROCESS_MISMATCH",
        )
    if grounded_ui_target["snapshot_creation_time_ns"] and active.pid:
        cur_t = context.get_process_creation_time_ns(active.pid)
        if cur_t and cur_t != grounded_ui_target["snapshot_creation_time_ns"]:
            return ToolResult(
                ok=False, tool="type_into_element", data=args,
                factual_message="Process creation timestamp mismatch (recycled PID).",
                verified=False, error="PROCESS_IDENTITY_MISMATCH", error_code="PROCESS_IDENTITY_MISMATCH",
            )
    if grounded_ui_target["snapshot_dpi_scale"] and abs(active.dpi_scale - grounded_ui_target["snapshot_dpi_scale"]) > 0.05:
        return ToolResult(
            ok=False, tool="type_into_element", data=args,
            factual_message=f"DPI scaling changed from {grounded_ui_target['snapshot_dpi_scale']} to {active.dpi_scale}",
            verified=False, error="DPI_MISMATCH", error_code="DPI_MISMATCH",
        )

    hwnd = active.hwnd
    auto_id = grounded_ui_target["auto_id"]
    name = grounded_ui_target["name"]''',
    code
)

with open('pluma/tools/ui.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('UI update done')
