using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record SettingsEditValues(string TextHotkey, string StopHotkey, string VoiceHotkey, int MaxPlanSteps,
        string PlannerModelPath="", string SttModelPath="", int ModelIdleUnloadSeconds=30,
        int SttIdleUnloadSeconds=20, int OcrIdleUnloadSeconds=10, bool AllowShortWarmGrace=true,
        string ActivationDefault="push_to_talk", string ModelRuntime="llama_cpp")
    {
        internal void Validate()
        {
            if (new[] { TextHotkey, StopHotkey, VoiceHotkey }.Any(v => string.IsNullOrWhiteSpace(v) || v.Length > 64)
                || MaxPlanSteps is < 1 or > 20 || ModelIdleUnloadSeconds is < 0 or > 30
                || SttIdleUnloadSeconds is < 0 or > 30 || OcrIdleUnloadSeconds is < 0 or > 30
                || ActivationDefault!="push_to_talk" || ModelRuntime!="llama_cpp") throw new JsonException("Invalid settings values.");
        }
    }

    internal sealed record SettingsEditSnapshot(int ProtocolVersion, string MessageType, string RequestId,
        string Revision, SettingsEditValues Persisted, SettingsEditValues Effective, string[] RestartFields, string[] EditableFields, string? PreviousRevision=null)
    {
        internal static SettingsEditSnapshot Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<SettingsEditSnapshot>(message, Options)
                ?? throw new JsonException("Empty settings edit response.");
            RequireId(value.RequestId, "request_id"); RequireSettingsRevision(value.Revision);
            if (value.ProtocolVersion != Version || value.MessageType != "settings_edit_snapshot"
                || value.Persisted is null || value.Effective is null || value.RestartFields is null
                || value.EditableFields is null || value.EditableFields.Distinct().Count()!=value.EditableFields.Length || value.EditableFields.Any(key=>!SettingKeys.Contains(key)))
                throw new JsonException("Invalid settings edit envelope.");
            if(value.PreviousRevision is not null) { RequireSettingsRevision(value.PreviousRevision); if(value.PreviousRevision=="absent" || value.EditableFields.Length!=0)throw new JsonException("Invalid recovery state."); }
            value.Persisted.Validate(); value.Effective.Validate();
            var persisted=JsonSerializer.SerializeToElement(value.Persisted,Options);
            var effective=JsonSerializer.SerializeToElement(value.Effective,Options);
            var expected=SettingKeys.Where(key=>persisted.GetProperty(key).GetRawText()!=effective.GetProperty(key).GetRawText()).ToList();
            if (value.RestartFields.Length != expected.Count || !value.RestartFields.Order().SequenceEqual(expected.Order()))
                throw new JsonException("Restart fields disagree with effective settings.");
            return value;
        }
    }

    private static void RequireSettingsRevision(string value)
    {
        if (value is null || value != "absent" && (value.Length != 64 || value.Any(c => !"0123456789abcdef".Contains(c))))
            throw new JsonException("Invalid settings revision.");
    }

    internal sealed record SettingsEditQuery(string RequestId)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id");
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version,
                message_type = "settings_edit_query", request_id = RequestId }, Options);
        }
    }

    internal static readonly string[] SettingKeys=["max_plan_steps","text_hotkey","stop_hotkey","voice_hotkey",
        "planner_model_path","stt_model_path","model_idle_unload_seconds","stt_idle_unload_seconds",
        "ocr_idle_unload_seconds","allow_short_warm_grace","activation_default","model_runtime"];

    internal sealed record SettingsEdits(int? MaxPlanSteps=null, string? TextHotkey=null, string? StopHotkey=null,
        string? VoiceHotkey=null, string? PlannerModelPath=null, string? SttModelPath=null,
        int? ModelIdleUnloadSeconds=null, int? SttIdleUnloadSeconds=null, int? OcrIdleUnloadSeconds=null,
        bool? AllowShortWarmGrace=null, string? ActivationDefault=null, string? ModelRuntime=null, bool? RecoverPrevious=null, [property: System.Text.Json.Serialization.JsonIgnore] string? RecoveryRevision=null)
    {
        internal Dictionary<string, object> Fields()
        {
            if (MaxPlanSteps is < 1 or > 20 || ModelIdleUnloadSeconds is < 0 or > 30
                || SttIdleUnloadSeconds is < 0 or > 30 || OcrIdleUnloadSeconds is < 0 or > 30
                || ActivationDefault is not null and not "push_to_talk" || ModelRuntime is not null and not "llama_cpp")
                throw new ArgumentException("Unsupported settings value.");
            foreach (var text in new[]{TextHotkey,StopHotkey,VoiceHotkey,PlannerModelPath,SttModelPath})
                if (text is not null && (string.IsNullOrWhiteSpace(text)||text.Length>4096||text.Contains('\0')))
                    throw new ArgumentException("Invalid settings text.");
            var fields=JsonSerializer.SerializeToElement(this,Options).EnumerateObject()
                .Where(p=>p.Value.ValueKind!=JsonValueKind.Null).ToDictionary(p=>p.Name,p=>(object)p.Value.Clone());
            if(RecoverPrevious is not null && (RecoverPrevious!=true || fields.Count!=1))throw new ArgumentException("Invalid recovery request.");
            if (fields.Count==0) throw new ArgumentException("No settings changes supplied.");
            return fields;
        }
    }

    internal sealed record SettingsSaveRequest(string RequestId, string ExpectedRevision, SettingsEdits Changes, string? PreviousRevision=null)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireSettingsRevision(ExpectedRevision);
            if((Changes.RecoverPrevious==true)!=(PreviousRevision is not null))throw new ArgumentException("Missing recovery revision.");
            if(PreviousRevision is not null)RequireSettingsRevision(PreviousRevision);
            var fields=new Dictionary<string,object>{["protocol_version"]=Version,["message_type"]="settings_save",
                ["request_id"]=RequestId,["expected_revision"]=ExpectedRevision,["changes"]=Changes.Fields()};
            if(PreviousRevision is not null)fields["previous_revision"]=PreviousRevision;
            return JsonSerializer.SerializeToUtf8Bytes(fields,Options);
        }
    }
}
