using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record ActionDetailRequest(string RequestId, string TaskId, long ActionId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(TaskId, "task_id");
            if (ActionId <= 0) throw new ArgumentException("Invalid action identity.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version, message_type = "action_detail_query",
                request_id = RequestId, task_id = TaskId, action_id = ActionId }, Options);
        }
    }

    internal sealed record ActionDetail([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string TaskRequestId,
        [property: JsonRequired] long ActionId, [property: JsonRequired] string Tool,
        [property: JsonRequired] string? FactualMessage, [property: JsonRequired] string? ErrorCode,
        [property: JsonRequired] string? PolicyReason)
    {
        internal static ActionDetail Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ActionDetail>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "action_detail", value.RequestId);
            RequireId(value.TaskId, "task_id"); RequireId(value.TaskRequestId, "task_request_id");
            if (value.ActionId <= 0 || value.Tool is null ||
                !System.Text.RegularExpressions.Regex.IsMatch(value.Tool, @"\A[a-z][a-z0-9_]{0,63}\z") ||
                value.ErrorCode is not null && !System.Text.RegularExpressions.Regex.IsMatch(value.ErrorCode, @"\A[A-Z][A-Z0-9_]{0,63}\z") ||
                new[] { value.FactualMessage, value.PolicyReason }.Any(text => text is not null && System.Text.Encoding.UTF8.GetByteCount(text) > 1024))
                throw new JsonException("Invalid action presentation.");
            return value;
        }
    }

    internal sealed record ActivityQueryRequest(string RequestId, string TaskId, long AfterActionId = 0, int Limit = 25)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(TaskId, "task_id");
            if (AfterActionId < 0 || Limit is < 1 or > 100) throw new ArgumentException("Invalid activity page bounds.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version, message_type = "activity_query",
                request_id = RequestId, task_id = TaskId, after_action_id = AfterActionId, limit = Limit }, Options);
        }
    }

    internal sealed record ActivityAction([property: JsonRequired] long ActionId, [property: JsonRequired] int StepIndex,
        [property: JsonRequired] string Tool, [property: JsonRequired] string Risk,
        [property: JsonRequired] bool Verified, [property: JsonRequired] bool ErrorRecorded,
        [property: JsonRequired] bool PolicyDenied, [property: JsonRequired] bool UndoAvailable,
        [property: JsonRequired] bool RollbackAttempted, [property: JsonRequired] bool? RollbackOk);
    internal sealed record ActivityCleanup([property: JsonRequired] bool Complete, [property: JsonRequired] int UnresolvedCount);
    internal sealed record ActivityPage([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string TaskRequestId,
        [property: JsonRequired] string? SavedState, [property: JsonRequired] string? Route,
        [property: JsonRequired] ActivityAction[] Actions, [property: JsonRequired] long NextActionId,
        [property: JsonRequired] bool HasMore, [property: JsonRequired] ActivityCleanup? Cleanup)
    {
        internal static ActivityPage Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ActivityPage>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "activity_page", value.RequestId);
            RequireId(value.TaskId, "task_id"); RequireId(value.TaskRequestId, "task_request_id");
            if (value.SavedState is not (null or "CREATED" or "RUNNING" or "STOPPING" or "ROLLING_BACK" or
                    "SUCCEEDED" or "FAILED" or "STOPPED" or "STOPPED_WITH_RESIDUAL" or "ABORTED_BY_CRASH") ||
                value.Route is not (null or "FAST" or "SMART" or "SCREEN" or "DEEP") || value.NextActionId < 0 ||
                value.Actions is null || value.Actions.Length > 100 || value.HasMore && value.Actions.Length == 0)
                throw new JsonException("Invalid activity page metadata.");
            long previous = 0;
            foreach (var item in value.Actions)
            {
                if (item is null || item.ActionId <= previous || item.StepIndex < 0 || string.IsNullOrEmpty(item.Tool) ||
                    item.Tool.Length > 64 || item.Tool[0] is < 'a' or > 'z' ||
                    item.Tool.Any(c => !(c is >= 'a' and <= 'z' or >= '0' and <= '9' or '_')) ||
                    item.Risk is not ("READ" or "LOW" or "MEDIUM" or "HIGH" or "ADMIN" or "DENY") ||
                    !item.RollbackAttempted && item.RollbackOk is not null)
                    throw new JsonException("Invalid or unordered action evidence.");
                previous = item.ActionId;
            }
            if (value.Actions.Length > 0 && value.NextActionId != previous ||
                value.Cleanup is { } cleanup && (cleanup.UnresolvedCount is < 0 or > 512 || cleanup.Complete != (cleanup.UnresolvedCount == 0)))
                throw new JsonException("Inconsistent activity evidence.");
            return value;
        }
    }
}

internal sealed record ActivityFact(string Identity, string Kind, string Message, bool Warning);

/// <summary>Saved evidence only: no live execution, termination or aggregate success inferred.</summary>
internal static class ActivityProjection
{
    internal static string ActionMessage(CoreRequestProtocol.ActivityAction action) =>
        action.PolicyDenied ? "Policy denial is recorded."
        : action.ErrorRecorded ? "An action issue is recorded."
        : action.Verified ? "The action postcondition was verified."
        : "Action recorded; its postcondition is unverified.";

    internal static ActivityFact[] Project(CoreRequestProtocol.ActivityPage page)
    {
        var facts = new System.Collections.Generic.List<ActivityFact>();
        foreach (var action in page.Actions)
        {
            string message = ActionMessage(action);
            facts.Add(new(page.TaskId + "/action/" + action.ActionId, "action",
                "Step " + ((long)action.StepIndex + 1) + ": " + message, action.PolicyDenied || action.ErrorRecorded));
            if (action.RollbackAttempted)
                facts.Add(new(page.TaskId + "/undo/" + action.ActionId, "rollback",
                    action.RollbackOk == true ? "Rollback success is recorded."
                        : action.RollbackOk == false ? "Rollback failure is recorded; remaining effects require review."
                        : "Rollback was attempted; its outcome is unverified.", action.RollbackOk != true));
        }
        if (page.Cleanup is { } cleanup)
            facts.Add(new(page.TaskId + "/cleanup", "cleanup", cleanup.Complete
                ? "The saved cleanup checks are complete."
                : "The saved cleanup checks contain unresolved evidence.", !cleanup.Complete));
        return facts.ToArray();
    }
}
