using PLUMA.UI;

internal static class SettingsControllerChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static CoreRequestResult<T> Ok<T>(T value) where T : class => new(value, CoreConnectionFailure.None, false, null, null);
    private static CoreRequestProtocol.SettingsEditSnapshot Snapshot(int saved=8, int effective=8) =>
        new(1, "settings_edit_snapshot", Id(), new string(saved == 8 ? 'a' : 'b',64),
            new("alt+space","ctrl+alt+esc","ctrl+alt+v",saved),
            new("alt+space","ctrl+alt+esc","ctrl+alt+v",effective),
            saved == effective ? [] : ["max_plan_steps"], ["max_plan_steps"]);
    private static CoreRequestProtocol.SettingsSnapshot Runtime(string id) => new(
        ProtocolVersion:1, MessageType:"settings_snapshot", RequestId:id,
        TextHotkey:"alt+space", StopHotkey:"ctrl+alt+esc", VoiceHotkey:"ctrl+alt+v",
        MaxPlanSteps:8, DefaultToolTimeoutSeconds:15, ModelIdleUnloadSeconds:30,
        SttIdleUnloadSeconds:20, OcrIdleUnloadSeconds:10, AllowShortWarmGrace:true,
        VoiceRequired:true, ActivationDefault:"push_to_talk", WakePhraseEnabled:false, SaveAudio:false,
        PersistScreenshots:false, OcrEnabled:true, UiaFirst:true, ModelRuntime:"llama_cpp", ModelProfile:"fixture",
        PlannerModelPath:@"C:\fixture\模型.gguf", SttModelPath:@"C:\fixture\speech.bin", ConfirmHighRisk:true,
        RedactSensitiveLogs:true, ActivityViewEnabled:true, SubmissionStopFence:true);

    internal static async Task RunAsync(Action<bool,string> check)
    {
        var backend = new Client();
        await using var command = new CommandController(backend, TimeSpan.FromMilliseconds(1));
        var saved = Snapshot(); bool unavailable = false;
        await using var settings = new SettingsController((id, token) => Task.FromResult(unavailable
            ? CoreRequestResult<CoreRequestProtocol.SettingsEditSnapshot>.Failed(CoreConnectionFailure.Unavailable)
            : Ok(saved with { RequestId=id })), (id, token) => Task.FromResult(Ok(Runtime(id))), command);
        command.Changed += settings.OnCommandChanged;
        await settings.RefreshAsync(default);
        check(settings.View.Connected && settings.View.DraftLimit==8 && !settings.View.CanSave,
            "settings uses actual readback instead of preview selections");
        settings.SetDraft(4); check(settings.View.CanSave && settings.View.CanCancel, "valid settings draft enables explicit Save and Cancel");
        settings.CancelEdits();
        check(settings.View.DraftLimit==8 && backend.Saves==0, "Cancel discards a draft without any mutation request");
        foreach (double invalid in new[] {double.NaN, double.PositiveInfinity, 0, 21, 3.5})
        {
            settings.SetDraft(invalid); await settings.SaveAsync(default);
            check(!settings.View.CanSave && backend.Saves==0, "invalid settings draft never reaches command admission");
        }
        settings.CancelEdits(); settings.SetDraft(4);
        backend.AfterSubmit = () => saved=Snapshot(4);
        await settings.SaveAsync(default);
        check(backend.Saves==1 && backend.Revision==new string('a',64) && backend.Limit==4 && command.View.State=="Completed",
            "settings Save uses one exact revision and the shared typed command lifecycle");
        check(settings.View.Saved!.Persisted.MaxPlanSteps==4 && settings.View.Saved.Effective.MaxPlanSteps==8 &&
            !settings.View.CanSave && settings.View.Message.Contains("restart",StringComparison.OrdinalIgnoreCase),
            "saved settings are read back and restart status never pretends immediate application");
        settings.SetDraft(6); saved=Snapshot(5); await settings.RefreshAsync(default);
        check(settings.View.DraftLimit==5 && backend.Saves==1, "explicit reload replaces a stale draft with current persisted values");
        unavailable=true; await settings.RefreshAsync(default);
        check(!settings.View.Connected && settings.View.Saved is null && settings.View.Runtime is null && !settings.View.CanSave,
            "lost settings storage clears stale controls without fake defaults");
        command.Changed -= settings.OnCommandChanged;

        var unknownBackend = new Client { Unknown=true, HistoryAvailable=false };
        await using var unknownCommand = new CommandController(unknownBackend);
        await using var unknown = new SettingsController((id,t)=>Task.FromResult(Ok(Snapshot() with {RequestId=id})),
            (id,t)=>Task.FromResult(Ok(Runtime(id))), unknownCommand);
        await unknown.RefreshAsync(default); unknown.SetDraft(4); await unknown.SaveAsync(default);
        await unknown.RefreshAsync(default); await unknown.SaveAsync(default);
        check(unknownBackend.Saves==1 && unknownCommand.View.Pending && !unknown.View.CanSave,
            "unknown settings write is reconciled read-only and never replayed");

        using var entered=new SemaphoreSlim(0);
        await using var blockedCommand = new CommandController(new Client());
        var blocked = new SettingsController(async (id,t)=>{entered.Release(); await Task.Delay(Timeout.Infinite,t); throw new Exception();},
            (id,t)=>Task.FromResult(Ok(Runtime(id))), blockedCommand);
        Task pending=blocked.RefreshAsync(default); await entered.WaitAsync();
        await blocked.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(1)); await pending;
        check(!blocked.View.CanSave, "disposing settings cancels and joins its owned read");

        using var submitted = new SemaphoreSlim(0);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var pressure = new Client { Gate=release.Task, Entered=submitted };
        await using var priorityCommand=new CommandController(pressure);
        await using var prioritySettings=new SettingsController((id,t)=>Task.FromResult(Ok(Snapshot() with {RequestId=id})),
            (id,t)=>Task.FromResult(Ok(Runtime(id))), priorityCommand);
        await prioritySettings.RefreshAsync(default); prioritySettings.SetDraft(4);
        Task save=prioritySettings.SaveAsync(default); await submitted.WaitAsync();
        await prioritySettings.SaveAsync(default);
        await priorityCommand.StopAsync().WaitAsync(TimeSpan.FromSeconds(1));
        release.TrySetResult(); await save;
        check(pressure.Stops==1 && pressure.Saves==1 && pressure.Fence==pressure.Request,
            "priority STOP fences one pending settings submission independently of the view operation");

        var queuedSource = new Client();
        await using var queuedCommand = new CommandController(queuedSource);
        await using var queuedSettings = new SettingsController((id,t)=>Task.FromResult(Ok(Snapshot() with {RequestId=id})),
            (id,t)=>Task.FromResult(Ok(Runtime(id))), queuedCommand);
        await queuedSettings.RefreshAsync(default); queuedSettings.SetDraft(4);
        var hold = new HeldContext();
        var oldContext = SynchronizationContext.Current;
        Task queued, stopped; string? queuedId;
        try
        {
            SynchronizationContext.SetSynchronizationContext(hold);
            queued=queuedSettings.SaveAsync(default); queuedId=queuedCommand.View.RequestId;
            stopped=queuedCommand.StopAsync();
        }
        finally { SynchronizationContext.SetSynchronizationContext(oldContext); }
        await stopped; hold.Drain(); await queued;
        check(queuedId is not null && queuedSource.Fence==queuedId && queuedSource.Saves==0,
            "STOP before the first settings UI await prevents late submission and preserves its exact fence");

        var extendedSource=new Client();
        await using var extendedCommand=new CommandController(extendedSource);
        var extendedSnapshot=Snapshot() with {EditableFields=CoreRequestProtocol.SettingKeys};
        await using var extended=new SettingsController((id,t)=>Task.FromResult(Ok(extendedSnapshot with {RequestId=id})),
            (id,t)=>Task.FromResult(Ok(Runtime(id))),extendedCommand);
        await extended.RefreshAsync(default);
        extended.SetValues(extended.View.DraftValues! with {ModelIdleUnloadSeconds=2,AllowShortWarmGrace=false,StopHotkey="ctrl+shift+f11"});
        check(extended.View.CanSave,"supported hotkey and grace edits enable one shared Save");
        extendedSource.AfterSubmit=()=>extendedSnapshot=extendedSnapshot with {Persisted=extended.View.DraftValues!};
        await extended.SaveAsync(default);
        check(extendedSource.Edits!.Fields().Keys.Order().SequenceEqual(new[]{"allow_short_warm_grace","model_idle_unload_seconds","stop_hotkey"}),
            "extended Settings Save sends only actual changed fields without rewriting unrelated configuration");
        extendedSnapshot=extendedSnapshot with {EditableFields=[],PreviousRevision=new string('c',64)};
        await extended.RefreshAsync(default);
        check(!extended.View.CanEdit && !extended.View.CanSave && extended.View.CanRecover,
            "recovery snapshot blocks normal edits and offers only exact previous-source restoration");
        extendedSource.AfterSubmit=()=>extendedSnapshot=extendedSnapshot with {EditableFields=CoreRequestProtocol.SettingKeys,PreviousRevision=null};
        await extended.RecoverAsync(default);
        check(extendedSource.Edits is {RecoverPrevious:true,RecoveryRevision:not null} && !extended.View.CanRecover,
            "settings recovery uses the shared typed submission with exact previous revision and verified readback");
    }

    private sealed class Client : ICommandClient
    {
        internal int Saves, Stops, Limit;
        internal CoreRequestProtocol.SettingsEdits? Edits;
        internal string? Revision, Request, Fence;
        internal readonly string TaskId=Id();
        internal bool Unknown, HistoryAvailable=true;
        internal Action? AfterSubmit;
        internal Task? Gate;
        internal SemaphoreSlim? Entered;
        public Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request,string text,CancellationToken token) =>
            throw new InvalidOperationException("Settings must not be submitted as natural language.");
        public async Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitSettingsAsync(string request,string revision,
            CoreRequestProtocol.SettingsEdits edits,CancellationToken token)
        {
            Saves++; Request=request; Revision=revision; Edits=edits; Limit=edits.MaxPlanSteps ?? 8; Entered?.Release();
            if(Gate is not null) await Gate.WaitAsync(token);
            AfterSubmit?.Invoke();
            return Unknown ? CoreRequestResult<CoreRequestProtocol.SubmissionAck>.Failed(CoreConnectionFailure.Timeout,true)
                : Ok(new CoreRequestProtocol.SubmissionAck(1,"submission_ack",request,true,TaskId,null,"Owned fixture"));
        }
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request,string task,CancellationToken token) =>
            Task.FromResult(Ok(new CoreRequestProtocol.TerminalReadback(1,"terminal_readback",request,task,true,"SUCCEEDED",true,true,false,"FAST","Owned fixture",1)));
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request,CancellationToken token) =>
            Task.FromResult(Ok(new CoreRequestProtocol.HistoryReply(1,"history_reply",request,null,
                HistoryAvailable ? [new(TaskId,Request!,"text","Owned fixture",DateTimeOffset.UtcNow.ToString("O"),null,null,null,null,null,null)] : [],[])));
        public Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request,string? submissionRequest,CancellationToken token)
        {
            Stops++; Fence=submissionRequest;
            return Task.FromResult(Ok(new CoreRequestProtocol.StopAck(1,"stop_ack",request,"ok","pluma.stop.v1","Latch acknowledged",null,[],[],0,1)));
        }
    }

    private sealed class HeldContext : SynchronizationContext
    {
        private readonly System.Collections.Concurrent.ConcurrentQueue<(SendOrPostCallback,object?)> _callbacks = new();
        public override void Post(SendOrPostCallback callback, object? state) => _callbacks.Enqueue((callback,state));
        internal void Drain() { while (_callbacks.TryDequeue(out var item)) item.Item1(item.Item2); }
    }
}
