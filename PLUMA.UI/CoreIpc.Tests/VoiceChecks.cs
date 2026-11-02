using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class VoiceChecks
{
    internal static void Run(Action<bool, string> check)
    {
        string id = Guid.NewGuid().ToString("D"), task = Guid.NewGuid().ToString("D");
        var view = new CoreRequestProtocol.VoiceView(id, task, null, "DECODING", null, null, null, id, 1, "actual segment");
        var frame = new CoreRequestProtocol.VoiceSnapshot(1, "voice_snapshot", id, task, true, view);
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        string wire = JsonSerializer.Serialize(frame, options);
        check(CoreRequestProtocol.VoiceSnapshot.Parse(Encoding.UTF8.GetBytes(wire)).Voice is { Phase: "DECODING", TaskRequestId: null },
            "native consumer never equates recognition with commitment");
        foreach (string phase in new[] { "STARTING", "LISTENING", "DECODING", "COMMITTED", "CLARIFICATION", "EMPTY", "ERROR", "CANCELLED", "TIMED_OUT" })
        {
            var candidate = frame with { Voice = view with { Phase = phase, Text = "", RecognitionId = null, RecognitionSequence = 0,
                TaskRequestId = phase == "COMMITTED" ? id : null,
                Code = phase == "CLARIFICATION" ? "LOW_CONFIDENCE_MATERIAL_TARGET" : phase == "ERROR" ? "VOICE_FAILED" : null } };
            check(CoreRequestProtocol.VoiceSnapshot.Parse(JsonSerializer.SerializeToUtf8Bytes(candidate, options)).Voice!.Phase == phase,
                "typed voice phase accepted: " + phase);
        }
        foreach (Action<JsonObject> mutate in new Action<JsonObject>[] {
            node => node.Remove("voice"), node => node["extra"] = true,
            node => node["voice"]!["phase"] = "COMMITTED",
            node => node["voice"]!["phase"] = "CANCELLED",
            node => node["voice"]!["capture_active"] = true,
            node => node["voice"]!["recognition_sequence"] = 129,
            node => node["voice"]!["recognition_id"] = null,
            node => node["voice"]!["text"] = new string('文', 6000),
            node => node["voice"]!["task_id"] = "bad",
            node => node["voice"]!["phase"] = "INVENTED",
            node => node["voice"]!["meter"] = JsonSerializer.SerializeToNode(new CoreRequestProtocol.VoiceMeter(.2, new double[31], true, 0), options),
            node => node["voice"]!.AsObject().Remove("text") })
        {
            var node = JsonNode.Parse(wire)!.AsObject(); mutate(node);
            try { CoreRequestProtocol.VoiceSnapshot.Parse(Encoding.UTF8.GetBytes(node.ToJsonString())); throw new Exception("Invalid voice accepted."); }
            catch (Exception error) when (error is JsonException or ArgumentException) { check(true, "invalid voice evidence refused"); }
        }
        try { new CoreRequestProtocol.VoiceRequest(id, null, task).ToMessage(); throw new Exception("Unscoped voice accepted."); }
        catch (ArgumentException) { check(true, "voice generation query requires a stream identity"); }
    }
}

internal static class VoiceControllerChecks
{
    internal static async Task RunAsync(Action<bool, string> check)
    {
        string stream = Guid.NewGuid().ToString("D"), generation = Guid.NewGuid().ToString("D"), task = Guid.NewGuid().ToString("D");
        string phase = "DECODING"; int sequence = 1; bool fail = false;
        var controller = new VoiceController((id, previousStream, previousVoice, token) =>
        {
            var view = new CoreRequestProtocol.VoiceView(generation, task, phase == "COMMITTED" ? task : null,
                phase, null, null, null, phase == "DECODING" ? task : null, phase == "DECODING" ? sequence : 0,
                phase is "DECODING" or "COMMITTED" ? "owned literal file_name.md" : "");
            var snapshot = new CoreRequestProtocol.VoiceSnapshot(1, "voice_snapshot", id, stream,
                previousStream != stream || previousVoice != generation, view);
            return Task.FromResult(fail ? CoreRequestResult<CoreRequestProtocol.VoiceSnapshot>.Failed(CoreConnectionFailure.Unavailable)
                : new CoreRequestResult<CoreRequestProtocol.VoiceSnapshot>(snapshot, CoreConnectionFailure.None, false, null, null));
        });
        await controller.PollOnceAsync(default);
        check(controller.View is { Connected: true, Reset: true, Voice.Phase: "DECODING" }, "voice observer binds real transient generation");
        sequence = 2; await controller.PollOnceAsync(default);
        check(!controller.View.Reset && controller.View.Voice!.RecognitionSequence == 2, "same voice generation preserves reading identity");
        sequence = 1;
        try { await controller.PollOnceAsync(default); throw new Exception("Regressed voice accepted."); }
        catch (InvalidOperationException) { check(controller.View.Voice is null, "regressed voice clears old transcript"); }
        sequence = 2; await controller.PollOnceAsync(default);
        phase = "COMMITTED"; await controller.PollOnceAsync(default);
        phase = "DECODING";
        try { await controller.PollOnceAsync(default); throw new Exception("Revived voice accepted."); }
        catch (InvalidOperationException) { check(controller.View.Voice is null, "late voice decoding cannot revive a committed generation"); }
        generation = Guid.NewGuid().ToString("D"); await controller.PollOnceAsync(default);
        check(controller.View.Reset && controller.View.Voice!.VoiceId == generation, "new voice replaces the old generation");
        fail = true; await controller.PollOnceAsync(default);
        check(!controller.View.Connected && controller.View.Voice is null, "disconnect clears recognition without persistence or replay");
        using var lifetime = new CancellationTokenSource();
        var blocked = new VoiceController(async (id, stream, voice, token) => { await Task.Delay(Timeout.Infinite, token); throw new Exception(); });
        var run = blocked.RunAsync(lifetime.Token); lifetime.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(1));
        check(blocked.View.Voice is null, "shell cancellation drains owned voice poll and clears copy");
    }
}
