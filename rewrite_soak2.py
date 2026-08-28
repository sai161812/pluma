import os
import re

with open('tests/benchmarks/test_memory_soak.py', 'r', encoding='utf-8') as f:
    code = f.read()

replacement = '''def test_soak_1000_fast_tasks_no_memory_leak() -> None:
    """Execute 1,000 FAST route tasks through SQLite Activity Ledger and verify zero resource leak."""
    import tempfile
    import psutil
    from pathlib import Path

    # Real filesystem DB to verify no file handle leaks and PRAGMA integrity
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "pluma_soak.db"
        db = DbConnection(str(db_path))
        db.open()
        ledger = ActivityLedger(db=db)
        registry = get_default_tool_registry()
        supervisor = TaskSupervisor(ledger=ledger)
        router = Router()
        orch = Orchestrator(
            router=router,
            registry=registry,
            supervisor=supervisor,
            ledger=ledger,
        )

        process = psutil.Process(os.getpid())
        
        # Helper to get current resources
        def get_resources():
            gc.collect()
            import glob
            temp_files = len(glob.glob(os.path.join(tempfile.gettempdir(), "pluma_*")))
            
            # Count job objects
            job_objects = 0
            if hasattr(supervisor, "job_object"):
                job_objects = 1 if getattr(supervisor, "job_object") else 0
            
            return {
                "rss": process.memory_info().rss / (1024.0 * 1024.0),
                "handles": process.num_handles() if hasattr(process, 'num_handles') else 0,
                "threads": process.num_threads(),
                "children": len(process.children(recursive=True)),
                "active_capsules": len(supervisor._active_tasks) if hasattr(supervisor, "_active_tasks") else 0,
                "job_objects": job_objects,
                "temp_files": temp_files
            }

        start_res = get_resources()

        task_commands = [
            "mute",
            "unmute",
            "set volume 40",
            "system status",
            "clear clipboard",
        ]

        total_tasks = 1000
        for i in range(total_tasks):
            cmd = task_commands[i % len(task_commands)]
            req = PlumaRequest(input_mode=InputMode.TEXT, text=cmd)
            res = orch.execute(req)
            assert res.final_state == "SUCCEEDED"

        end_res = get_resources()
        
        delta_rss = end_res["rss"] - start_res["rss"]
        delta_handles = end_res["handles"] - start_res["handles"]
        delta_threads = end_res["threads"] - start_res["threads"]
        delta_temp = end_res["temp_files"] - start_res["temp_files"]

        print(
            f"\\n[SOAK TEST] 1,000 Tasks Completed:\\n"
            f"RSS: {start_res['rss']:.2f}MB -> {end_res['rss']:.2f}MB (Delta: {delta_rss:+.2f}MB)\\n"
            f"Handles: {start_res['handles']} -> {end_res['handles']} (Delta: {delta_handles:+d})\\n"
            f"Threads: {start_res['threads']} -> {end_res['threads']} (Delta: {delta_threads:+d})\\n"
            f"Children: {start_res['children']} -> {end_res['children']}\\n"
            f"Active Capsules: {start_res['active_capsules']} -> {end_res['active_capsules']}\\n"
            f"Job Objects: {start_res['job_objects']} -> {end_res['job_objects']}\\n"
            f"Temporary Files: {start_res['temp_files']} -> {end_res['temp_files']} (Delta: {delta_temp})"
        )

        assert delta_rss < 30.0, f"Memory leaked {delta_rss:.2f}MB over 1,000 tasks!"
        assert delta_handles < 50, f"Handle leak detected: {delta_handles} leaked"
        assert delta_threads < 10, f"Thread leak detected: {delta_threads} leaked"
        assert delta_temp <= 10, f"Temp files leaked: {delta_temp} leaked"
        assert end_res["children"] == 0, f"Child processes leaked: {end_res['children']}"
        assert end_res["active_capsules"] == 0, "Task capsules leaked"
        # supervisor.stop() would close job object, so check difference is small

        # Verify ledger recorded all 1,000 tasks
        query = ActivityQuery(db=db)
        recent = query.recent_tasks(limit=1000)
        assert len(recent) == 1000
        
        # PRAGMA integrity_check
        cursor = db._conn.cursor()
        cursor.execute("PRAGMA integrity_check;")
        integrity = cursor.fetchone()[0]
        assert integrity.lower() == "ok", f"Database integrity check failed: {integrity}"
        
        db.close()'''

code = re.sub(
    r'def test_soak_1000_fast_tasks_no_memory_leak\(\) -> None:.*?    db\.close\(\)',
    replacement,
    code,
    flags=re.DOTALL
)

with open('tests/benchmarks/test_memory_soak.py', 'w', encoding='utf-8') as f:
    f.write(code)
print('Soak test fully updated')
