using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using PLUMA.UI;

internal static class ActivityChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static string Wire(object value) => JsonSerializer.Serialize(value, new JsonSerializerOptions
        { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower });

    internal static void Run(Action<bool, string> check)
    {
        string task = Id(), request = Id();
        var action = new CoreRequestProtocol.ActivityAction(3, 0, "fixture_read", "READ", true, false, false, true, false, null);
        var page = new CoreRequestProtocol.ActivityPage(1, "activity_page", Id(), task, request,
            "SUCCEEDED", "FAST", [action], 3, false, new(true, 0));
        var parsed = CoreRequestProtocol.ActivityPage.Parse(Encoding.UTF8.GetBytes(Wire(page)));
        var detail = new CoreRequestProtocol.ActionDetail(1, "action_detail", Id(), task, request, 3,
            "fixture_read", "Read owned résumé 文件.", null, null);
        check(CoreRequestProtocol.ActionDetail.Parse(Encoding.UTF8.GetBytes(Wire(detail))).FactualMessage == detail.FactualMessage,
            "typed action presentation preserves bounded Unicode executor copy");
        foreach (string change in new[] { "missing-text", "oversized-unicode", "bad-code", "bad-tool", "bad-id" })
        {
            var node = JsonNode.Parse(Wire(detail))!.AsObject();
            switch (change)
            {
                case "missing-text": node.Remove("factual_message"); break;
                case "oversized-unicode": node["factual_message"] = new string('文', 400); break;
                case "bad-code": node["error_code"] = "not a code"; break;
                case "bad-tool": node["tool"] = "bad tool"; break;
                case "bad-id": node["action_id"] = 0; break;
            }
            try { CoreRequestProtocol.ActionDetail.Parse(Encoding.UTF8.GetBytes(node.ToJsonString())); throw new Exception("Bad detail accepted."); }
            catch (JsonException) { check(true, "action presentation fails closed: " + change); }
        }
        check(parsed.TaskId == task && parsed.Actions.Single().Verified && parsed.Cleanup is { Complete: true },
            "typed activity parser retains exact task/action correlation and cleanup evidence");
        foreach (string change in new[] { "missing-flag", "wrong-boolean", "duplicate-id", "wrong-tail", "cleanup-contradiction", "unattempted-rollback", "unknown-state" })
        {
            var node = JsonNode.Parse(Wire(page))!.AsObject();
            var first = node["actions"]![0]!.AsObject();
            switch (change)
            {
                case "missing-flag": first.Remove("verified"); break;
                case "wrong-boolean": first["verified"] = "true"; break;
                case "duplicate-id": node["actions"]!.AsArray().Add(first.DeepClone()); break;
                case "wrong-tail": node["next_action_id"] = 9; break;
                case "cleanup-contradiction": node["cleanup"]!["unresolved_count"] = 1; break;
                case "unattempted-rollback": first["rollback_ok"] = true; break;
                case "unknown-state": node["saved_state"] = "invented"; break;
            }
            try { CoreRequestProtocol.ActivityPage.Parse(Encoding.UTF8.GetBytes(node.ToJsonString())); throw new InvalidOperationException("Invalid activity accepted."); }
            catch (JsonException) { check(true, "activity evidence fails closed: " + change); }
        }
        var facts = ActivityProjection.Project(parsed);
        check(facts.Any(f => f.Message.Contains("postcondition was verified")) &&
            facts.All(f => !f.Message.Contains("worker") && !f.Message.Contains("Task completed")),
            "action verification and cleanup completion never invent task success or worker termination");
        var pending = page with { Actions = [action with { Verified = false, ErrorRecorded = true, RollbackAttempted = true, RollbackOk = null }], Cleanup = new(false, 1) };
        check(ActivityProjection.Project(pending).Any(f => f.Kind == "rollback" && f.Warning && f.Message.Contains("unverified")) &&
            ActivityProjection.Project(pending).Any(f => f.Kind == "cleanup" && f.Warning),
            "unverified rollback and unresolved cleanup retain warning facts");
        var denied = page with { Actions = [action with { Verified = false, PolicyDenied = true, ErrorRecorded = true }] };
        check(ActivityProjection.Project(denied).Single(f => f.Kind == "action").Message.Contains("Policy denial"),
            "deterministic policy projection distinguishes denial from verified postconditions");
        foreach (var query in new[] { new CoreRequestProtocol.ActivityQueryRequest(Id(), task, -1),
            new CoreRequestProtocol.ActivityQueryRequest(Id(), task, Limit: 101) })
        {
            try { query.ToMessage(); throw new InvalidOperationException("Invalid page request accepted."); }
            catch (ArgumentException) { check(true, "activity request bounds validate before transport"); }
        }
    }

    internal static async Task RunNativeAsync(CoreIpcClient client, Action<bool, string> check)
    {
        var recent = await client.GetHistoryAsync(Id(), null, 25, default);
        if (!recent.IsSuccess) throw new InvalidOperationException("Owned fixture history unavailable.");
        foreach (var task in recent.Response!.Tasks)
        {
            var history = await client.GetHistoryAsync(Id(), task.TaskId, 100, default);
            if (!history.IsSuccess || history.Response!.Actions.Length == 0) continue;
            var result = await client.GetActivityAsync(new(Id(), task.TaskId, Limit: 1), default);
            if (!result.IsSuccess) throw new InvalidOperationException("Actual activity query refused.");
            var page = result.Response!;
            check(page.TaskId == task.TaskId && page.TaskRequestId == task.RequestId && page.Actions.Length == 1,
                "actual authenticated activity query preserves task/request/action scope");
            var expected = history.Response.Actions.Single(a => a.ActionId == page.Actions[0].ActionId);
            check(page.Actions[0].Verified == expected.Verified && page.Actions[0].RollbackAttempted == expected.RollbackAttempted &&
                page.Actions[0].UndoAvailable == expected.UndoAvailable,
                "actual activity flags agree with independent WAL history readback");
            var detail = await client.GetActionDetailAsync(new(Id(), task.TaskId, page.Actions[0].ActionId), default);
            check(detail.IsSuccess && detail.Response!.TaskRequestId == task.RequestId && detail.Response.Tool == expected.Tool,
                "actual authenticated action detail retains exact saved task/request/action/tool scope");
            string serialized = Wire(page);
            check(!serialized.Contains("arguments") && !serialized.Contains("command_text") && !serialized.Contains("creation_time"),
                "native activity response contains no command, argument body or process identity");
            var next = await client.GetActivityAsync(new(Id(), task.TaskId, page.NextActionId, 1), default);
            check(next.IsSuccess && next.Response!.Actions.All(a => a.ActionId > page.NextActionId),
                "actual native action pagination advances without duplicate rows");
            return;
        }
        throw new InvalidOperationException("No owned recorded action was available for native activity acceptance.");
    }
}
