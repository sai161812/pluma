using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace PLUMA.UI;

// Observation transport only. No rendering, capture, action or success authority.
internal static partial class CoreRequestProtocol
{
    internal sealed record PerceptionRequest(string RequestId)
    {
        internal byte[] ToMessage()
        {RequireId(RequestId,"request_id");return JsonSerializer.SerializeToUtf8Bytes(new{
            protocol_version=Version,message_type="perception_query",request_id=RequestId},Options);}
    }
    internal sealed record PerceptionBounds([property:JsonRequired] int Left,[property:JsonRequired] int Top,
        [property:JsonRequired] int Right,[property:JsonRequired] int Bottom)
    {
        internal long Width=>(long)Right-Left;
        internal long Height=>(long)Bottom-Top;
        internal void Validate(){if(Width<=0||Height<=0||Width>int.MaxValue||Height>int.MaxValue)throw new JsonException("Invalid observation bounds.");}
        internal bool Contains(PerceptionBounds other)=>Left<=other.Left&&Top<=other.Top&&other.Right<=Right&&other.Bottom<=Bottom;
    }
    internal sealed record PerceptionMatch([property:JsonRequired] string ElementId,
        [property:JsonRequired] PerceptionBounds Bounds,[property:JsonRequired] double Confidence);
    internal sealed record PerceptionObservation([property:JsonRequired] string TaskId,[property:JsonRequired] string TaskRequestId,
        [property:JsonRequired] long Sequence,[property:JsonRequired] string ObservationId,[property:JsonRequired] string SnapshotId,
        [property:JsonRequired] long Hwnd,[property:JsonRequired] int Pid,[property:JsonRequired] long CreationTime,
        [property:JsonRequired] string WindowClass,[property:JsonRequired] string TitleHash,
        [property:JsonRequired] PerceptionBounds WindowBounds,[property:JsonRequired] double DpiScale,
        [property:JsonRequired] PerceptionBounds Region,[property:JsonRequired] string ObservedUtc,[property:JsonRequired] string ExpiresUtc,
        [property:JsonRequired] string MatchState,[property:JsonRequired] PerceptionMatch? Match,
        [property:JsonRequired] bool RequiresTargetRevalidation)
    {
        internal void Validate()
        {
            RequireId(TaskId,"task_id");RequireId(TaskRequestId,"task_request_id");
            RequireId(ObservationId,"observation_id");RequireId(SnapshotId,"snapshot_id");
            if(Sequence<=0||Hwnd<=0||Pid<=0||CreationTime<=0||string.IsNullOrEmpty(WindowClass)||WindowClass.Length>256||
                !Regex.IsMatch(TitleHash??"",@"\Asha256:[0-9a-f]{64}\z")||!RequiresTargetRevalidation||
                !double.IsFinite(DpiScale)||DpiScale<.25||DpiScale>8||WindowBounds is null||Region is null||
                !DateTimeOffset.TryParse(ObservedUtc,out var observed)||!DateTimeOffset.TryParse(ExpiresUtc,out var expires)||
                observed.Offset!=TimeSpan.Zero||expires.Offset!=TimeSpan.Zero||expires<=observed||expires-observed>TimeSpan.FromSeconds(3)||
                MatchState is not ("NOT_REQUESTED" or "NONE" or "UNIQUE" or "AMBIGUOUS")||
                (MatchState=="UNIQUE")!=(Match is not null))throw new JsonException("Invalid perception observation.");
            WindowBounds.Validate();Region.Validate();
            if(!new PerceptionBounds(0,0,(int)WindowBounds.Width,(int)WindowBounds.Height).Contains(Region))throw new JsonException("Observation outside target.");
            if(Match is {} match)
            {
                RequireId(match.ElementId,"element_id");
                if(match.Bounds is null||!double.IsFinite(match.Confidence)||match.Confidence<0||match.Confidence>1)throw new JsonException("Invalid observed match.");
                match.Bounds.Validate();if(!Region.Contains(match.Bounds))throw new JsonException("Match outside captured region.");
            }
        }
    }
    internal sealed record PerceptionSnapshot([property:JsonRequired] int ProtocolVersion,[property:JsonRequired] string MessageType,
        [property:JsonRequired] string RequestId,[property:JsonRequired] PerceptionObservation[] Observations)
    {
        internal static PerceptionSnapshot Parse(ReadOnlySpan<byte> bytes)
        {
            var value=ReadContract<PerceptionSnapshot>(bytes);Envelope(value.ProtocolVersion,value.MessageType,"perception_snapshot",value.RequestId);
            if(value.Observations is null||value.Observations.Length>256||value.Observations.Any(o=>o is null)||
                value.Observations.Select(o=>o.TaskId).Distinct().Count()!=value.Observations.Length)throw new JsonException("Invalid perception task set.");
            foreach(var item in value.Observations)item.Validate();
            return value;
        }
    }
}
