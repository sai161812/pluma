import os
import re

with open('pluma/tools/registry.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''                if status == "ok":
                    if isinstance(payload, WorkerPayload):
                        result = payload.result
                        # Propagate worker undo stack sync
                        if payload.final_undo_stack is not None and task_context and hasattr(task_context, "undo_stack"):
                            task_context.undo_stack.clear()
                            task_context.undo_stack.extend(payload.final_undo_stack)
                        elif payload.undo_data and task_context and hasattr(task_context, "undo_stack") and payload.undo_data not in task_context.undo_stack:
                            task_context.undo_stack.append(payload.undo_data)
                    elif isinstance(payload, ToolResult):
                        result = payload
                    else:
                        result = ToolResult.failure(tool_name, "Invalid worker response payload format")
                        
                    # Handle snapshot grounding registrations from worker
                    registry = getattr(task_context, "snapshot_registry", None)
                    if registry and "raw_snapshot" in result.data:
                        try:
                            from pluma.perception.element_refs import ScreenSnapshot
                            raw = result.data.pop("raw_snapshot")
                            registry.register(ScreenSnapshot.model_validate(raw))
                        except Exception:
                            pass
                elif status == "timeout":'''

code = re.sub(
    r'''                if status == "ok" and isinstance\(payload, WorkerPayload\):.*?                elif status == "ok" and isinstance\(payload, ToolResult\):\n                    result = payload\n                elif status == "timeout":''',
    replacement,
    code,
    flags=re.DOTALL
)

with open('pluma/tools/registry.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Registry raw_snapshot fixed')
