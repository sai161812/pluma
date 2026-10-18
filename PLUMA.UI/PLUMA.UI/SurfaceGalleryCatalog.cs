using System.Collections.Generic;

namespace PLUMA.UI
{
    /// <summary>Preview inventory only; IDs match the owner-facing surface reference.</summary>
    public sealed record SurfaceGalleryItem(int Id, string Name)
    {
        public string Label => $"{Id:00} · {Name}";
    }

    public static class SurfaceGalleryCatalog
    {
        public static IReadOnlyList<SurfaceGalleryItem> Items { get; } = new List<SurfaceGalleryItem>
        {
            new(1, "Dashboard"), new(2, "Settings"), new(3, "History / Activity Ledger"),
            new(4, "Task Running Popup"), new(5, "Step Progress Popup"), new(6, "Route Badge Popup"),
            new(7, "Tool Call Card"), new(8, "Tool Result Card"), new(9, "Rollback Popup"),
            new(10, "Conflict Alert Popup"), new(11, "Voice Listening Animation"),
            new(12, "Live Transcription Overlay"), new(13, "Voice Committed Banner"),
            new(14, "Voice Silence Timeout Indicator"), new(15, "Screen Capture Flash"),
            new(16, "OCR Match Indicator"), new(17, "Post-Click Verify Indicator"),
            new(18, "Risk Approval Dialog"), new(19, "Policy Block Notice"),
            new(20, "Cancellation Animation"), new(21, "Worker Termination Flash"),
            new(22, "Live Message Feed"), new(23, "Core Health Indicator"),
            new(24, "Toast Notification"), new(25, "Critical Error Dialog"), new(26, "Setup Wizard")
        }.AsReadOnly();
    }
}
