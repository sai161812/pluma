using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace PLUMA.UI
{
    /// <summary>Deterministic presentation only. Never changes tool arguments, transcripts, or ledger records.</summary>
    public static class PopupText
    {
        private static readonly IReadOnlyDictionary<string, string> Labels = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["open_file"] = "Open file", ["move_file"] = "Move file", ["rename_file"] = "Rename file",
            ["open_app"] = "Open app", ["close_app"] = "Close app", ["invoke_control"] = "Select control",
            ["click_ocr_text"] = "Select text on screen", ["ocr_rescan"] = "Screen text check",
            ["ocr"] = "Screen text check", ["uia"] = "Windows accessibility check",
            ["api"] = "Application check", ["ocr_grounded"] = "Screen target check",
            ["restart_request"] = "Restart computer", ["shutdown_request"] = "Shut down computer",
            ["set_volume"] = "Set volume", ["permission_denied"] = "Permission denied",
            ["rollback_conflict"] = "Could not safely restore the previous state"
        };

        public static string Label(string? value)
        {
            string source = (value ?? string.Empty).Trim();
            if (Labels.TryGetValue(source, out string? label)) return label;
            string words = Message(source);
            if (words.Length == 0) return words;
            if (words.All(character => !char.IsLetter(character) || char.IsUpper(character))) words = words.ToLowerInvariant();
            return char.ToUpperInvariant(words[0]) + words.Substring(1);
        }

        public static string Message(string? value)
        {
            string text = value ?? string.Empty;
            text = Regex.Replace(text, @"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b",
                match => Labels.TryGetValue(match.Value, out string? label) ? label : match.Value.Replace('_', ' '));
            text = Regex.Replace(text.Replace('_', ' '), @"(?:\s*\u2014\s*)+", ". ");
            text = Regex.Replace(text, @"([.!?:;])\s*\.\s*", "$1 ");
            text = Regex.Replace(text, @"[^\S\r\n]+", " ");
            text = Regex.Replace(text, @"[ \t]+([.,:;!?])", "$1");
            text = Regex.Replace(text, @"^\.\s+", string.Empty);
            return text.Trim();
        }

        public static string Arguments(string? sanitizedArguments)
        {
            if (string.IsNullOrWhiteSpace(sanitizedArguments)) return string.Empty;
            try
            {
                using JsonDocument document = JsonDocument.Parse(sanitizedArguments, new JsonDocumentOptions { MaxDepth = 16 });
                return RenderValue(document.RootElement);
            }
            catch (JsonException) { return Message(sanitizedArguments); }
        }

        private static string RenderValue(JsonElement value) => value.ValueKind switch
        {
            JsonValueKind.Object => string.Join(Environment.NewLine, value.EnumerateObject().Select(property => $"{Label(property.Name)}: {RenderValue(property.Value)}")),
            JsonValueKind.Array => string.Join(", ", value.EnumerateArray().Select(RenderValue)),
            JsonValueKind.String => Message(value.GetString()),
            JsonValueKind.True => "Yes", JsonValueKind.False => "No", JsonValueKind.Null => "Not set",
            _ => Message(value.ToString())
        };
    }
}
