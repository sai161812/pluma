using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class LiveMessageFeed : UserControl
    {
        private readonly LiveMessageBuffer _buffer = new();

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
