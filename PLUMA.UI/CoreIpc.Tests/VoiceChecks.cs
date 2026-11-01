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
