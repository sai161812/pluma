"""Persisted settings -> owned restart -> actual model use; no microphone/hotkeys.

Run separately with the declared planner and speech environments. Existing model
files are read-only inputs. All writes and reports use a newly allocated root.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave


def run(args):
    from pluma.app import PlumaApplicationRuntime
    from pluma.brain.schemas import Plan, RouteMode, ToolCall
    from pluma.config.paths import PlumaPaths
    from pluma.config.settings import SettingsStore
    from pluma.core.request import PlumaRequest, InputMode
    from pluma.ui.confirmations import CallbackConfirmationContract, ConfirmationResponse
    root=args.report.parent/('native-'+args.kind+'-'+uuid.uuid4().hex)
    root.mkdir(parents=True,exist_ok=False)
    paths=PlumaPaths(root/'local',root/'roaming');paths.ensure_directories()
    directory=root/'files';directory.mkdir();(directory/'fixture.txt').write_text('Owned native settings fixture.',encoding='utf-8')
    model=args.model.resolve(strict=True)
    with model.open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    reports=[]
    for allow in (True,False):
        runtime=PlumaApplicationRuntime(paths,settings_path=str(paths.user_settings_path),
            confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=True)))
        try:
            changes={'planner_model_path' if args.kind=='planner' else 'stt_model_path':str(model),
                'allow_short_warm_grace':allow,'model_idle_unload_seconds':2,'stt_idle_unload_seconds':2}
            request=PlumaRequest(input_mode=InputMode.TEXT,text='Save owned native acceptance settings.')
            capsule=runtime.supervisor.create_task_capsule(request_id=request.request_id)
            result=runtime.orchestrator.execute_typed_plan(request,capsule,Plan(task_id=capsule.task_id,route=RouteMode.FAST,
                steps=[ToolCall(tool='save_settings',arguments={'expected_revision':SettingsStore(paths.user_settings_path).snapshot().revision,
                    'changes':changes},purpose='Save selected fixture settings.')]))
            assert result.success and result.completion_verified and result.terminal_persisted
        finally:
            assert runtime.close(5).complete
        restarted=PlumaApplicationRuntime(paths,settings_path=str(paths.user_settings_path))
        try:
            assert restarted.llm_lifecycle.state.value==restarted.voice_lifecycle.state=='COLD'
            lifecycle=restarted.llm_lifecycle if args.kind=='planner' else restarted.voice_lifecycle
            assert lifecycle.idle_unload_seconds==(2 if allow else 0)
            assert Path(lifecycle.adapter.model_path if args.kind=='planner' else lifecycle.model_path)==model
            start=time.monotonic()
            if args.kind=='planner':
                from tests.windows.p13_native_runtime_acceptance import _planner_task
                task_id=_planner_task(restarted,directory,'P21 saved native path')
            else:
                with wave.open(str(args.sample),'rb') as source:
                    assert (source.getframerate(),source.getsampwidth(),source.getnchannels())==(16000,2,1)
                    audio=source.readframes(source.getnframes())
                capsule=restarted.supervisor.create_task_capsule(history_expected=False)
                transcript=restarted.voice_lifecycle.transcribe(audio,cancellation_token=capsule.cancellation_token)
                assert transcript.text.strip() and not transcript.is_low_confidence
                controller=capsule.worker_controller
                assert controller is not None and controller.worker_identity
                restarted.supervisor.stop_task(capsule.task_id,grace_s=0)
                assert controller.verify_cleanup() is True
                task_id=capsule.task_id
                audio=b''
            assert lifecycle.state.value=='COLD' if args.kind=='planner' else lifecycle.state=='COLD'
            assert not lifecycle.adapter.is_loaded and not restarted.tool_registry._worker_controllers
            assert 'llama_cpp' not in sys.modules and 'pywhispercpp.model' not in sys.modules
            reports.append({'allow_short_warm_grace':allow,'configured_upper_bound_seconds':2,
                'effective_manager_upper_bound_seconds':lifecycle.idle_unload_seconds,'native_weights_retained_after_task':False,
                'elapsed_seconds':round(time.monotonic()-start,3),'task_id':task_id,'owned_worker_absence_verified':True,
                'startup_cold':True,'returned_cold':True,'persisted_settings_restart_readback':True})
        finally:
            assert restarted.close(5).complete
    report={'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'kind':args.kind,
        'model_sha256':digest,'model_bytes':model.stat().st_size,'isolated_root':str(root),'cycles':reports,
        'microphone_opened':False,'raw_audio_saved':False,'native_warm_cache_enabled':False}
    with args.report.open('x',encoding='utf-8') as stream:json.dump(report,stream,indent=2)
    print(json.dumps(report))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--kind',choices=['planner','speech'],required=True)
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--sample',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    run(parser.parse_args())
