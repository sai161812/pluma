import os
import re

with open('pluma/tools/registry.py', 'r', encoding='utf-8') as f:
    code = f.read()

# In ToolRegistry.execute
code = re.sub(
    r'''        if use_process_isolation:
            try:
                status, payload = _GLOBAL_WORKER_POOL.execute\(
                    spec.executor,
                    validated_args,
                    worker_req,
                    timeout_s,
                    task_context=task_context,
                \)''',
    '''        if use_process_isolation:
            try:
                worker_controller = TaskWorkerController(task_id=task_id or "global")
                status, payload = worker_controller.execute_call(
                    spec.executor,
                    validated_args,
                    worker_req,
                    timeout_s,
                    job_object=getattr(task_context, "job_object", None) if task_context else None,
                )''',
    code
)

with open('pluma/tools/registry.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Replacement done')
