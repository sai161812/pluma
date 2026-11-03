using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class HistoryChecks
{
    internal static CoreRequestProtocol.SavedHistoryTask Row(string? task = null) => new(
        task ?? Guid.NewGuid().ToString("D"), Guid.NewGuid().ToString("D"), "voice", "Open file_预算.md",
        "2026-11-02T08:00:00+00:00", null, "2026-11-02T08:01:00+00:00", "STOPPED", "FAST", "user_stop", null);
    internal static async Task RunAsync(Action<bool, string> check)
    {
        string id = Guid.NewGuid().ToString("D");
        var row = Row();
        var frame = new CoreRequestProtocol.HistoryPageReply(1, "history_page", id, null, [row], true, row.TaskId);
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
        string wire = JsonSerializer.Serialize(frame, options);
        check(CoreRequestProtocol.HistoryPageReply.Parse(Encoding.UTF8.GetBytes(wire)).Tasks[0].CommandText == row.CommandText,
            "saved history retains literal filenames and raw saved identities");
        foreach (Action<JsonObject> mutate in new Action<JsonObject>[] {
            node => node.Remove("has_more"), node => node["extra"] = "private",
            node => node["next_before_task_id"] = null, node => node["has_more"] = false,
            node => node["tasks"]![0]!["input_mode"] = "guess",
            node => node["tasks"]![0]!["task_id"] = "bad",
            node => node["tasks"]![0]!["created_at"] = "yesterday",
            node => node["tasks"]![0]!["route"] = "invented",
            node => node["tasks"]![0]!["final_state"] = "unknown_success",
            node => node["tasks"]![0]!.AsObject().Remove("command_text"),
            node => node["tasks"]![0]!["command_text"] = new string('文', 3000),
            node => node["tasks"]!.AsArray().Add(node["tasks"]![0]!.DeepClone()) })
        {
            var node = JsonNode.Parse(wire)!.AsObject(); mutate(node);
            try { CoreRequestProtocol.HistoryPageReply.Parse(Encoding.UTF8.GetBytes(node.ToJsonString())); throw new Exception("Invalid history accepted."); }
            catch (JsonException) { check(true, "inconsistent saved history is refused"); }
        }
        int calls = 0; bool fail = false;
        var controller = new HistoryController((query, token) =>
        {
            calls++;
            if (calls == 1) return Task.FromResult(CoreRequestResult<CoreRequestProtocol.HistoryPageReply>.Failed(CoreConnectionFailure.Busy));
            var next = query.BeforeTaskId is null ? row : Row("00000000-0000-0000-0000-000000000000");
            return Task.FromResult(fail ? CoreRequestResult<CoreRequestProtocol.HistoryPageReply>.Failed(CoreConnectionFailure.Unavailable)
                : new CoreRequestResult<CoreRequestProtocol.HistoryPageReply>(frame with { RequestId = query.RequestId,
                    BeforeTaskId = query.BeforeTaskId, Tasks = [next], HasMore = query.BeforeTaskId is null,
                    NextBeforeTaskId = query.BeforeTaskId is null ? row.TaskId : null }, CoreConnectionFailure.None, false, null, null));
        });
        await controller.RefreshAsync("预算", default);
        check(calls == 2 && controller.View.Rows[0].CommandText == row.CommandText && controller.View.HasMore,
            "owned history read retries temporary slot pressure without changing its cursor");
        check(controller.View.Rows[0].StateText == "Saved: Stopped" && controller.View.Rows[0].MetadataText.Contains("Voice"),
            "history presentation labels saved facts without inventing verification");
        await controller.OlderAsync(default);
        check(controller.View.Rows.Length == 1 && !controller.View.HasMore && controller.View.Rows[0].TaskId != row.TaskId,
            "older history replaces its page and keeps memory bounded");
        fail = true; await controller.RefreshAsync("private filter", default);
        check(!controller.View.Connected && controller.View.Rows.Length == 0 && !controller.View.HasMore,
            "storage failure clears stale history without pretending it is empty");
        await controller.DisposeAsync();
        using var entered = new SemaphoreSlim(0);
        var blocked = new HistoryController(async (request, token) => { entered.Release(); await Task.Delay(Timeout.Infinite, token); throw new Exception(); });
        Task pending = blocked.RefreshAsync("", default); await entered.WaitAsync();
        await blocked.DisposeAsync(); await pending.WaitAsync(TimeSpan.FromSeconds(1));
        check(true, "shell disposal cancels and joins its only history read");
    }
}
