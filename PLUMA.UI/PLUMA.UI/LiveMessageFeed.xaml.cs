using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class LiveMessageFeed : UserControl
    {
        private readonly LiveMessageBuffer _buffer = new();
        internal System.Collections.ObjectModel.ReadOnlyObservableCollection<LiveMessageEntry> Entries => _buffer.Entries;
        private string[] _identities = [];
        internal void ApplyEntries(IEnumerable<EventFeedEntry> supplied)
        {
            var rows = supplied.TakeLast(_buffer.Capacity).ToArray();
            if (_identities.SequenceEqual(rows.Select(row => row.Identity))) return;
            while (_identities.Length > 0 && !rows.Any(row => row.Identity == _identities[0]))
            { _buffer.RemoveOldest(); _identities = _identities.Skip(1).ToArray(); }
            // Preserve the unchanged prefix; reset only on replacement/reset.
            int overlap = _identities.Length;
            if (rows.Length < overlap || !rows.Take(overlap).Select(row => row.Identity).SequenceEqual(_identities))
            { _buffer.Clear(); overlap = 0; }
            foreach (var row in rows.Skip(overlap)) _buffer.Append(row.DisplayText, row.Timestamp);
            _identities = rows.Select(row => row.Identity).ToArray();
            ApplyEmptyState();
        }

        public LiveMessageFeed()
        {
            InitializeComponent();
            MessageList.ItemsSource = _buffer.Entries;
            ApplyEmptyState();
        }

        // Call on the UI thread with factual, redacted executor/status events only.
        public void AppendMessage(string sanitizedMessage, DateTimeOffset timestamp)
        {
            _buffer.Append(sanitizedMessage, timestamp);
            ApplyEmptyState();
        }

        public void ClearMessages()
        {
            _buffer.Clear();
            _identities = [];
            ApplyEmptyState();
        }

        private void ApplyEmptyState()
        {
            bool empty = _buffer.Entries.Count == 0;
            EmptyText.Visibility = empty ? Visibility.Visible : Visibility.Collapsed;
            MessageList.Visibility = empty ? Visibility.Collapsed : Visibility.Visible;
        }
    }
}
