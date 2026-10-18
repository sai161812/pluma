using System;
using System.Collections.Generic;
using System.Linq;

namespace PLUMA.UI
{
    public sealed class PopupStackItem
    {
        internal PopupStackItem(string key, long sequence) { Key = key; Sequence = sequence; }
        public string Key { get; }
        public long Sequence { get; }
        public double WidthDips { get; internal set; }
        public double HeightDips { get; internal set; }
        public bool Persistent { get; internal set; }
        public int Priority { get; internal set; }
        public bool Held { get; internal set; }
        public bool Displayed { get; internal set; }
        public double RemainingMilliseconds { get; internal set; }
    }

    public sealed record PopupStackPlan(IReadOnlyList<PopupPlacement> Placements, IReadOnlyList<string> Retire);

    /// <summary>UI-only ordering/lifetime state. It cannot execute, cancel, or report success for a task.</summary>
    public sealed class PopupStackState
    {
        public const int Capacity = 48;
        private readonly List<PopupStackItem> _items = new();
        private long _sequence;
        public IReadOnlyList<PopupStackItem> Items => _items.AsReadOnly();

        public bool Upsert(string key, double widthDips, double heightDips, bool persistent, TimeSpan? lifetime, int priority = 0)
        {
            if (string.IsNullOrWhiteSpace(key) || !double.IsFinite(widthDips) || !double.IsFinite(heightDips) || widthDips <= 0 || heightDips <= 0 ||
                (lifetime.HasValue && (lifetime.Value <= TimeSpan.Zero || lifetime.Value > TimeSpan.FromMinutes(1))))
                throw new ArgumentException("Invalid popup presentation.");
            PopupStackItem? entry = _items.FirstOrDefault(item => item.Key == key);
            if (entry == null)
            {
                // The caller retains the factual event. Refuse admission without silently deleting an active entry.
                if (_items.Count >= Capacity) return false;
                entry = new PopupStackItem(key, ++_sequence);
                _items.Add(entry);
            }
            entry.WidthDips = Math.Min(widthDips, PopupStackLayout.MaximumWidthDips);
            entry.HeightDips = heightDips;
            entry.Persistent = persistent;
            entry.Priority = priority;
            entry.RemainingMilliseconds = lifetime?.TotalMilliseconds ?? double.PositiveInfinity;
            return true;
        }

        public bool Remove(string key) => _items.RemoveAll(item => item.Key == key) > 0;
        public void Clear() => _items.Clear();
        public void Hold(string key, bool held) { var entry = Find(key); if (entry != null) entry.Held = held; }
        public void SetDisplayed(string key, bool displayed) { var entry = Find(key); if (entry != null) entry.Displayed = displayed; }
        public PopupStackItem? Find(string key) => _items.FirstOrDefault(item => item.Key == key);

        public IReadOnlyList<string> Advance(TimeSpan elapsed)
        {
            if (elapsed < TimeSpan.Zero || !double.IsFinite(elapsed.TotalMilliseconds)) throw new ArgumentOutOfRangeException(nameof(elapsed));
            var expired = new List<string>();
            foreach (PopupStackItem entry in _items)
            {
                if (!entry.Displayed || entry.Held || entry.Persistent) continue;
                entry.RemainingMilliseconds = Math.Max(0, entry.RemainingMilliseconds - elapsed.TotalMilliseconds);
                if (entry.RemainingMilliseconds == 0) expired.Add(entry.Key);
            }
            return expired;
        }

        public PopupStackPlan Plan(PopupDesktop desktop)
        {
            PopupRect area = PopupStackLayout.ContentArea(desktop);
            double gap = Math.Ceiling(PopupStackLayout.GapDips * desktop.Scale), used = 0;
            var selected = new HashSet<string>(StringComparer.Ordinal);
            bool Admit(PopupStackItem item)
            {
                double height = Math.Ceiling(item.HeightDips * desktop.Scale);
                double cost = height + (selected.Count == 0 ? 0 : gap);
                if (area.Width < Math.Ceiling(120 * desktop.Scale) || height > area.Height || used + cost > area.Height) return false;
                selected.Add(item.Key); used += cost; return true;
            }
            foreach (PopupStackItem item in _items.Where(item => item.Priority > 0 || item.Persistent || item.Held)
                .OrderByDescending(item => item.Priority).ThenByDescending(item => item.Sequence)) Admit(item);
            foreach (PopupStackItem item in _items.Where(item => !selected.Contains(item.Key) && !item.Persistent && !item.Held && item.Priority == 0)
                .OrderByDescending(item => item.Sequence)) Admit(item);
            var visible = _items.Where(item => selected.Contains(item.Key)).OrderBy(item => item.Sequence).ToArray();
            var retire = _items.Where(item => !selected.Contains(item.Key) && !item.Persistent && !item.Held && item.Displayed).Select(item => item.Key).ToArray();
            return new(PopupStackLayout.Arrange(desktop, visible), retire);
        }
    }
}
