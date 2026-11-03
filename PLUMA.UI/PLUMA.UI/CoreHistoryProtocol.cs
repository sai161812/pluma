using System;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record HistoryPageRequest(string RequestId, string Search = "", string? BeforeTaskId = null, int Limit = 20)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id");
            if (BeforeTaskId is not null) RequireId(BeforeTaskId, "before_task_id");
            if (Search is null || Search.EnumerateRunes().Count() > 256 || Limit is < 1 or > 20)
                throw new ArgumentException("Invalid saved history bounds.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "history_page_query", request_id = RequestId, search = Search,
                before_task_id = BeforeTaskId, limit = Limit }, Options);
        }
    }
    internal sealed record SavedHistoryTask([property: JsonRequired] string TaskId,
        [property: JsonRequired] string RequestId, [property: JsonRequired] string InputMode,
        [property: JsonRequired] string? CommandText, [property: JsonRequired] string CreatedAt,
        [property: JsonRequired] string? StartedAt, [property: JsonRequired] string? CompletedAt,
        [property: JsonRequired] string? FinalState, [property: JsonRequired] string? Route,
        [property: JsonRequired] string? StopReason, [property: JsonRequired] string? ErrorCode);

    internal sealed record HistoryPageReply([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string? BeforeTaskId, [property: JsonRequired] SavedHistoryTask[] Tasks,
        [property: JsonRequired] bool HasMore, [property: JsonRequired] string? NextBeforeTaskId)
    {
        internal static HistoryPageReply Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<HistoryPageReply>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "history_page", value.RequestId);
            if (value.BeforeTaskId is not null) RequireId(value.BeforeTaskId, "before_task_id");
            if (value.NextBeforeTaskId is not null) RequireId(value.NextBeforeTaskId, "next_before_task_id");
            if (value.Tasks is null || value.Tasks.Length > 20 || value.Tasks.Any(t => t is null) ||
                value.HasMore != (value.NextBeforeTaskId is not null) ||
                value.HasMore && (value.Tasks.Length == 0 || value.NextBeforeTaskId != value.Tasks[^1].TaskId) ||
                value.Tasks.Select(t => t.TaskId).Distinct().Count() != value.Tasks.Length ||
                value.Tasks.Any(t => t.TaskId == value.BeforeTaskId))
                throw new JsonException("Inconsistent saved history page.");
            static bool Time(string? text) => text is not null && text.Length <= 64 &&
                DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out _) &&
                (text.EndsWith("Z", StringComparison.Ordinal) || System.Text.RegularExpressions.Regex.IsMatch(text, @"[+-]\d{2}:\d{2}$"));
            static bool Code(string? text) => text is null || System.Text.RegularExpressions.Regex.IsMatch(text, @"\A[A-Za-z][A-Za-z0-9_]{0,63}\z");
            foreach (var task in value.Tasks)
            {
                RequireId(task.TaskId, "task_id"); RequireId(task.RequestId, "request_id");
                if (task.InputMode is not ("text" or "voice") || !Time(task.CreatedAt) ||
                    task.StartedAt is not null && !Time(task.StartedAt) || task.CompletedAt is not null && !Time(task.CompletedAt) ||
                    task.CommandText is not null && Encoding.UTF8.GetByteCount(task.CommandText) > 8192 ||
                    task.FinalState is not (null or "CREATED" or "RUNNING" or "STOPPING" or "ROLLING_BACK" or "SUCCEEDED" or
                        "FAILED" or "STOPPED" or "STOPPED_WITH_RESIDUAL" or "DEFERRED" or "ABORTED_BY_CRASH") ||
                    task.Route is not (null or "FAST" or "SMART" or "SCREEN" or "DEEP") || !Code(task.StopReason) || !Code(task.ErrorCode))
                    throw new JsonException("Invalid saved task facts.");
            }
            for (int i = 1; i < value.Tasks.Length; i++)
                if (CompareHistory(value.Tasks[i-1], value.Tasks[i]) <= 0)
                    throw new JsonException("Saved history ordering regressed.");
            return value;
        }
    }
    internal static int CompareHistory(SavedHistoryTask first, SavedHistoryTask second)
    {
        int time = StringComparer.Ordinal.Compare(first.CreatedAt, second.CreatedAt);
        return time == 0 ? StringComparer.Ordinal.Compare(first.TaskId, second.TaskId) : time;
    }
}
