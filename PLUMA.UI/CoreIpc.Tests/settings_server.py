"""Actual settings graph in a private fixture root; no desktop or ML activation."""
def run(address, root, mode):
    import os
    import sys
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.paths import PlumaPaths

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
    server = runtime.resident_core.ipc
    server.address = "\\\\.\\pipe\\" + address
    try:
        server.start()
        if mode == "settings_ui":
            # Only the IPC readiness marker is required by this shell fixture.
            # Never start resident hotkeys or the microphone on the test desktop.
            runtime.resident_core._running = True
        print("READY", flush=True)
        for line in sys.stdin:
            if line.strip() == "stop":
                break
            if mode == "settings_ui" and line.strip() == "settings_external_limit_6":
                from pluma.config.settings import SettingsStore
                store = SettingsStore(paths.user_settings_path)
                store.save({"agent.max_plan_steps": 6}, expected_revision=store.snapshot().revision)
                print("SETTINGS_EXTERNAL_LIMIT_6", flush=True)
    finally:
        server.stop()
        if not runtime.close(5).complete:
            raise RuntimeError("Owned settings graph did not close.")
        if runtime.tool_registry._worker_controllers or runtime.db.is_open:
            raise RuntimeError("Settings fixture ownership/storage remains open.")
