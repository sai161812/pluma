using System;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record SavedDetailRequest(string RequestId, string TaskId, long After)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(TaskId, "task_id");
            if (After < 0) throw new ArgumentException("Invalid action cursor.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version=1, message_type="task_detail_query",
                request_id=RequestId, task_id=TaskId, after_action_id=After, limit=10 }, Options);
        }
    }
    internal sealed record UndoSubmission(string RequestId, UndoSelection Selection)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); Selection.Validate();
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version=1, message_type="undo_submit",
                request_id=RequestId, selection=Selection }, Options);
        }
    }
    internal sealed record FolderSelection(string TaskId, long ActionId, string Location)
    {
        internal byte[] ToMessage(string request)
        {
            RequireId(request, "request_id"); RequireId(TaskId, "task_id");
            if (ActionId < 1 || Location is not ("current" or "target")) throw new ArgumentException("Invalid folder selection.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version=1, message_type="history_folder_submit",
                request_id=request, task_id=TaskId, action_id=ActionId, location=Location }, Options);
        }
    }
    internal sealed record UndoSelection([property: JsonRequired] string TargetTaskId,
        [property: JsonRequired] long ActionId, [property: JsonRequired] string Revision,
        [property: JsonRequired] string Material)
    {
        internal void Validate()
        {
            RequireId(TargetTaskId, "target_task_id"); RequireBinding(Revision);
            if (ActionId < 1 || string.IsNullOrWhiteSpace(Material) || Encoding.UTF8.GetByteCount(Material) > 4096)
                throw new JsonException("Invalid saved selection.");
        }
    }
    internal sealed record SavedAction([property: JsonRequired] long ActionId,
        [property: JsonRequired] int StepIndex, [property: JsonRequired] string Tool,
        [property: JsonRequired] string Arguments, [property: JsonRequired] string? Adapter,
        [property: JsonRequired] string Risk, [property: JsonRequired] string? Approval,
        [property: JsonRequired] string? StartedAt, [property: JsonRequired] string? EndedAt,
        [property: JsonRequired] double? DurationMs, [property: JsonRequired] string? FactualMessage,
        [property: JsonRequired] string? PolicyReason, [property: JsonRequired] string? ErrorCode,
        [property: JsonRequired] bool Verified, [property: JsonRequired] string? VerificationMethod,
        [property: JsonRequired] string? VerificationDetail, [property: JsonRequired] bool UndoAvailable,
        [property: JsonRequired] bool RollbackAttempted, [property: JsonRequired] bool? RollbackOk,
        [property: JsonRequired] string? RollbackCode, [property: JsonRequired] string? ClaimState, [property: JsonRequired] string? EffectState, [property: JsonRequired] string? ConflictCurrent,
        [property: JsonRequired] string? ConflictTarget, [property: JsonRequired] UndoSelection? Selection);

    internal sealed record SavedTaskDetail([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string TaskRequestId,
        [property: JsonRequired] string? OriginalTranscript, [property: JsonRequired] string? ActiveProcess,
        [property: JsonRequired] string? ActiveWindow, [property: JsonRequired] bool? CleanupComplete,
        [property: JsonRequired] int? CleanupUnresolved, [property: JsonRequired] string[] ResidualCodes, [property: JsonRequired] SavedAction[] Actions,
        [property: JsonRequired] bool HasMore, [property: JsonRequired] long NextActionId)
    {
        internal static SavedTaskDetail Parse(ReadOnlySpan<byte> bytes)
        {
            var value = ReadContract<SavedTaskDetail>(bytes);
            Envelope(value.ProtocolVersion, value.MessageType, "task_detail", value.RequestId);
            RequireId(value.TaskId, "task_id"); RequireId(value.TaskRequestId, "task_request_id");
            static bool Bounded(string? text, int max) => text is null || Encoding.UTF8.GetByteCount(text) <= max;
            static bool Code(string? text) => text is null || System.Text.RegularExpressions.Regex.IsMatch(text, @"\A[A-Za-z][A-Za-z0-9_]{0,63}\z");
            if (!Bounded(value.OriginalTranscript, 8192) || !Bounded(value.ActiveProcess, 2048) || !Bounded(value.ActiveWindow, 2048) ||
                value.CleanupUnresolved is < 0 or > 512 || (value.CleanupComplete is null) != (value.CleanupUnresolved is null) ||
                value.CleanupComplete is not null && value.CleanupComplete != (value.CleanupUnresolved == 0) ||
                value.ResidualCodes is null || value.ResidualCodes.Length > 512 || value.ResidualCodes.Any(c => c is null || !Code(c)) ||
                value.CleanupUnresolved is int count && count != value.ResidualCodes.Length ||
                value.Actions is null || value.Actions.Length > 10 || value.Actions.Any(a => a is null) ||
                value.HasMore && value.Actions.Length == 0 || value.NextActionId < 0 ||
                value.Actions.Length > 0 && value.NextActionId != value.Actions[^1].ActionId)
                throw new JsonException("Inconsistent saved detail.");
            static bool Time(string? value) => value is null || value.Length <= 64 &&
                DateTimeOffset.TryParse(value, System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out _) &&
                (value.EndsWith("Z",StringComparison.Ordinal) || System.Text.RegularExpressions.Regex.IsMatch(value,@"[+-]\d{2}:\d{2}$"));
            long previous = 0;
            foreach (var action in value.Actions)
            {
                if (action.ActionId <= previous || action.StepIndex < 0 || !Code(action.Tool) || action.Tool is null ||
                    !Time(action.StartedAt) || !Time(action.EndedAt) || !Code(action.Adapter) || !Code(action.Approval) || !Code(action.ErrorCode) || !Code(action.RollbackCode) || !Code(action.VerificationMethod) ||
                    action.Risk is not ("READ" or "LOW" or "MEDIUM" or "HIGH" or "ADMIN" or "DENY") ||
                    action.Arguments is null || !Bounded(action.Arguments, 65536) || !Bounded(action.FactualMessage, 2048) ||
                    !Bounded(action.PolicyReason, 2048) || !Bounded(action.VerificationDetail, 2048) ||
                    action.DurationMs is double duration && (!double.IsFinite(duration) || duration < 0) ||
                    action.ClaimState is not (null or "claimed" or "verified" or "unverified") ||
                    action.EffectState is not (null or "committed" or "unknown" or "not_executed") ||
                    !action.RollbackAttempted && action.RollbackOk is not null ||
                    !Bounded(action.ConflictCurrent, 2048) || !Bounded(action.ConflictTarget, 2048) ||
                    (action.ConflictCurrent is not null || action.ConflictTarget is not null) && (!action.RollbackAttempted || action.RollbackOk is not false) ||
                    action.Selection is not null && (!action.UndoAvailable || action.ClaimState is not null ||
                        action.Selection.TargetTaskId != value.TaskId || action.Selection.ActionId != action.ActionId || value.CleanupComplete is not true))
                    throw new JsonException("Invalid saved action.");
                using var arguments = JsonDocument.Parse(action.Arguments);
                if (arguments.RootElement.ValueKind != JsonValueKind.Object) throw new JsonException("Invalid saved arguments.");
                action.Selection?.Validate(); previous = action.ActionId;
            }
            return value;
        }
    }
}
