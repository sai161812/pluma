"""Explicit owned native setup/host check. No samples/screenshots are retained."""
import argparse,json,os,sys,time,uuid
from pathlib import Path


def run(args):
    root=args.report.parent/('owned-host-'+uuid.uuid4().hex);root.mkdir(exist_ok=False)
    for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):
        path=root/key;path.mkdir();os.environ[key]=str(path)
    for key in list(os.environ):
        if key.startswith('PLUMA_'):del os.environ[key]
    from pluma.core.host import CoreHost
    from pluma.config.paths import PlumaPaths
    paths=PlumaPaths(root/'local',root/'roaming');paths.ensure_directories()
    paths.user_settings_path.write_text(json.dumps({'agent':{'text_hotkey':'ctrl+alt+shift+f7','stop_hotkey':'ctrl+alt+shift+f8','voice_hotkey':'ctrl+alt+shift+f9'},
        'brain':{'model_path':str(args.model.resolve())},'voice':{'model_path':str(args.speech.resolve())}}),encoding='utf-8')
    host=CoreHost(paths,config_path=str(paths.user_settings_path),address='\\\\.\\pipe\\p22-native-'+uuid.uuid4().hex)
    try:
        host.start()
        assert host.state=='READY'
        assert host.runtime.llm_lifecycle.state.value==host.runtime.voice_lifecycle.state=='COLD'
        ack=host.handle({'protocol_version':1,'message_type':'setup_check','request_id':str(uuid.uuid4()),
            'instance_id':host.instance_id,'include_microphone':True})
        assert ack.get('accepted'),ack
        end=time.monotonic()+35
        while time.monotonic()<end:
            cap=host.runtime.supervisor.get_task(ack['task_id'])
            if cap.terminal_ready.is_set():break
            time.sleep(.02)
        assert cap.terminal_ready.is_set() and cap.state.value=='SUCCEEDED'
        view=host.health(str(uuid.uuid4()))
        assert view['native_verified'] and len(view['checks'])==5
        assert view['setup_ready'] and all(c['state']=='PASSED' for c in view['checks'])
        assert view['hotkeys_registered']
        assert host.runtime.llm_lifecycle.state.value==host.runtime.voice_lifecycle.state=='COLD'
        assert not host.runtime.tool_registry._worker_controllers
        assert 'llama_cpp' not in sys.modules and 'onnxruntime' not in sys.modules and 'pywhispercpp.model' not in sys.modules
        report={'commit':__import__('subprocess').check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'native_checks':view['checks'],'setup_ready':view['setup_ready'],'worker_absence_verified':True,
            'resident_models_cold':True,'audio_saved':False,'screenshot_saved':False,'owned_root':str(root)}
        with args.report.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
        print(json.dumps(report))
    finally:
        end=time.monotonic()+5
        while not host.close() and time.monotonic()<end:time.sleep(.02)
        assert host.state=='STOPPED'


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--speech',type=Path,required=True);parser.add_argument('--report',type=Path,required=True)
    run(parser.parse_args())
