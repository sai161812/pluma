using System.Text;
using System.Text.Json;
using PLUMA.UI;

internal static class HealthChecks
{
    private static string Id()=>Guid.NewGuid().ToString("D");
    private static CoreHealthProtocol.Snapshot Snapshot()=>new(1,"health_snapshot",Id(),Id(),123,456,"READY","CORE_READY",true,
        "sha256:"+new string('a',64),[],false,true,false,0);
    private static CoreRequestResult<T> Ok<T>(T value) where T:class=>new(value,CoreConnectionFailure.None,false,null,null);
    internal static async Task RunAsync(Action<bool,string> check)
    {
        var snapshot=Snapshot();
        string Wire(CoreHealthProtocol.Snapshot value)=>JsonSerializer.Serialize(value,new JsonSerializerOptions{PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower});
        check(CoreHealthProtocol.Snapshot.Parse(Encoding.UTF8.GetBytes(Wire(snapshot))).CanRestart,"health parser preserves exact owned Core identity without inventing setup readiness");
        var fixture=snapshot with {Checks=new[]{"planner","speech","ocr","uia","microphone"}.Select(id=>new CoreHealthProtocol.Check(id,"PASSED","FIXTURE_ONLY","fixture")).ToArray(),NativeVerified=false,SetupReady=true};
        bool rejected=false;try{CoreHealthProtocol.Snapshot.Parse(Encoding.UTF8.GetBytes(Wire(fixture)));}catch(JsonException){rejected=true;}
        check(rejected,"fixture capability results cannot assert production Continue");
        var native=snapshot with {Checks=new[]{"planner","speech","ocr","uia","microphone"}.Select(id=>new CoreHealthProtocol.Check(id,"PASSED","NATIVE_ACCESS_VERIFIED","native")).ToArray(),NativeVerified=true,SetupReady=true};
        check(CoreHealthProtocol.Snapshot.Parse(Encoding.UTF8.GetBytes(Wire(native))).SetupReady,"complete native receipt schema is accepted; unit data is not native acceptance");
        rejected=false;try{CoreHealthProtocol.Snapshot.Parse(Encoding.UTF8.GetBytes(Wire(native).Replace("\"state\":\"PASSED\"","\"state\":\"FAILED\",\"state\":\"PASSED\"")));}catch(JsonException){rejected=true;}
        check(rejected,"nested duplicate capability state cannot override failure");
        var backend=new Client();
        await using var commands=new CommandController(backend,TimeSpan.FromMilliseconds(1));
        await using var health=new HealthController((id,t)=>Task.FromResult(Ok(snapshot with {RequestId=id})),commands);
        await health.RefreshAsync(default);
        check(health.View.CanCheck&&health.View.CanRestart&&!health.View.CanContinue,"authenticated Core responsiveness never substitutes for native setup proof");
        await health.CheckAsync(false,default);
        check(backend.Count==1&&backend.Last?.IncludeMicrophone==false&&!health.View.CanContinue,"user setup check retains microphone consent and native readiness stays unverified");
        backend.AfterSubmit=()=>snapshot=snapshot with {InstanceId=Id(),State="READY"};
        await health.RestartAsync(default);
        check(backend.Count==2&&health.View.Message.Contains("authenticated health was verified"),"recovery requires authenticated new-instance health from the same owned PID and creation time");
        backend.AfterSubmit=()=>snapshot=snapshot with {Code="RESTART_CANCELLED"};
        await health.RestartAsync(default);
        check(health.View.Message.Contains("stopped before replacement"),"global STOP withdrawing a queued restart never reports recovery");
        backend.AfterSubmit=()=>snapshot=snapshot with {InstanceId=Id(),State="CONFIGURATION_ERROR",Code="SETTINGS_INVALID"};
        await health.RestartAsync(default);
        check(health.View.Message.Contains("did not restore")&&!health.View.CanCheck&&!health.View.CanContinue,"restart with invalid configuration never claims successful recovery");
        snapshot=Snapshot();await health.RefreshAsync(default);
        using var entered=new SemaphoreSlim(0);
        backend.Entered=entered;backend.Wait=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending=health.CheckAsync(false,default);await entered.WaitAsync();
        await commands.StopAsync().WaitAsync(TimeSpan.FromSeconds(1));
        backend.Wait.TrySetResult();await pending;
        check(backend.Fence==backend.Request&&backend.Stops==1,"setup STOP uses the independently owned shared request fence");
        health.OnRuntime(new([],true,1,Id(),true));
        check(health.View.Snapshot is null&&!health.View.CanContinue,"a changed Core instance invalidates all cached setup proofs");
    }
    private sealed class Client:ICommandClient
    {
        internal int Count,Stops;
        internal string? Request,Fence;
        internal CoreHealthProtocol.Operation? Last;
        internal Action? AfterSubmit;
        internal SemaphoreSlim? Entered;
        internal TaskCompletionSource? Wait;
        private readonly string TaskId=Id();
        public Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request,string text,CancellationToken token)=>throw new Exception("Health must be typed.");
        public async Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitHealthAsync(string request,CoreHealthProtocol.Operation operation,CancellationToken token)
        {Count++;Request=request;Last=operation;Entered?.Release();if(Wait is not null)await Wait.Task.WaitAsync(token);AfterSubmit?.Invoke();return Ok(new CoreRequestProtocol.SubmissionAck(1,"submission_ack",request,true,TaskId,null,"Owned fixture"));}
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request,string task,CancellationToken token)=>Task.FromResult(Ok(new CoreRequestProtocol.TerminalReadback(1,"terminal_readback",request,task,true,"SUCCEEDED",true,true,false,"FAST","Owned fixture",1)));
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request,CancellationToken token)=>Task.FromResult(Ok(new CoreRequestProtocol.HistoryReply(1,"history_reply",request,null,[],[])));
        public Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request,string? submissionRequest,CancellationToken token)
        {Stops++;Fence=submissionRequest;return Task.FromResult(Ok(new CoreRequestProtocol.StopAck(1,"stop_ack",request,"ok","pluma.stop.v1","Owned fixture",null,[],[],0,1)));}
    }
}
