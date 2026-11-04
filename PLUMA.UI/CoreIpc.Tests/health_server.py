"""Execution-authorized native host fixture with private files and owned keys."""
def run(address,root):
    import contextlib,json,sys,threading,time,os
    from pluma.core.host import CoreHost
    from pluma.config.paths import PlumaPaths
    paths=PlumaPaths(root/"health-local",root/"health-roaming");paths.ensure_directories()
    # This is the explicit missing-model native scenario. Do not depend on
    # whether another acceptance suite provisioned OCR in the runner's cache.
    os.environ['PADDLEX_HOME']=str(root/'missing-ocr-models')
    source=paths.user_settings_path
    source.write_text(json.dumps({"agent":{"text_hotkey":"ctrl+alt+shift+f4","stop_hotkey":"ctrl+alt+shift+f5","voice_hotkey":"ctrl+alt+shift+f6"}}),encoding="utf-8")
    host=CoreHost(paths,config_path=str(source),address="\\\\.\\pipe\\"+address)
    stopped=threading.Event()
    errors=[]
    def loop():
        try:
            while not stopped.wait(.02):
                with contextlib.redirect_stdout(sys.stderr):host.advance()
        except BaseException as error:errors.append(type(error).__name__)
    with contextlib.redirect_stdout(sys.stderr):host.start()
    owner=threading.Thread(target=loop,name="OwnedFixtureHostLoop",daemon=True);owner.start()
    if os.environ.get('GITHUB_ACTIONS')=='true':
        import faulthandler
        faulthandler.cancel_dump_traceback_later()
    print("READY",flush=True)
    try:
        for line in sys.stdin:
            command=line.strip()
            if command=="stop":break
            if command=="health_corrupt":source.write_bytes(b"{owned invalid health configuration")
            elif command=="health_repair":source.write_text(json.dumps({"agent":{"text_hotkey":"ctrl+alt+shift+f4","stop_hotkey":"ctrl+alt+shift+f5","voice_hotkey":"ctrl+alt+shift+f6"}}),encoding="utf-8")
            elif command=="health_disconnect":host.server.stop()
            else:raise ValueError("Unknown fixture command.")
            print(command.upper(),flush=True)
    finally:
        stopped.set();owner.join(5)
        assert not owner.is_alive() and not errors
        end=time.monotonic()+5
        while not host.close() and time.monotonic()<end:time.sleep(.02)
        assert host.state=="STOPPED" and not host.runtime.db.is_open
