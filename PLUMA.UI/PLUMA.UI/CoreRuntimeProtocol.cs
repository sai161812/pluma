using System;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record VerificationRequest(string RequestId, string TaskId, long ActionId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(TaskId, "task_id");
            if (ActionId <= 0) throw new ArgumentException("Invalid verification action.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "action_verification_query", request_id = RequestId, task_id = TaskId, action_id = ActionId }, Options);
        }
    }
    internal sealed record ActionVerification([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string TaskRequestId,
        [property: JsonRequired] long ActionId, [property: JsonRequired] string Tool,
        [property: JsonRequired] bool? Verified, [property: JsonRequired] string? Method,
        [property: JsonRequired] string? Detail)
    {
        internal static ActionVerification Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ActionVerification>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "action_verification", value.RequestId);
            RequireId(value.TaskId, "task_id"); RequireId(value.TaskRequestId, "task_request_id");
            if (value.ActionId <= 0 || value.Tool is null || !System.Text.RegularExpressions.Regex.IsMatch(value.Tool, @"\A[a-z][a-z0-9_]{0,63}\z") ||
                (value.Verified is null) != (value.Method is null) || (value.Method is null) != (value.Detail is null) ||
                value.Method is not null && !System.Text.RegularExpressions.Regex.IsMatch(value.Method, @"\A[A-Za-z][A-Za-z0-9_]{0,63}\z") ||
                value.Detail is not null && Encoding.UTF8.GetByteCount(value.Detail) > 1024)
                throw new JsonException("Invalid saved verifier proof.");
            return value;
        }
    }
    internal sealed record RuntimeRequest(string RequestId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "runtime_query", request_id = RequestId }, Options);
        }
    }
    internal sealed record RuntimeTask([property: JsonRequired] string TaskId,
        [property: JsonRequired] string TaskRequestId, [property: JsonRequired] string State,
        [property: JsonRequired] long ElapsedMs, [property: JsonRequired] int PlanRevision,
        [property: JsonRequired] int? Step, [property: JsonRequired] int? Total,
        [property: JsonRequired] string? Tool, [property: JsonRequired] string? Risk,
        [property: JsonRequired] string? Phase, [property: JsonRequired] long? ToolElapsedMs,
        [property: JsonRequired] string? Arguments, [property: JsonRequired] int? RollbackStep,
        [property: JsonRequired] int? RollbackTotal, [property: JsonRequired] string? RollbackRecipe);
    internal sealed record WorkerTermination([property: JsonRequired] string TaskId,
        [property: JsonRequired] string TaskRequestId, [property: JsonRequired] long Pid,
        [property: JsonRequired] long CreationTime, [property: JsonRequired] long ExitCode,
        [property: JsonRequired] string CommandClass)
    {
        internal string Key => $"worker-{TaskId}-{Pid}-{CreationTime}";
    }
    internal sealed record RuntimeSnapshot([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] RuntimeTask[] Tasks, [property: JsonRequired] WorkerTermination[] Terminations,
        string? TextActivationId=null, string? TextActivationUtc=null,string? CoreInstanceId=null,bool? CoreReady=null)
    {
        internal static RuntimeSnapshot Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<RuntimeSnapshot>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "runtime_snapshot", value.RequestId);
            if((value.CoreInstanceId is null)!=(value.CoreReady is null))throw new JsonException("Partial Core identity.");
            if(value.CoreInstanceId is not null)RequireId(value.CoreInstanceId,"core_instance_id");
            if((value.TextActivationId is null)!=(value.TextActivationUtc is null))throw new JsonException("Partial text activation.");
            if(value.TextActivationId is not null)
            {
                RequireId(value.TextActivationId,"text_activation_id");
                if(!System.Text.RegularExpressions.Regex.IsMatch(value.TextActivationUtc!,@"(?:Z|[+-]\d{2}:\d{2})$",System.Text.RegularExpressions.RegexOptions.CultureInvariant) ||
                    !DateTimeOffset.TryParse(value.TextActivationUtc,System.Globalization.CultureInfo.InvariantCulture,
                    System.Globalization.DateTimeStyles.RoundtripKind,out _))throw new JsonException("Invalid activation time.");
            }
            if (value.Terminations is null || value.Terminations.Length > 256 ||
                value.Terminations.Any(t => t is null) || value.Terminations.Select(t => t.Key).Distinct().Count() != value.Terminations.Length)
                throw new JsonException("Invalid termination proof set.");
            foreach (var proof in value.Terminations)
            {
                RequireId(proof.TaskId, "task_id"); RequireId(proof.TaskRequestId, "task_request_id");
                if (proof.Pid <= 0 || proof.CreationTime <= 0 || proof.CommandClass != "tool_worker")
                    throw new JsonException("Invalid owned termination evidence.");
            }
            if (value.Tasks is null || value.Tasks.Length > 256 || value.Tasks.Select(t => t?.TaskId).Distinct().Count() != value.Tasks.Length)
                throw new JsonException("Invalid runtime task set.");
            foreach (var task in value.Tasks)
            {
                if (task is null) throw new JsonException("Missing runtime task.");
                RequireId(task.TaskId, "task_id"); RequireId(task.TaskRequestId, "task_request_id");
                bool ValidName(string? text) => text is null || System.Text.RegularExpressions.Regex.IsMatch(text, @"\A[a-z][a-z0-9_]{0,63}\z");
                if (task.State is not ("CREATED" or "RUNNING" or "STOPPING" or "ROLLING_BACK") ||
                    task.ElapsedMs < 0 || task.PlanRevision < 0 || task.Step is < 1 || task.Total is < 1 ||
                    task.Step is not null && (task.Total is null || task.Step > task.Total) ||
                    !ValidName(task.Tool) || !ValidName(task.RollbackRecipe) ||
                    task.Risk is not (null or "READ" or "LOW" or "MEDIUM" or "HIGH" or "ADMIN" or "DENY") ||
                    task.Phase is not (null or "DISPATCHING" or "EXECUTING" or "VERIFYING" or "RECORDING") ||
                    (task.Tool is null) != (task.Phase is null) || (task.Tool is null) != (task.Risk is null) ||
                    task.ToolElapsedMs is < 0 || task.Phase == "DISPATCHING" && task.ToolElapsedMs is not null ||
                    task.Phase == "EXECUTING" && task.ToolElapsedMs is null ||
                    task.Arguments is not null && Encoding.UTF8.GetByteCount(task.Arguments) > 1024 ||
                    task.RollbackStep is < 1 || task.RollbackTotal is < 1 ||
                    task.RollbackStep is not null && (task.RollbackTotal is null || task.RollbackStep > task.RollbackTotal))
                    throw new JsonException("Inconsistent runtime evidence.");
            }
            return value;
        }
    }
}
