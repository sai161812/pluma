using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class RuntimeChecks
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        string id = Guid.NewGuid().ToString("D"), task = Guid.NewGuid().ToString("D");
        var node = new CoreRequestProtocol.RuntimeTask(task, id, "RUNNING", 100, 1, 1, 2,
            "fixture_wait", "READ", "EXECUTING", 20, "{}", null, null, null);
        var frame = new CoreRequestProtocol.RuntimeSnapshot(1, "runtime_snapshot", id, [node], []);
        var activation=frame with {TextActivationId=Guid.NewGuid().ToString("D"),TextActivationUtc=DateTimeOffset.UtcNow.ToString("O")};
        var source=activation;
        var controller=new RuntimeController((request,token)=>Task.FromResult(new CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>(
            source with {RequestId=request},CoreConnectionFailure.None,false,null,null)));
        int activations=0;controller.TextRequested+=_=>activations++;
        await controller.PollOnceAsync(default);await controller.PollOnceAsync(default);
        source=activation with {TextActivationId=Guid.NewGuid().ToString("D"),TextActivationUtc=DateTimeOffset.UtcNow.AddSeconds(-10).ToString("O")};
        await controller.PollOnceAsync(default);
        check(activations==1,"text activation opens once and expired readback cannot replay command entry");
        string Wire(object value) => JsonSerializer.Serialize(value, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower });
        check(CoreRequestProtocol.RuntimeSnapshot.Parse(Encoding.UTF8.GetBytes(Wire(frame))).Tasks.Single().Tool == "fixture_wait",
            "runtime parser retains exact owned task and actual execution phase");
        foreach (string fault in new[] { "terminal", "step", "entry", "private-size", "duplicate", "missing" })
        {
            var value = JsonNode.Parse(Wire(frame))!.AsObject(); var item = value["tasks"]![0]!.AsObject();
            switch (fault)
            {
                case "terminal": item["state"] = "SUCCEEDED"; break;
                case "step": item["step"] = 3; break;
                case "entry": item["tool_elapsed_ms"] = null; break;
                case "private-size": item["arguments"] = new string('文', 400); break;
                case "duplicate": value["tasks"]!.AsArray().Add(item.DeepClone()); break;
                case "missing": item.Remove("phase"); break;
            }
            try { CoreRequestProtocol.RuntimeSnapshot.Parse(Encoding.UTF8.GetBytes(value.ToJsonString())); throw new Exception("Bad runtime accepted."); }
            catch (JsonException) { check(true, "runtime fails closed: " + fault); }
        }
        bool fail = false;
        var owner = new RuntimeController((request, token) => Task.FromResult(fail
            ? CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>.Failed(CoreConnectionFailure.Unavailable)
            : new CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>(frame with { RequestId = request }, CoreConnectionFailure.None, false, null, null)));
        await owner.PollOnceAsync(default);
        check(owner.View is { Connected: true, Tasks.Length: 1, RoundTripMs: not null }, "runtime observer publishes supplied facts with measured round-trip time");
        fail = true; await owner.PollOnceAsync(default);
        check(!owner.View.Connected && owner.View.Tasks.Length == 0 && owner.View.RoundTripMs is null,
            "unavailable runtime clears live claims without inventing a terminal outcome");
        using var cancel = new CancellationTokenSource();
        var blocked = new RuntimeController(async (request, token) => { await Task.Delay(Timeout.Infinite, token); throw new Exception(); });
        var loop = blocked.RunAsync(cancel.Token); cancel.Cancel(); await loop.WaitAsync(TimeSpan.FromSeconds(1));
        check(!blocked.View.Connected, "owned runtime observer cancels and drains its pending readback");
        var proof = new CoreRequestProtocol.WorkerTermination(task, id, 321, 123456, 1, "tool_worker");
        var current = frame with { Terminations = [proof] };
        var observer = new RuntimeController((request, token) => Task.FromResult(fail
            ? CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>.Failed(CoreConnectionFailure.Unavailable)
            : new CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>(current with { RequestId = request }, CoreConnectionFailure.None, false, null, null)));
        int notices = 0; observer.WorkerTerminated += _ => notices++;
        fail = false; await observer.PollOnceAsync(default);
        check(notices == 0, "historical worker evidence seeds silently at initial connection");
        current = current with { Terminations = [proof, proof with { CreationTime = 123457 }] };
        await observer.PollOnceAsync(default); await observer.PollOnceAsync(default);
        fail = true; await observer.PollOnceAsync(default); fail = false; await observer.PollOnceAsync(default);
        check(notices == 1, "new identity-bound worker proof emits once across replay and reconnect");
        foreach (var bad in new[] { proof with { Pid = 0 }, proof with { CreationTime = 0 }, proof with { CommandClass = "external" } })
        {
            try { CoreRequestProtocol.RuntimeSnapshot.Parse(Encoding.UTF8.GetBytes(Wire(frame with { Terminations = [bad] }))); throw new Exception("Invalid worker accepted."); }
            catch (JsonException) { check(true, "worker parser rejects invalid ownership identity"); }
        }
        var verification = new CoreRequestProtocol.ActionVerification(1, "action_verification", id, task, id, 1,
            "invoke_control", true, "owned_readback", "Verified fixture.");
        check(CoreRequestProtocol.ActionVerification.Parse(Encoding.UTF8.GetBytes(Wire(verification))).Verified == true,
            "verification parser retains saved readback proof");
        try { CoreRequestProtocol.ActionVerification.Parse(Encoding.UTF8.GetBytes(Wire(verification with { Method = null }))); throw new Exception("Partial proof accepted."); }
        catch (JsonException) { check(true, "verification parser refuses partial proof"); }
    }
}
