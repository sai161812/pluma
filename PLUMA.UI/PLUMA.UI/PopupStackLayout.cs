using System;
using System.Collections.Generic;
using System.Linq;

namespace PLUMA.UI
{
    public readonly record struct PopupRect(double X, double Y, double Width, double Height)
    {
        public double Right => X + Width;
        public double Bottom => Y + Height;
        public bool IsValid => double.IsFinite(X) && double.IsFinite(Y) && double.IsFinite(Width) &&
            double.IsFinite(Height) && Width > 0 && Height > 0;
        public bool Contains(PopupRect other, double tolerance = 0) => IsValid && other.IsValid &&
            other.X >= X - tolerance && other.Y >= Y - tolerance && other.Right <= Right + tolerance && other.Bottom <= Bottom + tolerance;
        public bool Overlaps(PopupRect other) => X < other.Right && Right > other.X && Y < other.Bottom && Bottom > other.Y;
        public PopupRect Intersect(PopupRect other)
        {
            double left = Math.Max(X, other.X), top = Math.Max(Y, other.Y);
            return new(left, top, Math.Max(0, Math.Min(Right, other.Right) - left), Math.Max(0, Math.Min(Bottom, other.Bottom) - top));
        }
    }

    public enum PopupScreenEdge { Left, Top, Right, Bottom }
    public sealed record PopupAppBar(PopupScreenEdge Edge, double ThicknessPixels, bool IsRevealed = true);
    public sealed record PopupDesktop(PopupRect Monitor, PopupRect WorkArea, double Scale,
        IReadOnlyList<PopupAppBar> AutoHideBars, bool GeometryVerified = true);
    public sealed record PopupPlacement(string Key, PopupRect Bounds);

    /// <summary>Pure physical-pixel geometry. DIPs are converted once, with inward-safe rounding.</summary>
    public static class PopupStackLayout
    {
        public const double EdgeInsetDips = 24;
        public const double ShadowReserveDips = 8;
        public const double GapDips = 12;
        public const double MaximumWidthDips = 460;

        public static PopupRect SafeArea(PopupDesktop desktop)
        {
            if (!desktop.Monitor.IsValid || !desktop.WorkArea.IsValid || !double.IsFinite(desktop.Scale) || desktop.Scale < 0.5 || desktop.Scale > 8)
                throw new ArgumentException("Invalid display geometry.", nameof(desktop));
            PopupRect safe = desktop.Monitor.Intersect(desktop.WorkArea);
            foreach (PopupAppBar bar in desktop.AutoHideBars)
            {
                if (!double.IsFinite(bar.ThicknessPixels) || bar.ThicknessPixels <= 0)
                    throw new ArgumentException("Invalid taskbar geometry.", nameof(desktop));
                if (!bar.IsRevealed) continue;
                PopupRect monitor = desktop.Monitor;
                PopupRect excluded = bar.Edge switch
                {
                    PopupScreenEdge.Left => new(monitor.X + bar.ThicknessPixels, monitor.Y, Math.Max(0, monitor.Width - bar.ThicknessPixels), monitor.Height),
                    PopupScreenEdge.Top => new(monitor.X, monitor.Y + bar.ThicknessPixels, monitor.Width, Math.Max(0, monitor.Height - bar.ThicknessPixels)),
                    PopupScreenEdge.Right => new(monitor.X, monitor.Y, Math.Max(0, monitor.Width - bar.ThicknessPixels), monitor.Height),
                    PopupScreenEdge.Bottom => new(monitor.X, monitor.Y, monitor.Width, Math.Max(0, monitor.Height - bar.ThicknessPixels)),
                    _ => throw new ArgumentException("Invalid taskbar edge.")
                };
                safe = safe.Intersect(excluded); // Existing docked reservation is never added twice.
            }
            return safe;
        }

        public static bool IsTaskbarRevealed(PopupRect monitor, PopupRect currentBounds, PopupScreenEdge edge, double scale)
        {
            if (!monitor.IsValid || !currentBounds.IsValid || !double.IsFinite(scale) || scale <= 0)
                throw new ArgumentException("Invalid taskbar visibility geometry.");
            PopupRect visible = monitor.Intersect(currentBounds);
            double thickness = edge is PopupScreenEdge.Left or PopupScreenEdge.Right ? visible.Width : visible.Height;
            return visible.IsValid && thickness > Math.Ceiling(2 * scale); // Ignore the hidden activation strip.
        }

        public static bool CanGlideForTaskbar(PopupDesktop previous, PopupDesktop next)
        {
            if (previous.Monitor != next.Monitor || previous.Scale != next.Scale) return false;
            var before = previous.AutoHideBars.OrderBy(bar => bar.Edge).ToArray();
            var after = next.AutoHideBars.OrderBy(bar => bar.Edge).ToArray();
            if (before.Length != after.Length || before.Length == 0) return false;
            if (before.Where((bar, index) => bar.Edge != after[index].Edge || bar.ThicknessPixels != after[index].ThicknessPixels).Any()) return false;
            if (!before.Where((bar, index) => bar.IsRevealed != after[index].IsRevealed).Any()) return false;
            PopupDesktop FullyReserved(PopupDesktop desktop) => desktop with { AutoHideBars = desktop.AutoHideBars.Select(bar => bar with { IsRevealed = true }).ToArray() };
            // Some shells update the work area on reveal. Accept only changes covered by the same appbar footprint.
            return SafeArea(FullyReserved(previous)) == SafeArea(FullyReserved(next));
        }

        public static PopupRect ContentArea(PopupDesktop desktop)
        {
            PopupRect safe = SafeArea(desktop);
            double inset = Math.Ceiling((EdgeInsetDips + ShadowReserveDips) * desktop.Scale);
            double left = Math.Ceiling(safe.X + inset), top = Math.Ceiling(safe.Y + inset);
            return new(left, top, Math.Max(0, Math.Floor(safe.Right - inset) - left), Math.Max(0, Math.Floor(safe.Bottom - inset) - top));
        }

        public static IReadOnlyList<PopupPlacement> Arrange(PopupDesktop desktop, IReadOnlyList<PopupStackItem> oldestFirst)
        {
            PopupRect area = ContentArea(desktop);
            var positions = new List<PopupPlacement>();
            double bottom = area.Bottom, gap = Math.Ceiling(GapDips * desktop.Scale);
            foreach (PopupStackItem entry in oldestFirst.Reverse())
            {
                double width = Math.Min(Math.Ceiling(entry.WidthDips * desktop.Scale), area.Width);
                double height = Math.Ceiling(entry.HeightDips * desktop.Scale);
                var bounds = new PopupRect(area.Right - width, bottom - height, width, height);
                if (!area.Contains(bounds)) throw new InvalidOperationException("Popup selection exceeds its safe area.");
                positions.Add(new(entry.Key, bounds));
                bottom = bounds.Y - gap;
            }
            positions.Reverse();
            return positions;
        }

        public static double Ease(double elapsedMilliseconds, double durationMilliseconds)
        {
            if (!double.IsFinite(elapsedMilliseconds) || !double.IsFinite(durationMilliseconds) || durationMilliseconds <= 0) return 1;
            double progress = Math.Clamp(elapsedMilliseconds / durationMilliseconds, 0, 1);
            return 1 - Math.Pow(1 - progress, 3);
        }
    }
}
