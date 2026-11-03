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
            if mode == "settings_ui" and line.strip() == "settings_prepare_models":
                (root / "planner.gguf").write_bytes(b"GGUF" + b"format fixture; not native weights")
                (root / "speech.bin").write_bytes(b"lmgg" + b"format fixture; not native weights")
                print("SETTINGS_PREPARE_MODELS", flush=True)
            if mode == "settings_ui" and line.strip() == "settings_corrupt":
                paths.user_settings_path.write_bytes(b"{owned rejected source")
                print("SETTINGS_CORRUPT", flush=True)
            if mode == "settings_ui" and line.strip() == "settings_assert_advanced_restart":
                restarted=PlumaApplicationRuntime(paths,settings_path=str(paths.user_settings_path))
                try:
                    assert restarted.llm_lifecycle.adapter.model_path==str(root/"planner.gguf")
                    assert restarted.voice_lifecycle.model_path==str(root/"speech.bin")
                    assert restarted.llm_lifecycle.idle_unload_seconds==restarted.voice_lifecycle.idle_unload_seconds==0
                    assert restarted.resident_core.voice_activation.hotkey=="ctrl+alt+v"
                    assert restarted.llm_lifecycle.state.value==restarted.voice_lifecycle.state=="COLD"
                finally:
                    assert restarted.close(5).complete
                print("SETTINGS_ASSERT_ADVANCED_RESTART", flush=True)
            if mode == "settings_ui" and line.strip() == "settings_assert_recovered":
                from pluma.config.settings import SettingsStore
                store=SettingsStore(paths.user_settings_path)
                assert store.snapshot().overrides["agent"]["max_plan_steps"] == 6
                assert any(item.read_bytes()==b"{owned rejected source" for item in store.path.parent.glob(store.path.name+".rejected.*"))
                print("SETTINGS_ASSERT_RECOVERED", flush=True)
            if mode == "settings_ui" and line.strip() == "settings_native_hotkeys":
                native_hotkeys(root, address)
                print("SETTINGS_NATIVE_HOTKEYS", flush=True)
    finally:
        server.stop()
        unchanged = (runtime.llm_lifecycle.adapter.max_plan_steps == expected
                     and runtime.llm_lifecycle.state.value == "COLD" and runtime.voice_lifecycle.state == "COLD")
        if not runtime.close(5).complete:
            raise RuntimeError("Owned settings graph did not close.")
        if runtime.tool_registry._worker_controllers or runtime.db.is_open:
            raise RuntimeError("Settings fixture ownership/storage remains open.")
        if not unchanged:
            raise RuntimeError("Settings edits changed active or cold runtime state before restart.")


def native_hotkeys(root, address):
    """Disposable CI desktop only: no SendInput, user key changes or window cleanup."""
    import os
    import ctypes
    import time
    from pluma.adapters.hotkeys import NativeHotkeys, HotkeyRegistrationError, probe_changed
    from pluma.app import PlumaApplicationRuntime
    from pluma.config.paths import PlumaPaths
    from pluma.config.loader import load_config
    from pluma.core.resident import HOTKEY_ID_STOP
    from pluma.memory.activity import TaskRecord
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Native hotkey acceptance requires the disposable CI desktop.")
    chord="ctrl+alt+shift+f11"
    owner=NativeHotkeys()
    try:
        owner.acquire([(0x3B00,chord)])
        try:
            probe_changed(["ctrl+alt+shift+f12",chord])
        except HotkeyRegistrationError:
            pass
        else:
            raise AssertionError("Occupied owned chord was accepted.")
        # A failed bundle released its new STOP candidate but not the first owner's key.
        probe_changed(["ctrl+alt+shift+f12"])
        try:
            probe_changed([chord])
        except HotkeyRegistrationError:
            pass
        else:
            raise AssertionError("Another owner's registration was released.")
    finally:
        owner.close()
    probe_changed([chord])
    paths=PlumaPaths(root/"native-hotkey-local",root/"native-hotkey-roaming")
    paths.ensure_directories()
    cfg=load_config(root/"absent-native-hotkeys.json")
    cfg["agent"].update(text_hotkey="ctrl+alt+shift+f10",stop_hotkey="ctrl+alt+shift+f11",voice_hotkey="ctrl+alt+shift+f12")
    runtime=PlumaApplicationRuntime(paths,config=cfg,settings_path=str(paths.user_settings_path))
    runtime.resident_core.ipc.address="\\\\.\\pipe\\"+address+"-hotkeys"
    try:
        runtime.resident_core.start()
        assert runtime.resident_core._hotkey_ready.is_set() and runtime.resident_core._hotkey_error is None
        import uuid
        snapshot=runtime.resident_core.handle_ipc_command({"protocol_version":1,"message_type":"settings_edit_query","request_id":str(uuid.uuid4())})
        assert snapshot["hotkeys_registered"] is True
        capsule=runtime.supervisor.create_task("owned hotkey STOP fixture")
        runtime.ledger.insert_task(TaskRecord(task_id=capsule.task_id,request_id=capsule.request_id,input_mode="text",command_text="Owned hotkey STOP fixture"))
        runtime.supervisor.start_task(capsule.task_id)
        assert ctypes.WinDLL("user32").PostThreadMessageW(runtime.resident_core._hotkey_thread.native_id,0x0312,HOTKEY_ID_STOP,0)
        end=time.monotonic()+2
        while not capsule.cancellation_token.is_cancelled and time.monotonic()<end:
            time.sleep(.01)
        assert capsule.cancellation_token.is_cancelled
    finally:
        assert runtime.close(5).complete
    assert not runtime.resident_core._hotkey_thread.is_alive()
    probe_changed(list(cfg["agent"][key] for key in ("text_hotkey","stop_hotkey","voice_hotkey")))
