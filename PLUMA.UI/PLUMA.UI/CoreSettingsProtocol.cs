using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

namespace PLUMA.UI;

internal static partial class CoreRequestProtocol
{
    internal sealed record SettingsEditValues(string TextHotkey, string StopHotkey, string VoiceHotkey, int MaxPlanSteps)
    {
        internal void Validate()
        {
            if (new[] { TextHotkey, StopHotkey, VoiceHotkey }.Any(v => string.IsNullOrWhiteSpace(v) || v.Length > 64)
                || MaxPlanSteps is < 1 or > 20) throw new JsonException("Invalid settings values.");
        }
    }

    internal sealed record SettingsEditSnapshot(int ProtocolVersion, string MessageType, string RequestId,
        string Revision, SettingsEditValues Persisted, SettingsEditValues Effective, string[] RestartFields, string[] EditableFields)
    {
        internal static SettingsEditSnapshot Parse(ReadOnlySpan<byte> message)
        {
            RejectDuplicateProperties(message);
            var value = JsonSerializer.Deserialize<SettingsEditSnapshot>(message, Options)
                ?? throw new JsonException("Empty settings edit response.");
            RequireId(value.RequestId, "request_id"); RequireSettingsRevision(value.Revision);
            if (value.ProtocolVersion != Version || value.MessageType != "settings_edit_snapshot"
                || value.Persisted is null || value.Effective is null || value.RestartFields is null
                || value.EditableFields is null || !value.EditableFields.SequenceEqual(new[] { "max_plan_steps" }))
                throw new JsonException("Invalid settings edit envelope.");
            value.Persisted.Validate(); value.Effective.Validate();
            var expected = new List<string>();
            if (value.Persisted.TextHotkey != value.Effective.TextHotkey) expected.Add("text_hotkey");
            if (value.Persisted.StopHotkey != value.Effective.StopHotkey) expected.Add("stop_hotkey");
            if (value.Persisted.VoiceHotkey != value.Effective.VoiceHotkey) expected.Add("voice_hotkey");
            if (value.Persisted.MaxPlanSteps != value.Effective.MaxPlanSteps) expected.Add("max_plan_steps");
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

    internal sealed record SettingsEdits(int? MaxPlanSteps = null)
    {
        internal Dictionary<string, object> Fields()
        {
            var fields = new Dictionary<string, object>();
            if (MaxPlanSteps is not null)
            {
                if (MaxPlanSteps is < 1 or > 20) throw new ArgumentException("Invalid plan limit.");
                fields.Add("max_plan_steps", MaxPlanSteps.Value);
            }
            if (fields.Count == 0) throw new ArgumentException("No settings changes supplied.");
            return fields;
        }
    }

    internal sealed record SettingsSaveRequest(string RequestId, string ExpectedRevision, SettingsEdits Changes)
    {
        internal byte[] ToMessage()
        {
            RequireId(RequestId, "request_id"); RequireSettingsRevision(ExpectedRevision);
            return JsonSerializer.SerializeToUtf8Bytes(new { protocol_version = Version, message_type = "settings_save",
                request_id = RequestId, expected_revision = ExpectedRevision, changes = Changes.Fields() }, Options);
        }
    }
}
