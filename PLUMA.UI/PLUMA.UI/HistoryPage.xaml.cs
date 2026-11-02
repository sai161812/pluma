using System;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI
{
    public sealed partial class HistoryPage : Page
    {
        private HistoryController? _history;
        private CancellationToken _owner;
        private SavedDetailController? _detail;
        private CommandController? _commands;
        internal ConflictAlertPopup? ActiveConflict { get; private set; }
        public HistoryPage()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += (_, _) => {
                if (_history is not null) _history.Changed -= Apply;
                if (_detail is not null) _detail.Changed -= ApplyDetail;
                if (_commands is not null) _commands.Changed -= ApplyUndo;
                ActiveConflict?.Hide();
            };
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
            if (_detail is not null) { _detail.Changed -= ApplyDetail; _detail.Changed += ApplyDetail; ApplyDetail(_detail.View); }
            if (_commands is not null) { _commands.Changed -= ApplyUndo; _commands.Changed += ApplyUndo; ApplyUndo(_commands.View); }
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

        internal void AttachDetail(SavedDetailController detail, CommandController commands)
        {
            _detail = detail; _commands = commands;
            detail.Changed += ApplyDetail; commands.Changed += ApplyUndo;
            ApplyDetail(detail.View); ApplyUndo(commands.View);
        }
        private void ApplyDetail(SavedDetailView view)
        {
            if (!DispatcherQueue.HasThreadAccess) { DispatcherQueue.TryEnqueue(() => ApplyDetail(_detail!.View)); return; }
            if (_owner.IsCancellationRequested) return;
            DetailStatus.Text = view.Status; DetailContext.Text = view.Context; DetailActions.ItemsSource = view.Actions;
            DetailMore.IsEnabled = view.HasMore && !view.Busy; HistoryRecords.IsEnabled = !view.Busy;
            if (view.RequestId is not null && !view.Busy) _commands?.SetConnected(true);
            UpdateActions();
        }
        private void ApplyUndo(CommandView view)
        {
            if (!DispatcherQueue.HasThreadAccess) { DispatcherQueue.TryEnqueue(() => ApplyUndo(_commands!.View)); return; }
            if (_owner.IsCancellationRequested) return;
            UndoStatus.Text = view.RequestId is null ? "" : view.Message + "\nRequest " + view.RequestId + (view.TaskId is null ? "" : "\nTask " + view.TaskId);
            UpdateActions();
        }
        private void UpdateActions()
        {
            var action = (DetailActions.SelectedItem as SavedActionRow)?.Original;
            DetailUndo.IsEnabled = _detail?.View.Busy == false && action?.Selection is not null && _commands?.View.CanSubmit == true;
            DetailConflict.IsEnabled = action?.RollbackAttempted == true && action.RollbackOk is false;
        }
        private async void OnTaskSelected(object sender, SelectionChangedEventArgs args)
        { if (_detail is not null && HistoryRecords.SelectedItem is HistoryRow task) await _detail.ReadAsync(task.TaskId); }
        private void OnActionSelected(object sender, SelectionChangedEventArgs args) => UpdateActions();
        private async void OnMoreActions(object sender, RoutedEventArgs args)
        { if (_detail?.View is { TaskId: string task, HasMore: true } view) await _detail.ReadAsync(task, view.Cursor); }
        private async void OnUndoSelected(object sender, RoutedEventArgs args)
        {
            if (_commands is null || _detail is null || !DetailUndo.IsEnabled ||
                (DetailActions.SelectedItem as SavedActionRow)?.Original.Selection is not { } selected) return;
            await _commands.SubmitAsync("Undo saved action " + selected.ActionId + " of task " + selected.TargetTaskId, selected);
            if (!_owner.IsCancellationRequested && _detail.View.TaskId == selected.TargetTaskId)
                await _detail.ReadAsync(selected.TargetTaskId);
        }
        private async void OnViewConflict(object sender, RoutedEventArgs args)
        {
            if (ActiveConflict is not null || (DetailActions.SelectedItem as SavedActionRow)?.Original is not { } action) return;
            var dialog = new ConflictAlertPopup { XamlRoot = XamlRoot };
            dialog.BindSavedConflict(action.ConflictCurrent, action.ConflictTarget);
            dialog.ViewConflictRequested += (_, _) => { DetailStatus.Text = "Action " + action.ActionId + ": " + new SavedActionRow(action).Facts; dialog.Hide(); };
            dialog.IsSecondaryButtonEnabled = dialog.IsSecondaryButtonEnabled && _commands?.View.CanSubmit == true;
            dialog.OpenFolderRequested += async (_, _) => {
                if (_commands is null || _detail?.View.TaskId is not string task || !_commands.View.CanSubmit) return;
                dialog.Hide();
                await _commands.SubmitAsync("Open recorded conflict folder for action " + action.ActionId,
                    folder: new CoreRequestProtocol.FolderSelection(task, action.ActionId, action.ConflictCurrent is not null ? "current" : "target"));
            };
            ActiveConflict = dialog;
            try { using var registration = _owner.Register(() => DispatcherQueue.TryEnqueue(dialog.Hide)); await dialog.ShowAsync(); }
            finally { ActiveConflict = null; }
        }
    }
}
