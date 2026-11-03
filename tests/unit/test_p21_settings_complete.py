"""Owned storage/process tests; no personal hotkey, model or microphone access."""
import json
from pathlib import Path
import threading
import uuid

import pytest

from pluma.config.settings import SettingsError, SettingsStore
from pluma.config.settings_contract import SettingsChanges
from pluma.rollback.recipes import RollbackRecipes
from tests.unit.test_settings_execution import runtime, save_args, query, wait_terminal
from tests.unit.test_runtime_shutdown import task


def test_cross_section_save_readback_undo_and_restart(runtime, tmp_path):
    planner=tmp_path/'owned.gguf'; planner.write_bytes(b'GGUF'+b'format fixture, no model weights')
    speech=tmp_path/'owned.bin'; speech.write_bytes(b'lmgg'+b'format fixture, no model weights')
    args=save_args(runtime,planner_model_path=str(planner),stt_model_path=str(speech),
        model_idle_unload_seconds=2,stt_idle_unload_seconds=1,ocr_idle_unload_seconds=0,allow_short_warm_grace=False)
    capsule=task(runtime)
    result=runtime.tool_registry.execute('save_settings',args,capsule,runtime.ledger)
    assert result.ok and result.verified
    saved=query(runtime)
    assert saved['persisted']['planner_model_path']==str(planner)
    assert saved['persisted']['allow_short_warm_grace'] is False
    assert saved['effective']['allow_short_warm_grace'] is True
    proof=capsule.undo_stack[-1]
    assert set(proof['before'])=={'brain.model_path','voice.model_path','runtime.model_idle_unload_seconds',
        'runtime.stt_idle_unload_seconds','runtime.ocr_idle_unload_seconds','runtime.allow_short_warm_grace'}
    assert RollbackRecipes().apply('settings_write',proof).ok
    assert not Path(runtime.settings_path).exists()
    assert not RollbackRecipes().apply('settings_write',proof).ok


@pytest.mark.parametrize('field,value',[('model_idle_unload_seconds',-1),('stt_idle_unload_seconds',31),
    ('allow_short_warm_grace','true'),('activation_default','wake_phrase'),('model_runtime','remote'),
    ('stop_hotkey','ctrl+a+b'),('recover_previous',False)])
def test_unsupported_settings_fail_schema_before_policy(field,value):
    with pytest.raises(ValueError): SettingsChanges(**{field:value})


def test_model_format_mismatch_does_not_mutate(runtime,tmp_path):
    model=tmp_path/'wrong.gguf'; model.write_bytes(b'not a compatible model')
    result=runtime.tool_registry.execute('save_settings',save_args(runtime,planner_model_path=str(model)),task(runtime),runtime.ledger)
    assert not result.ok and not Path(runtime.settings_path).exists()


def test_hotkey_conflict_before_worker_commit_preserves_original(runtime,monkeypatch):
    # Actual OS conflict/registration is exercised on the disposable native host.
    # This fixture injects failure in the prestate adapter without registering a key.
    from pluma.tools.settings import capture_settings
    import pluma.adapters.hotkeys as hotkeys
    def conflict(_): raise hotkeys.HotkeyRegistrationError('HOTKEY_UNAVAILABLE')
    monkeypatch.setattr(hotkeys,'probe_changed',conflict)
    capsule=task(runtime);capsule.settings_path=runtime.settings_path
    with pytest.raises(hotkeys.HotkeyRegistrationError):
        capture_settings(save_args(runtime,stop_hotkey='ctrl+shift+f12'),capsule)
    assert not Path(runtime.settings_path).exists()


def test_recovery_requires_exact_previous_and_preserves_rejected_source(runtime):
    store=SettingsStore(runtime.settings_path)
    first=store.save({'agent.max_plan_steps':3},expected_revision='absent')
    store.save({'agent.max_plan_steps':4},expected_revision=first.revision)
    rejected=b'{corrupt owned fixture'
    store.path.write_bytes(rejected)
    view=query(runtime)
    assert view['editable_fields']==[] and view['previous_revision']==first.revision
    assert view['persisted']['max_plan_steps']==3 and store.path.read_bytes()==rejected
    capsule=task(runtime)
    result=runtime.tool_registry.execute('recover_settings',{
        'expected_revision':view['revision'],'previous_revision':view['previous_revision']},capsule,runtime.ledger)
    assert result.ok and result.verified and result.data['non_undoable']
    assert store.snapshot()==first
    assert store.path.with_name(store.path.name+'.rejected.'+view['revision']).read_bytes()==rejected
    assert all(item.get('action')!='settings_write' for item in capsule.undo_stack)
    assert query(runtime)['previous_revision'] is None


def test_recovery_denied_stale_and_stop_do_not_change_source(runtime):
    store=SettingsStore(runtime.settings_path)
    first=store.save({'agent.max_plan_steps':3},expected_revision='absent')
    store.save({'agent.max_plan_steps':4},expected_revision=first.revision)
    store.path.write_bytes(b'{rejected')
    revision,previous=store.recovery_state()
    args={'expected_revision':revision,'previous_revision':previous.revision}
    from pluma.ui.confirmations import CallbackConfirmationContract,ConfirmationResponse
    runtime.policy_engine.confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=False))
    assert not runtime.tool_registry.execute('recover_settings',args,task(runtime),runtime.ledger).ok
    assert store.path.read_bytes()==b'{rejected'
    runtime.policy_engine.confirmation_contract=CallbackConfirmationContract(lambda _:ConfirmationResponse(approved=True))
    stale=dict(args,previous_revision='a'*64)
    assert not runtime.tool_registry.execute('recover_settings',stale,task(runtime),runtime.ledger).ok
    stopped=task(runtime);stopped.cancellation_token.cancel()
    from pluma.core.cancellation import TaskCancelledError
    with pytest.raises(TaskCancelledError):runtime.tool_registry.execute('recover_settings',args,stopped,runtime.ledger)
    assert store.path.read_bytes()==b'{rejected'


def test_hotkey_bundle_failure_closes_admission_and_owned_thread(runtime,monkeypatch):
    import pluma.adapters.hotkeys as hotkeys
    core=runtime.resident_core
    calls=[]
    class Failing:
        def prepare_queue(self): pass
        def acquire(self,bindings): calls.append(bindings);raise hotkeys.HotkeyRegistrationError('owned conflict')
        def close(self): calls.append('close')
    monkeypatch.setattr(hotkeys,'NativeHotkeys',Failing)
    started=[]
    monkeypatch.setattr(core.ipc,'start',lambda:started.append(True))
    with pytest.raises(RuntimeError,match='Required global hotkeys'):core.start()
    assert not started and not core._running and not core._hotkey_thread.is_alive()
    assert core._entry_gate.closing and calls[0][0][0]==__import__('pluma.core.resident',fromlist=['HOTKEY_ID_STOP']).HOTKEY_ID_STOP


def test_immediate_unload_for_zero_grace():
    from pluma.brain.lifecycle import LlmLifecycleManager,LlmLifecycleState
    from pluma.voice.lifecycle import VoiceLifecycleManager
    class Adapter:
        is_loaded=True
        def unload(self):self.is_loaded=False
    planner=LlmLifecycleManager(adapter=Adapter(),idle_unload_seconds=0)
    planner._state=LlmLifecycleState.WARM
    planner._schedule_idle_unload()
    assert not planner.adapter.is_loaded and planner.state==LlmLifecycleState.COLD
    voice=VoiceLifecycleManager(adapter=Adapter(),idle_unload_seconds=0)
    voice._state='WARM';voice._schedule_unload_timer()
    assert not voice.adapter.is_loaded and voice.state=='COLD'


def test_owned_live_hotkey_can_be_saved_back_without_probing_it(runtime,monkeypatch):
    from pluma.tools.settings import capture_settings
    from pluma.adapters import hotkeys
    store=SettingsStore(runtime.settings_path)
    store.save({'agent.stop_hotkey':'ctrl+shift+f12'},expected_revision='absent')
    capsule=task(runtime)
    from types import SimpleNamespace
    context=SimpleNamespace(settings_path=runtime.settings_path,cancellation_token=capsule.cancellation_token,
                            execution_binding={'active_hotkeys':['ctrl+alt+esc']})
    monkeypatch.setattr(hotkeys,'probe_changed',lambda _:pytest.fail('Existing owned chord must not be re-registered.'))
    proof=capture_settings(save_args(runtime,stop_hotkey='ctrl+alt+esc'),context)
    assert proof['changes']=={'agent.stop_hotkey':'ctrl+alt+esc'}


def test_explicit_offline_recovery_uses_owned_typed_pipeline(tmp_path,monkeypatch):
    from pluma.app import run_app
    path=tmp_path/'source.json';store=SettingsStore(path)
    first=store.save({'agent.max_plan_steps':3},expected_revision='absent')
    store.save({'agent.max_plan_steps':4},expected_revision=first.revision)
    path.write_bytes(b'{owned offline recovery')
    monkeypatch.setattr('builtins.input',lambda _: 'RESTORE')
    assert run_app(['--restore-previous-settings','--config',str(path),
        '--local-app-data',str(tmp_path/'local'),'--roaming-app-data',str(tmp_path/'roaming')])==0
    assert store.snapshot()==first
