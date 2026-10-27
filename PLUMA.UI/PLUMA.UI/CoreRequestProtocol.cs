using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static class CoreRequestProtocol
{
    internal const int Version = 1;
    private static readonly JsonSerializerOptions Options = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = false,
        UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
        MaxDepth = 8
    };

    internal sealed record SubmitText(string RequestId, string Text)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, nameof(RequestId));
            if (string.IsNullOrWhiteSpace(Text) || Text.Length > 4096)
                throw new ArgumentException("Text request is outside the protocol bounds.");
            return JsonSerializer.SerializeToUtf8Bytes(new SubmitEnvelope(Version, "submit_text", RequestId, Text), Options);
        }
    }

    internal sealed record TerminalReadbackRequest(string RequestId, string TaskId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, nameof(RequestId)); RequireId(TaskId, nameof(TaskId));
            return JsonSerializer.SerializeToUtf8Bytes(new ReadbackEnvelope(Version, "terminal_readback", RequestId, TaskId), Options);
        }
    }

    internal sealed record StopRequest(string RequestId, string? TaskId = null)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, nameof(RequestId));
            if (TaskId is not null) RequireId(TaskId, nameof(TaskId));
            return JsonSerializer.SerializeToUtf8Bytes(new StopEnvelope(Version, "stop", RequestId, TaskId), Options);
        }
    }

    internal sealed record SettingsQueryRequest(string RequestId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, nameof(RequestId));
            return JsonSerializer.SerializeToUtf8Bytes(new SettingsEnvelope(Version, "settings_query", RequestId), Options);
        }
    }

    internal sealed record HistoryQueryRequest(string RequestId, string? TaskId = null, int Limit = 25)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, nameof(RequestId));
            if (TaskId is not null) RequireId(TaskId, nameof(TaskId));
            if (Limit is < 1 or > 100) throw new ArgumentOutOfRangeException(nameof(Limit));
            return JsonSerializer.SerializeToUtf8Bytes(new HistoryEnvelope(Version, "history_query", RequestId, TaskId, Limit), Options);
        }
    }

    internal sealed record SettingsSnapshot(int ProtocolVersion, string MessageType, string RequestId,
        string TextHotkey, string StopHotkey, string VoiceHotkey, int MaxPlanSteps, int DefaultToolTimeoutSeconds,
        int ModelIdleUnloadSeconds, int SttIdleUnloadSeconds, int OcrIdleUnloadSeconds,
        bool AllowShortWarmGrace, bool VoiceRequired, string ActivationDefault,
        bool WakePhraseEnabled, bool SaveAudio, bool PersistScreenshots, bool OcrEnabled,
        bool UiaFirst, string ModelRuntime, string ModelProfile, string? PlannerModelPath,
        string? SttModelPath, bool ConfirmHighRisk,
        bool RedactSensitiveLogs, bool ActivityViewEnabled)
    {
        internal static SettingsSnapshot Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<SettingsSnapshot>(message.ToArray(), Options)
                ?? throw new JsonException("Empty settings response.");
            if (value.ProtocolVersion != Version || value.MessageType != "settings_snapshot")
                throw new JsonException("Unsupported settings response envelope.");
            RequireId(value.RequestId, "request_id");
            if (string.IsNullOrWhiteSpace(value.TextHotkey) || string.IsNullOrWhiteSpace(value.StopHotkey) ||
                string.IsNullOrWhiteSpace(value.VoiceHotkey) ||
                value.MaxPlanSteps < 1 || value.DefaultToolTimeoutSeconds < 1 ||
                value.ModelIdleUnloadSeconds < 0 || value.SttIdleUnloadSeconds < 0 || value.OcrIdleUnloadSeconds < 0 ||
                string.IsNullOrWhiteSpace(value.ActivationDefault) || string.IsNullOrWhiteSpace(value.ModelRuntime) ||
                string.IsNullOrWhiteSpace(value.ModelProfile) ||
                (value.PlannerModelPath is not null && string.IsNullOrWhiteSpace(value.PlannerModelPath)) ||
                (value.SttModelPath is not null && string.IsNullOrWhiteSpace(value.SttModelPath)))
                throw new JsonException("Invalid settings snapshot values.");
            return value;
        }
    }

    internal sealed record TaskSummary(string TaskId, string RequestId, string InputMode,
        string CommandText, string CreatedAt, string? StartedAt, string? CompletedAt,
        string? FinalState, string? Route, string? StopReason, string? ErrorCode);

    internal sealed record ActionHistory(int ActionId, int StepIndex, string Tool, string? Adapter,
        string Risk, string? ApprovalState, string StartedAt, string? EndedAt, double? DurationMs,
        JsonElement Arguments, JsonElement? Result, bool Verified, JsonElement? Verification,
        JsonElement? Error, bool UndoAvailable, bool RollbackAttempted, bool? RollbackOk,
        JsonElement? RollbackResult);

    internal sealed record HistoryReply(int ProtocolVersion, string MessageType, string RequestId,
        string? TaskId, TaskSummary[] Tasks, ActionHistory[] Actions)
    {
        internal static HistoryReply Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<HistoryReply>(message.ToArray(), Options)
                ?? throw new JsonException("Empty history response.");
            if (value.ProtocolVersion != Version || value.MessageType != "history_reply" ||
                value.Tasks is null || value.Actions is null || value.Tasks.Length > 100 || value.Actions.Length > 100 ||
                value.Tasks.Any(item => item is null) || value.Actions.Any(item => item is null))
                throw new JsonException("Unsupported history response envelope.");
            RequireId(value.RequestId, "request_id");
            if (value.TaskId is not null)
            {
                RequireId(value.TaskId, "task_id");
                if (value.Tasks.Length > 1 || value.Tasks.Any(item => item.TaskId != value.TaskId))
                    throw new JsonException("Task history does not match the requested task.");
            }
            else if (value.Actions.Length != 0) throw new JsonException("Recent history contains unscoped actions.");
            foreach (TaskSummary task in value.Tasks)
            {
                RequireId(task.TaskId, "task_id"); RequireId(task.RequestId, "request_id");
                if (task.InputMode is not ("text" or "voice") || string.IsNullOrWhiteSpace(task.CommandText) ||
                    string.IsNullOrWhiteSpace(task.CreatedAt))
                    throw new JsonException("Invalid task history summary.");
            }
            if (value.Actions.Any(item => item.ActionId < 1 || item.StepIndex < 0 ||
                string.IsNullOrWhiteSpace(item.Tool) || string.IsNullOrWhiteSpace(item.Risk) ||
                string.IsNullOrWhiteSpace(item.StartedAt) || item.DurationMs is < 0 ||
                item.Arguments.ValueKind != JsonValueKind.Object))
                throw new JsonException("Invalid action history summary.");
            return value;
        }
    }

    internal sealed record StopAck(int ProtocolVersion, string MessageType, string RequestId,
        string Status, string StopContract, string Message, string? ErrorCode,
        JsonElement[] Tasks, string[] StoppedTasks, int StoppedCount, int LatchAcknowledgedCount)
    {
        internal static StopAck Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<StopAck>(message.ToArray(), Options)
                ?? throw new JsonException("Empty STOP acknowledgement.");
            if (value.ProtocolVersion != Version || value.MessageType != "stop_ack" ||
                value.StopContract != "pluma.stop.v1" || value.Status is not ("ok" or "error"))
                throw new JsonException("Unsupported STOP acknowledgement envelope.");
            RequireId(value.RequestId, "request_id");
            if (value.StoppedCount != value.StoppedTasks.Length || value.StoppedCount < 0 || value.LatchAcknowledgedCount < 0)
                throw new JsonException("Inconsistent STOP acknowledgement counts.");
            return value;
        }
    }

    internal sealed record SubmissionAck(int ProtocolVersion, string MessageType, string RequestId,
        bool Accepted, string? TaskId, string? ErrorCode, string Message)
    {
        internal static SubmissionAck Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<SubmissionAck>(message, Options)
                ?? throw new JsonException("Empty acknowledgement.");
            if (value.ProtocolVersion != Version || value.MessageType != "submission_ack")
                throw new JsonException("Unsupported acknowledgement envelope.");
            RequireId(value.RequestId, "request_id");
            if ((value.Accepted && (value.TaskId is null || value.ErrorCode is not null)) ||
                (!value.Accepted && (value.TaskId is not null || string.IsNullOrWhiteSpace(value.ErrorCode))) ||
                string.IsNullOrWhiteSpace(value.Message))
                throw new JsonException("Inconsistent acknowledgement.");
            if (value.TaskId is not null) RequireId(value.TaskId, "task_id");
            return value;
        }
    }

    internal sealed record ProtocolError(int ProtocolVersion, string MessageType, string ErrorCode, string Message)
    {
        internal static ProtocolError Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<ProtocolError>(message.ToArray(), Options)
                ?? throw new JsonException("Empty protocol error.");
            if (value.ProtocolVersion != Version || value.MessageType != "protocol_error" ||
                string.IsNullOrWhiteSpace(value.ErrorCode) || string.IsNullOrWhiteSpace(value.Message))
                throw new JsonException("Invalid protocol error envelope.");
            return value;
        }
    }

    internal sealed record TerminalReadback(int ProtocolVersion, string MessageType, string RequestId,
        string TaskId, bool Terminal, string FinalState, bool CompletionVerified,
        bool? TerminalPersisted, bool HasResidual, string? Route, string Message, double? DurationMs)
    {
        internal static TerminalReadback Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<TerminalReadback>(message, Options)
                ?? throw new JsonException("Empty terminal readback.");
            if (value.ProtocolVersion != Version || value.MessageType != "terminal_readback")
                throw new JsonException("Unsupported terminal envelope.");
            RequireId(value.RequestId, "request_id"); RequireId(value.TaskId, "task_id");
            if (string.IsNullOrWhiteSpace(value.FinalState) || string.IsNullOrWhiteSpace(value.Message) ||
                (!value.Terminal && value.TerminalPersisted is not null) ||
                (value.CompletionVerified && !value.Terminal) ||
                (value.DurationMs is < 0))
                throw new JsonException("Inconsistent terminal readback.");
            return value;
        }
    }

    private sealed record SubmitEnvelope(int protocol_version, string message_type, string request_id, string text);
    private sealed record ReadbackEnvelope(int protocol_version, string message_type, string request_id, string task_id);
    private sealed record StopEnvelope(int protocol_version, string message_type, string request_id, string? task_id);
    private sealed record SettingsEnvelope(int protocol_version, string message_type, string request_id);
    private sealed record HistoryEnvelope(int protocol_version, string message_type, string request_id,
        string? task_id, int limit);

    private static void RequireId(string value, string name)
    {
        if (!Guid.TryParseExact(value, "D", out Guid id) || id.ToString("D") != value)
            throw new JsonException($"{name} must be a canonical lowercase UUID.");
    }

    private static void RejectDuplicateProperties(ReadOnlySpan<byte> message)
    {
        using JsonDocument document = JsonDocument.Parse(message.ToArray(), new JsonDocumentOptions { MaxDepth = 8 });
        if (document.RootElement.ValueKind != JsonValueKind.Object) throw new JsonException("Expected object.");
        var names = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
        foreach (JsonProperty property in document.RootElement.EnumerateObject())
            if (!names.Add(property.Name)) throw new JsonException("Duplicate property.");
    }
}
