using System;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal sealed record HealthView(CoreHealthProtocol.Snapshot? Snapshot,bool Busy,string Message,bool CanCheck,bool CanRestart,bool CanContinue);

/// <summary>Explicit bounded reads/checks/recovery; no new background poller.</summary>
internal sealed class HealthController(Func<string,CancellationToken,Task<CoreRequestResult<CoreHealthProtocol.Snapshot>>> read,
    CommandController commands):IAsyncDisposable
{
    private readonly CancellationTokenSource _life=new();
    private Task _work=Task.CompletedTask;
    private bool _closed,_busy;
    private CoreHealthProtocol.Snapshot? _snapshot;
    private string _message="Setup has not been checked.";
    private DateTimeOffset _readAt;
    internal event Action<HealthView>? Changed;
    internal HealthView View=>new(_snapshot,_busy,_message,
        !_closed&&!_busy&&!commands.View.Pending&&_snapshot?.State=="READY"&&commands.View.CanSubmit,
        !_closed&&!_busy&&!commands.View.Pending&&_snapshot?.CanRestart==true,
        !_closed&&!_busy&&!commands.View.Pending&&_snapshot is {SetupReady:true,NativeVerified:true,State:"READY"}&&DateTimeOffset.UtcNow-_readAt<TimeSpan.FromSeconds(45));
    private void Publish(){if(!_closed)Changed?.Invoke(View);}
    private Task Run(Func<Task> operation)
    {
        if(_closed||_busy||!_work.IsCompleted)return _work;
        _busy=true;_work=Execute(operation);Publish();return _work;
    }
    private async Task Execute(Func<Task> operation)
    {
        await Task.Yield();
        try{await operation();}
        catch(Exception){_snapshot=null;_message="Core health is unavailable. No recovery was verified.";}
        finally{_busy=false;Publish();}
    }
    private static string Id()=>Guid.NewGuid().ToString("D");
    private async Task Read(CancellationToken owner)
    {
        using var bounded=CancellationTokenSource.CreateLinkedTokenSource(owner,_life.Token);
        bounded.CancelAfter(TimeSpan.FromSeconds(3));
        var value=await read(Id(),bounded.Token);
        for(int i=0;value.Failure==CoreConnectionFailure.Busy&&i<4;i++)
        {await Task.Delay(50,bounded.Token);value=await read(Id(),bounded.Token);}
        if(!value.IsSuccess)throw new InvalidOperationException();
        _snapshot=value.Response!;_readAt=DateTimeOffset.UtcNow;
        commands.SetCoreReady(_snapshot.State=="READY");
        commands.SetConnected(_snapshot.State=="READY");
        _message=_snapshot.State=="READY"?(_snapshot.SetupReady?"Required setup checks are available.":"Core is responding. Setup checks are incomplete or unavailable.")
            :"Core needs attention: "+PopupText.Message(_snapshot.Code)+". Repair the cause and check again.";
    }
    internal Task RefreshAsync(CancellationToken owner)=>Run(async()=>{
        if(commands.View.Pending)await commands.ReconcileAsync().WaitAsync(_life.Token);
        await Read(owner);
    });
    internal Task CheckAsync(bool microphone,CancellationToken owner)
    {
        if(!View.CanCheck)return Task.CompletedTask;
        var target=_snapshot!;
        // Own the shared submission before yielding, preserving same-turn STOP.
        Task pending=commands.SubmitHealthAsync(new(target,microphone));
        return Run(async()=>{await pending.WaitAsync(_life.Token);await Read(owner);});
    }
    internal Task RestartAsync(CancellationToken owner)
    {
        if(!View.CanRestart)return Task.CompletedTask;
        var target=_snapshot!;
        Task pending=commands.SubmitHealthAsync(new(target,null));
        return Run(async()=>{
            await pending.WaitAsync(_life.Token);
            if(commands.View.State is "Failed" or "Stopped" or "Not accepted" or "Not submitted")
            {await Read(owner);_message="Restart was not verified. The requested operation failed, was denied or was stopped.";return;}
            using var budget=CancellationTokenSource.CreateLinkedTokenSource(owner,_life.Token);
            budget.CancelAfter(TimeSpan.FromSeconds(20));
            while(true)
            {
                try{await Read(budget.Token);}catch(Exception)when(!budget.IsCancellationRequested){_snapshot=null;}
                if(_snapshot is {} current)
                {
                    if(current.Pid!=target.Pid||current.CreationTime!=target.CreationTime)
                        throw new InvalidOperationException("Owned host changed.");
                    if(current.InstanceId!=target.InstanceId||current.Code=="RESTART_CANCELLED")
                    {
                        // Drain may interrupt the last live task read. Reconcile
                        // persisted intent on the authenticated graph, never replay it.
                        if(commands.View.Pending)await commands.ReconcileAsync().WaitAsync(budget.Token);
                        if(commands.View.Pending)throw new InvalidOperationException("Saved restart outcome is unconfirmed.");
                    }
                    if(current.InstanceId==target.InstanceId&&current.Code=="RESTART_CANCELLED")
                    {_message="Restart was stopped before replacement began. No recovery was verified.";return;}
                    if(current.InstanceId!=target.InstanceId)
                    {
                        _message=current.State=="READY"&&current.HotkeysRegistered?"Owned Core restarted and authenticated health was verified. Recheck setup for this instance.":"Restart did not restore readiness. "+PopupText.Message(current.Code);
                        return;
                    }
                }
                await Task.Delay(100,budget.Token);
            }
        });
    }
    internal async Task<bool> VerifyContinueAsync(CancellationToken owner)
    {await RefreshAsync(owner);return View.CanContinue;}
    internal void OnRuntime( RuntimeView value)
    {
        if(!value.Connected||value.CoreReady==false||(_snapshot is not null&&value.CoreInstanceId is not null&&_snapshot.InstanceId!=value.CoreInstanceId)||DateTimeOffset.UtcNow-_readAt>TimeSpan.FromSeconds(45))
        {_snapshot=null;if(!_busy)_message="Setup health needs a fresh check.";Publish();}
    }
    internal void OnCommand(CommandView _) => Publish();
    public async ValueTask DisposeAsync()
    {if(_closed)return;_closed=true;_life.Cancel();await _work;Changed=null;_life.Dispose();}
}
