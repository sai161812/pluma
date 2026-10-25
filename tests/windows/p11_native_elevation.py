"""Explicit P11 native UAC acceptance. Never collected by ordinary pytest runs.

Run with: python -m tests.windows.p11_native_elevation --run-dns-flush
This requests one real local DNS-cache flush through the production registry.
"""
import argparse
import json
import os
from pathlib import Path
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dns-flush", action="store_true", required=True)
    parser.parse_args()
    root = Path("output") / ("p11-e58-uac-" + uuid.uuid4().hex)
    root.mkdir(parents=True)
    for name in ("LOCALAPPDATA", "APPDATA", "TEMP", "TMP"):
        path = (root / name.lower()).resolve()
        path.mkdir()
        os.environ[name] = str(path)
    for name in tuple(os.environ):
        if name.startswith("PLUMA_"):
            os.environ.pop(name)
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.paths import PlumaPaths
    from pluma.memory.activity import ActivityQuery, TaskRecord
    from pluma.core.task_supervisor import TaskState

    paths = PlumaPaths((root / "local").resolve(), (root / "roaming").resolve())
    paths.ensure_directories()
    runtime = PlumaApplicationRuntime(paths, config={"voice": {"required": False}})
    report = {}
    try:
        cap = runtime.supervisor.create_task("p11-native-uac-acceptance")
        runtime.ledger.insert_task(TaskRecord(task_id=cap.task_id, request_id=cap.request_id,
            input_mode="text", command_text="P11 fixed DNS-cache operation acceptance"))
        runtime.supervisor.start_task(cap.task_id)
        result = runtime.tool_registry.execute("flush_dns_cache", {}, cap, runtime.ledger)
        row = ActivityQuery(runtime.db).actions_for_task(cap.task_id)[0]
        report.update(result=result.model_dump(mode="json", exclude={"private_context"}),
            ledger={"risk": row["risk"], "approval_state": row["approval_state"],
                "verified": row["verified"]}, task_id=cap.task_id)
        runtime.supervisor.finalize_task(cap.task_id,
            TaskState.SUCCEEDED if result.ok and result.verified else TaskState.FAILED)
    finally:
        closed = runtime.close(5)
        report["runtime_closed"] = closed.complete
        report["runtime_close_code"] = closed.code
        (root / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report))
    return 0 if report["result"]["ok"] and report["result"]["verified"] and report["runtime_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
