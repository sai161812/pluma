"""Actual settings graph in a private fixture root; no desktop or ML activation."""
def run(address, root, mode):
    import os
    import sys
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.paths import PlumaPaths
    from pluma.core.ipc import IpcServer

    paths = PlumaPaths(root / "p21-owned" / "local", root / "p21-owned" / "roaming")
    paths.ensure_directories()
    if paths.user_settings_path.exists() != (mode == "settings_restart"):
        raise RuntimeError("Owned settings fixture precondition changed.")
    os.environ["PLUMA_CONFIG"] = str(paths.user_settings_path)
    runtime = PlumaApplicationRuntime(paths)
    expected = 4 if mode == "settings_restart" else 8
    if (runtime.llm_lifecycle.adapter.max_plan_steps != expected
            or runtime.llm_lifecycle.state.value != "COLD" or runtime.voice_lifecycle.state != "COLD"):
        raise RuntimeError("Actual settings application/cold lifecycle readback disagrees.")
    server = IpcServer(address=address, handler=runtime.resident_core.handle_ipc_command)
    try:
        server.start()
        print("READY", flush=True)
        for line in sys.stdin:
            if line.strip() == "stop":
                break
    finally:
        server.stop()
        if not runtime.close(5).complete:
            raise RuntimeError("Owned settings graph did not close.")
        if runtime.tool_registry._worker_controllers or runtime.db.is_open:
            raise RuntimeError("Settings fixture ownership/storage remains open.")
