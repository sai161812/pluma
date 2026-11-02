using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;
using System.Threading;

namespace PLUMA.UI
{
    public sealed partial class HistoryPage : Page
    {
        private HistoryController? _history;
        private CancellationToken _owner;
        public HistoryPage()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += (_, _) => { if (_history is not null) _history.Changed -= Apply; };
        }
        internal void AttachHistory(HistoryController history, CancellationToken owner)
        {
            if (_history is not null) _history.Changed -= Apply;
            _history = history; _owner = owner;
            history.Changed += Apply; HistorySearch.Text = history.View.Search; Apply(history.View);
        }
        private async void OnLoaded(object sender, RoutedEventArgs args)
        {
            if (_history is null) return;
            _history.Changed -= Apply; _history.Changed += Apply; Apply(_history.View);
            if (!_history.View.Connected && !_history.View.Busy) await _history.RefreshAsync(_history.View.Search, _owner);
        }
        private void Apply(HistoryView view)
        {
            if (!DispatcherQueue.HasThreadAccess) { DispatcherQueue.TryEnqueue(() => { if (_history is not null) Apply(_history.View); }); return; }
            if (_owner.IsCancellationRequested) return;
            HistoryRecords.ItemsSource = view.Rows;
            HistoryStatus.Text = view.Message;
            HistorySearch.IsEnabled = HistoryRefresh.IsEnabled = !view.Busy;
            HistoryOlder.IsEnabled = !view.Busy && view.Connected && view.HasMore;
        }
        private async void OnRefresh(object sender, RoutedEventArgs args)
        { if (_history is not null) await _history.RefreshAsync(HistorySearch.Text, _owner); }
        private async void OnSearchSubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
        { if (_history is not null) await _history.RefreshAsync(args.QueryText, _owner); }
        private async void OnOlder(object sender, RoutedEventArgs args)
        { if (_history is not null) await _history.OlderAsync(_owner); }
    }
}
