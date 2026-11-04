using PLUMA.UI;

internal static class PerceptionDeliveryChecks
{
    internal static async Task RunAsync(Action<bool,string> check)
    {
        string Id() => Guid.NewGuid().ToString("D");
        string task = Id(), request = Id(), instance = Id();
        var live = new CoreRequestProtocol.RuntimeTask(task, request,"RUNNING",0,0,null,null,null,null,null,null,null,null,null,null);
        int calls = 0;
        bool active = false, fail = false, mismatch = false;
        var controller = new RuntimeController((id,token) => Task.FromResult(
            new CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>(new(1,"runtime_snapshot",id,active?[live]:[],[],
                CoreInstanceId:instance,CoreReady:true),CoreConnectionFailure.None,false,null,null)),
            perception:(id,token) =>
            {
                calls++;
                return Task.FromResult(fail ? CoreRequestResult<CoreRequestProtocol.PerceptionSnapshot>.Failed(CoreConnectionFailure.Timeout) :
                    new(new(1,"perception_snapshot",mismatch?Id():id,[]),CoreConnectionFailure.None,false,null,null));
            });
        CoreRequestProtocol.PerceptionSnapshot? observed = null;
        controller.PerceptionChanged += frame => observed=frame;
        await controller.PollOnceAsync(default);
        check(calls==0 && observed is null,"idle runtime observer does not query, capture or poll perception separately");
        active=true; await controller.PollOnceAsync(default);
        check(calls==1 && observed is not null,"live runtime owner serializes correlated perception readback under the same lifetime");
        fail=true; await controller.PollOnceAsync(default);
        check(observed is null,"failed perception readback clears the previous presentation frame");
        fail=false; mismatch=true; await controller.PollOnceAsync(default);
        check(observed is null,"mismatched perception correlation never reaches the native host");
        active=false; await controller.PollOnceAsync(default);
        check(calls==3 && observed is null,"terminal or missing task clears feedback without starting new observation work");
    }
}
