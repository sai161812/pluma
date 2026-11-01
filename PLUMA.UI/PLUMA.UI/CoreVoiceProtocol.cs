using System;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record VoiceRequest(string RequestId, string? StreamId = null, string? VoiceId = null)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id");
            if (StreamId is not null) RequireId(StreamId, "stream_id");
            if (VoiceId is not null) RequireId(VoiceId, "voice_id");
            if (VoiceId is not null && StreamId is null) throw new ArgumentException("Voice generation requires its stream.");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "voice_query", request_id = RequestId, stream_id = StreamId, voice_id = VoiceId }, Options);
        }
    }

    internal sealed record VoiceView([property: JsonRequired] string VoiceId,
        [property: JsonRequired] string TaskId, [property: JsonRequired] string? TaskRequestId,
        [property: JsonRequired] string Phase, [property: JsonRequired] string? Code,
        [property: JsonRequired] bool? CaptureActive, [property: JsonRequired] bool? BoundaryComplete,
        [property: JsonRequired] string? RecognitionId, [property: JsonRequired] int RecognitionSequence,
        [property: JsonRequired] string Text);

    internal sealed record VoiceSnapshot([property: JsonRequired] int ProtocolVersion,
        [property: JsonRequired] string MessageType, [property: JsonRequired] string RequestId,
        [property: JsonRequired] string StreamId, [property: JsonRequired] bool ResetRequired,
        [property: JsonRequired] VoiceView? Voice)
    {
        internal static VoiceSnapshot Parse(ReadOnlySpan<byte> message)
        {
            var value = ReadContract<VoiceSnapshot>(message);
            Envelope(value.ProtocolVersion, value.MessageType, "voice_snapshot", value.RequestId);
            RequireId(value.StreamId, "stream_id");
            if (value.Voice is not { } voice) return value;
            RequireId(voice.VoiceId, "voice_id"); RequireId(voice.TaskId, "task_id");
            if (voice.TaskRequestId is not null) RequireId(voice.TaskRequestId, "task_request_id");
            if (voice.RecognitionId is not null) RequireId(voice.RecognitionId, "recognition_id");
            if (voice.Phase is not ("STARTING" or "LISTENING" or "DECODING" or "COMMITTED" or "CLARIFICATION" or
                    "EMPTY" or "ERROR" or "CANCELLED" or "TIMED_OUT") ||
                (voice.Phase == "COMMITTED") != (voice.TaskRequestId is not null) ||
                voice.Text is null || Encoding.UTF8.GetByteCount(voice.Text) > 16384 ||
                voice.Phase is not ("DECODING" or "COMMITTED") && voice.Text.Length != 0 ||
                voice.Phase != "LISTENING" && (voice.CaptureActive is not null || voice.BoundaryComplete is not null) ||
                voice.RecognitionSequence is < 0 or > 128 || voice.RecognitionId is null && voice.RecognitionSequence != 0 ||
                (voice.Phase == "CLARIFICATION") != (voice.Code == "LOW_CONFIDENCE_MATERIAL_TARGET") ||
                voice.Phase == "ERROR" && voice.Code is not ("CAPTURE_DENIED" or "CAPTURE_UNAVAILABLE" or "VOICE_FAILED") ||
                voice.Phase is not ("ERROR" or "CLARIFICATION") && voice.Code is not null)
                throw new JsonException("Inconsistent voice evidence.");
            return value;
        }
    }
}
