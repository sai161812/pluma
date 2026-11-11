using System;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;

namespace PLUMA.UI;

internal static class CoreHealthProtocol
{
    private static readonly JsonSerializerOptions Json=new(){PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower,
        UnmappedMemberHandling=JsonUnmappedMemberHandling.Disallow,MaxDepth=8};
    internal sealed record Check(string Id,string State,string Code,string Origin);
    internal sealed record Snapshot(int ProtocolVersion,string MessageType,string RequestId,string InstanceId,int Pid,long CreationTime,
        string State,string Code,bool CanRestart,string Fingerprint,Check[] Checks,bool NativeVerified,bool HotkeysRegistered,
        bool SetupReady,int StaleTasksRecovered)
    {
        internal static Snapshot Parse(ReadOnlySpan<byte> bytes)
        {
            using var document=JsonDocument.Parse(bytes.ToArray());
            ValidateFields(document.RootElement);
            // Record defaults may not silently substitute for missing safety evidence.
            foreach(var key in new[]{"protocol_version","message_type","request_id","instance_id","pid","creation_time","state","code",
                "can_restart","fingerprint","checks","native_verified","hotkeys_registered","setup_ready","stale_tasks_recovered"})
                if(!document.RootElement.TryGetProperty(key,out _))throw new JsonException("Missing health evidence.");
            var value=JsonSerializer.Deserialize<Snapshot>(bytes,Json)??throw new JsonException();
            Id(value.RequestId);Id(value.InstanceId);
            if(value.ProtocolVersion!=1||value.MessageType!="health_snapshot"||value.Pid<=0||value.CreationTime<=0||value.StaleTasksRecovered<0||
                !new[]{"STARTING","READY","RESTARTING","CONFIGURATION_ERROR","HOTKEY_ERROR","RECOVERY_ERROR","STOPPED"}.Contains(value.State)||
                !Regex.IsMatch(value.Code??"",@"\A[A-Z][A-Z0-9_]{0,63}\z")||!Regex.IsMatch(value.Fingerprint??"",@"\Asha256:[0-9a-f]{64}\z")||
                value.Checks is null||value.Checks.Length>5||value.Checks.Select(c=>c?.Id).Distinct().Count()!=value.Checks.Length)
                throw new JsonException("Invalid health evidence.");
            foreach(var check in value.Checks)
                if(check is null||!new[]{"planner","speech","ocr","uia","microphone"}.Contains(check.Id)||
                    !new[]{"PASSED","FAILED","UNVERIFIED"}.Contains(check.State)||!new[]{"native","fixture"}.Contains(check.Origin)||
                    !Regex.IsMatch(check.Code??"",@"\A[A-Z][A-Z0-9_]{0,63}\z"))throw new JsonException("Invalid capability evidence.");
            bool native=value.Checks.Length==5&&value.Checks.All(c=>c.Origin=="native");
            if(value.NativeVerified&&!native||value.SetupReady!=(value.State=="READY"&&value.NativeVerified&&value.HotkeysRegistered&&value.Checks.Length==5&&value.Checks.All(c=>c.State=="PASSED")))
                throw new JsonException("Contradictory setup readiness.");
            return value;
        }
    }
    private static void ValidateFields(JsonElement element)
    {
        if(element.ValueKind==JsonValueKind.Object)
        {
            var fields=element.EnumerateObject().ToArray();
            if(fields.GroupBy(p=>p.Name).Any(g=>g.Count()!=1))throw new JsonException("Duplicate health field.");
            foreach(var field in fields)ValidateFields(field.Value);
        }
        else if(element.ValueKind==JsonValueKind.Array)
            foreach(var item in element.EnumerateArray())ValidateFields(item);
    }
    internal sealed record Operation(Snapshot Target,bool? IncludeMicrophone)
    {
        internal byte[] Message(string request)
        {
            Id(request);Id(Target.InstanceId);
            return IncludeMicrophone is not null
                ? JsonSerializer.SerializeToUtf8Bytes(new{protocol_version=1,message_type="setup_check",request_id=request,
                    instance_id=Target.InstanceId,include_microphone=IncludeMicrophone.Value},Json)
                : JsonSerializer.SerializeToUtf8Bytes(new{protocol_version=1,message_type="core_restart",request_id=request,
                    instance_id=Target.InstanceId,pid=Target.Pid,creation_time=Target.CreationTime},Json);
        }
    }
    internal static byte[] Query(string request)
    { Id(request);return JsonSerializer.SerializeToUtf8Bytes(new{protocol_version=1,message_type="health_query",request_id=request},Json); }
    private static void Id(string value)
    { if(!Guid.TryParseExact(value,"D",out var id)||id.ToString("D")!=value)throw new JsonException("Invalid health identity."); }
}
