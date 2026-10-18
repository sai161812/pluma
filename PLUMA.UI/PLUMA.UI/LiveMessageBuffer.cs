using System;
using System.Collections.ObjectModel;

namespace PLUMA.UI
{
    public sealed record LiveMessageEntry(DateTimeOffset Timestamp, string Message)
    {
        public string DisplayTime => Timestamp.ToLocalTime().ToString("HH:mm:ss");
    }

    /// <summary>Transient display buffer; the Activity Ledger remains the history source.</summary>
    public sealed class LiveMessageBuffer
    {
        private readonly ObservableCollection<LiveMessageEntry> _entries = new();
        public ReadOnlyObservableCollection<LiveMessageEntry> Entries { get; }
        public int Capacity { get; }

        public LiveMessageBuffer(int capacity = 200)
        {
            if (capacity < 1) throw new ArgumentOutOfRangeException(nameof(capacity));
            Capacity = capacity;
            Entries = new ReadOnlyObservableCollection<LiveMessageEntry>(_entries);
        }

        // The host supplies an already-redacted executor message and its event timestamp.
        public void Append(string sanitizedMessage, DateTimeOffset timestamp)
        {
            if (string.IsNullOrWhiteSpace(sanitizedMessage)) return;
            if (_entries.Count == Capacity) _entries.RemoveAt(0);
            _entries.Add(new LiveMessageEntry(timestamp, sanitizedMessage));
        }

        public void Clear() => _entries.Clear();
    }
}
