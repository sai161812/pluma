using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Dispatching;
using System;
using System.Globalization;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI
{
    public sealed partial class DashboardPage : Page
    {
        private ICoreStatusClient? _core;
        private CancellationTokenSource? _healthLifetime;
        private Task _healthTask = Task.CompletedTask;
        private bool _preview;
        private CancellationToken _ownerLifetime;
        private CommandController? _commands;
        private EventFeedController? _events;
        private readonly ObservableCollection<EventFeedEntry> _liveEntries = new();
        private readonly DispatcherQueue _dispatcher;

        public DashboardPage()
        {
            this.InitializeComponent();
            _dispatcher = DispatcherQueue;
            Loaded += (_, _) =>
            {
                if (_commands != null) { _commands.Changed -= OnCommandChanged; _commands.Changed += OnCommandChanged; ApplyCommand(_commands.View); }
                if (_events != null) { _events.Changed -= OnEventsChanged; _events.Changed += OnEventsChanged; OnEventsChanged(_events.View); }
                BeginRefresh();
            };
            Unloaded += OnUnloaded;
        }

        internal void AttachEventController(EventFeedController events)
        {
            if (_events != null) _events.Changed -= OnEventsChanged;
            _events = events;
            _events.Changed += OnEventsChanged;
            OnEventsChanged(events.View);
        }

        private void OnEventsChanged(EventFeedView view)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnEventsChanged(_events!.View)); return; }
            if (!IsLoaded || _ownerLifetime.IsCancellationRequested || _preview) return;
            while (_liveEntries.Count > 0 && !view.Entries.Any(entry => entry.Identity == _liveEntries[0].Identity)) _liveEntries.RemoveAt(0);
            if (_liveEntries.Count > view.Entries.Length || _liveEntries.Where((entry, index) => entry.Identity != view.Entries[index].Identity).Any()) _liveEntries.Clear();
            foreach (var entry in view.Entries.Skip(_liveEntries.Count)) _liveEntries.Add(entry);
            if (!ReferenceEquals(LiveMessagesList.ItemsSource, _liveEntries)) LiveMessagesList.ItemsSource = _liveEntries;
            LiveConnectionText.Text = view.Status;
        }

        internal void AttachCommandController(CommandController commands)
        {
            if (_commands != null) _commands.Changed -= OnCommandChanged;
            _commands = commands;
            _commands.Changed += OnCommandChanged;
            ApplyCommand(commands.View);
        }

        internal void AttachCoreClient(ICoreStatusClient core, CancellationToken ownerLifetime = default)
        {
            _core = core;
            _ownerLifetime = ownerLifetime;
            _preview = false;
            CurrentActivityList.Items.Clear(); RecentActivityList.Items.Clear();
            LiveMessagesList.ItemsSource = null; LiveMessagesList.Items.Clear();
            CommandInput.IsEnabled = false;
            ApplyStatus(CoreStatusResult.Failed(CoreConnectionFailure.Unavailable));
            CoreRefreshButton.IsEnabled = true;
            BeginRefresh();
        }

        // Explicit fixture entry point; normal navigation never calls this or creates sample results.
        internal void ShowPreviewData()
        {
            _preview = true;
            TaskStateText.Text = "Running"; RouteText.Text = "Screen"; CoreHealthText.Text = "Connected";
            CommandInput.IsEnabled = true;
            CommandMessageText.Text = "Preview only. Commands are not executed.";
            CurrentActivityList.Items.Add("Reading the active window");
            foreach (string text in new[] { "Opened Calculator", "Found quarterly report.pdf", "Closed Notepad" }) RecentActivityList.Items.Add(text);
            foreach (string text in new[] { "Captured active window", "Detected visible text", "Locating Downloads" })
                LiveMessagesList.Items.Add(new EventFeedEntry(text, "Preview", DateTimeOffset.UtcNow, text, false, false, false));
        }

        private async void OnRefreshCore(object sender, RoutedEventArgs args)
        {
            BeginRefresh();
            if (_commands != null) await _commands.ReconcileAsync();
        }

        private async void OnCommandSubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args) => await SubmitCommandAsync();
        private async void OnRunCommand(object sender, RoutedEventArgs args) => await SubmitCommandAsync();
        private Task SubmitCommandAsync() => !_preview && _commands != null ? _commands.SubmitAsync(CommandInput.Text) : Task.CompletedTask;
        private async void OnStopCommand(object sender, RoutedEventArgs args)
        {
            if (!_preview && _commands != null) await _commands.StopAsync();
        }

        private void OnCommandChanged(CommandView view)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnCommandChanged(_commands!.View)); return; }
            if (!_ownerLifetime.IsCancellationRequested && IsLoaded) ApplyCommand(view);
        }

        private void ApplyCommand(CommandView view)
        {
            CommandInput.IsEnabled = CommandRunButton.IsEnabled = view.CanSubmit;
            CommandStopButton.IsEnabled = !view.StopPending && !_ownerLifetime.IsCancellationRequested;
            CommandMessageText.Text = view.StopMessage is null ? view.Message : view.Message + " " + view.StopMessage;
            CommandIdentityText.Visibility = view.RequestId is null ? Visibility.Collapsed : Visibility.Visible;
            CommandIdentityText.Text = "Request " + view.RequestId + (view.TaskId is null ? "" : " · Task " + view.TaskId);
            if (view.RequestId != null) { TaskStateText.Text = view.State; RouteText.Text = view.Route; }
        }

        private void BeginRefresh()
        {
            if (_preview || _core == null || !IsLoaded || !_healthTask.IsCompleted || _ownerLifetime.IsCancellationRequested) return;
            _healthLifetime?.Dispose();
            _healthLifetime = CancellationTokenSource.CreateLinkedTokenSource(_ownerLifetime);
            CoreRefreshButton.IsEnabled = false;
            CoreHealthText.Text = "Connecting";
            TaskStateText.Text = "Unavailable"; RouteText.Text = "Unavailable";
            _healthTask = RefreshAsync(_core, _healthLifetime.Token);
        }

        private async Task RefreshAsync(ICoreStatusClient core, CancellationToken token)
        {
            try
            {
                CoreStatusResult result = await core.GetStatusAsync(token);
                if (!token.IsCancellationRequested && IsLoaded) ApplyStatus(result);
            }
            catch (OperationCanceledException) { }
            catch (ObjectDisposedException) { if (IsLoaded && !token.IsCancellationRequested) ApplyStatus(CoreStatusResult.Failed(CoreConnectionFailure.Unavailable)); }
            finally { if (!token.IsCancellationRequested && IsLoaded) CoreRefreshButton.IsEnabled = true; }
        }

        private void ApplyStatus(CoreStatusResult result)
        {
            CoreHealthText.Text = result.HealthLabel;
            TaskStateText.Text = result.TaskLabel;
            RouteText.Text = "Unavailable";
            string help = result.Message + " Checked at " + DateTime.Now.ToString("T", CultureInfo.CurrentCulture) + ". Refresh to check again.";
            ToolTipService.SetToolTip(CoreHealthText, help);
            AutomationProperties.SetHelpText(CoreHealthText, help);
            _commands?.SetConnected(result.Status is { Running: true });
            if (_commands?.View.RequestId != null) ApplyCommand(_commands.View);
        }

        private async void OnUnloaded(object sender, RoutedEventArgs args)
        {
            if (_commands != null) _commands.Changed -= OnCommandChanged;
            if (_events != null) _events.Changed -= OnEventsChanged;
            CancellationTokenSource? stopped = _healthLifetime;
            Task previous = _healthTask;
            stopped?.Cancel();
            try { await previous; }
            finally
            {
                if (ReferenceEquals(_healthLifetime, stopped)) _healthLifetime = null;
                stopped?.Dispose();
            }
            if (IsLoaded) BeginRefresh();
        }
    }
}
