using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record ConfirmationQueryRequest(string RequestId, string ClientId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(ClientId, "client_id");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "confirmation_query", request_id = RequestId, client_id = ClientId }, Options);
        }
    }

    internal sealed record ConfirmationDecisionRequest(string RequestId, string ClientId,
        string TaskId, string ConfirmationId, string Binding, bool Approved)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(ClientId, "client_id");
            RequireId(TaskId, "task_id"); RequireId(ConfirmationId, "confirmation_id"); RequireBinding(Binding);
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "confirmation_decision", request_id = RequestId, client_id = ClientId,
                task_id = TaskId, confirmation_id = ConfirmationId, binding = Binding, approved = Approved }, Options);
        }
    }

    internal sealed record ConfirmationDisconnectRequest(string RequestId, string ClientId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireId(ClientId, "client_id");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "confirmation_disconnect", request_id = RequestId, client_id = ClientId }, Options);
        }
    }

    internal sealed record EventsQueryRequest(string RequestId, string? StreamId = null, long AfterSequence = 0, int Limit = 100)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id");
            if (StreamId is not null) RequireId(StreamId, "stream_id");
            if (AfterSequence < 0 || (StreamId is null && AfterSequence != 0) || Limit is < 1 or > 100)
                throw new ArgumentException("Invalid event cursor bounds.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "events_query", request_id = RequestId, stream_id = StreamId,
                after_sequence = AfterSequence, limit = Limit }, Options);
        }
    }

    internal sealed record ConfirmationView([property: JsonRequired] string ConfirmationId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string Binding,
        [property: JsonRequired] string Tool, [property: JsonRequired] string Risk,
        [property: JsonRequired] JsonElement Arguments, [property: JsonRequired] string Prompt,
        [property: JsonRequired] string? TargetSummary, [property: JsonRequired] string ExpiresAt);

    internal sealed record ConfirmationList([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string ClientId, [property: JsonRequired] ConfirmationView[] Confirmations)
    {
        internal static ConfirmationList Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ConfirmationList>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "confirmation_list", value.RequestId);
            RequireId(value.ClientId, "client_id");
            if (value.Confirmations is null || value.Confirmations.Length > 32 || value.Confirmations.Any(x => x is null))
                throw new JsonException("Invalid confirmation list.");
            foreach (var item in value.Confirmations)
            {
                RequireId(item.ConfirmationId, "confirmation_id"); RequireId(item.TaskId, "task_id"); RequireBinding(item.Binding);
                if (item.Risk is not ("MEDIUM" or "HIGH") || string.IsNullOrWhiteSpace(item.Tool) ||
                    string.IsNullOrWhiteSpace(item.Prompt) || item.Arguments.ValueKind != JsonValueKind.Object ||
                    !DateTimeOffset.TryParse(item.ExpiresAt, out _)) throw new JsonException("Invalid material confirmation.");
            }
            if (value.Confirmations.Select(x => x.ConfirmationId).Distinct().Count() != value.Confirmations.Length)
                throw new JsonException("Duplicate confirmation identity.");
            return value;
        }
    }

    internal sealed record ConfirmationAck([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string ConfirmationId, [property: JsonRequired] bool Accepted,
        [property: JsonRequired] bool? Approved, [property: JsonRequired] string? ErrorCode)
    {
        internal static ConfirmationAck Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ConfirmationAck>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "confirmation_ack", value.RequestId);
            RequireId(value.ConfirmationId, "confirmation_id");
            if (value.Accepted ? value.Approved is null || value.ErrorCode is not null
                : value.Approved is not null || string.IsNullOrWhiteSpace(value.ErrorCode))
                throw new JsonException("Inconsistent confirmation acknowledgement.");
            return value;
        }
    }

    internal sealed record ConfirmationDisconnected([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string ClientId, [property: JsonRequired] int DeniedCount)
    {
        internal static ConfirmationDisconnected Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<ConfirmationDisconnected>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "confirmation_disconnected", value.RequestId);
            RequireId(value.ClientId, "client_id");
            if (value.DeniedCount is < 0 or > 32) throw new JsonException("Invalid disconnect count.");
            return value;
        }
    }

    internal sealed record LedgerEvent([property: JsonRequired] long Sequence,
        [property: JsonRequired] string Kind, [property: JsonRequired] string OccurredAt,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string? RequestId,
        [property: JsonRequired] long? RecordId);

    internal sealed record EventBatch([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string StreamId, [property: JsonRequired] long FirstSequence,
        [property: JsonRequired] long LastSequence, [property: JsonRequired] long NextSequence,
        [property: JsonRequired] bool ResetRequired, [property: JsonRequired] bool HasMore,
        [property: JsonRequired] LedgerEvent[] Events)
    {
        internal static EventBatch Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<EventBatch>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "event_batch", value.RequestId);
            RequireId(value.StreamId, "stream_id");
            if (value.FirstSequence < 0 || value.LastSequence < value.FirstSequence || value.NextSequence < 0 ||
                value.NextSequence > value.LastSequence || value.Events is null || value.Events.Length > 100 ||
                value.Events.Any(x => x is null) ||
                (value.ResetRequired && (value.Events.Length != 0 || value.NextSequence != value.LastSequence || value.HasMore)))
                throw new JsonException("Invalid event batch bounds.");
            if (!value.ResetRequired && (value.HasMore != (value.NextSequence < value.LastSequence) ||
                (value.HasMore && value.Events.Length == 0))) throw new JsonException("Inconsistent event batch continuation.");
            long previous = 0;
            foreach (var item in value.Events)
            {
                RequireId(item.TaskId, "task_id");
                if (item.RequestId is not null) RequireId(item.RequestId, "request_id");
                if (item.Sequence <= previous || item.Sequence < value.FirstSequence || item.Sequence > value.LastSequence ||
                    item.RecordId is < 1 || !DateTimeOffset.TryParse(item.OccurredAt, out _) ||
                    item.Kind is not ("task_recorded" or "task_changed" or "action_recorded" or "action_changed" or
                    "rollback_changed" or "cleanup_recorded" or "resource_changed" or "screen_recorded"))
                    throw new JsonException("Invalid or out-of-order factual event.");
                previous = item.Sequence;
            }
            if (value.Events.Length > 0 && value.NextSequence != previous)
                throw new JsonException("Event cursor differs from the delivered tail.");
            return value;
        }
    }

    private static T ReadContract<T>(ReadOnlySpan<byte> message) where T : class
    {
        RejectDuplicateProperties(message);
        return JsonSerializer.Deserialize<T>(message.ToArray(), Options) ?? throw new JsonException("Empty contract response.");
    }
    private static void Envelope(int version, string type, string expected, string request)
    {
        if (version != Version || type != expected) throw new JsonException("Unsupported contract envelope.");
        RequireId(request, "request_id");
    }
    private static void RequireBinding(string value)
    {
        if (value is null || value.Length != 64 || value.Any(x => !(x is >= '0' and <= '9' or >= 'a' and <= 'f')))
            throw new JsonException("Invalid exact-call binding.");
    }
}

/// <summary>One serialized consumer per cursor; no polling worker or cached UI state.</summary>
internal sealed class CoreEventCursor
{
    internal string? StreamId { get; private set; }
    internal long Sequence { get; private set; }
    internal bool RequiresSnapshot { get; private set; }

    internal CoreRequestProtocol.LedgerEvent[] Apply(CoreRequestProtocol.EventBatch batch)
    {
        if (batch.ResetRequired)
        {
            StreamId = batch.StreamId; Sequence = batch.NextSequence; RequiresSnapshot = true;
            return [];
        }
        if (StreamId != batch.StreamId || RequiresSnapshot) throw new JsonException("Read a fresh snapshot before applying events.");
        var fresh = batch.Events.Where(x => x.Sequence > Sequence).ToArray();
        long next = Sequence;
        foreach (var item in fresh)
            if (item.Sequence != ++next) throw new JsonException("Event gap requires resynchronization.");
        if (fresh.Length > 0 && next != batch.NextSequence) throw new JsonException("Inconsistent event tail.");
        if (fresh.Length == 0 && batch.NextSequence > Sequence) throw new JsonException("Missing event payload.");
        Sequence = Math.Max(Sequence, next);
        return fresh;
    }

    // The consumer calls this only after history/terminal/pending-query readback.
    internal void SnapshotRead() => RequiresSnapshot = false;
}
