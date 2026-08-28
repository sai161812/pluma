import re

with open('tests/benchmarks/test_memory_soak.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''        print(
            "\\n[SOAK TEST] 1,000 Tasks Completed:\\n"
            f"RSS: {start_res['rss']:.2f}MB -> {end_res['rss']:.2f}MB (Delta: {delta_rss:+.2f}MB)\\n"
            f"Handles: {start_res['handles']} -> {end_res['handles']} (Delta: {delta_handles:+d})\\n"
            f"Threads: {start_res['threads']} -> {end_res['threads']} (Delta: {delta_threads:+d})\\n"
            f"Children: {start_res['children']} -> {end_res['children']}\\n"
            f"Active Capsules: {start_res['active_capsules']} -> {end_res['active_capsules']}\\n"
            f"Job Objects: {start_res['job_objects']} -> {end_res['job_objects']}\\n"
            f"Temporary Files: {start_res['temp_files']} -> {end_res['temp_files']} (Delta: {delta_temp})"
        )'''

code = re.sub(
    r'        print\(\n            f"\\n\[SOAK TEST\].*?\{delta_temp\}\)"\n        \)',
    replacement,
    code,
    flags=re.DOTALL
)

with open('tests/benchmarks/test_memory_soak.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Soak test print statement fixed")
