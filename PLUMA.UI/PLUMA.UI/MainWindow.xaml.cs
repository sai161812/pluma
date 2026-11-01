using Microsoft.UI.Xaml;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Foundation;
using Windows.Foundation.Collections;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace PLUMA.UI
{
    /// <summary>
    /// An empty window that can be used on its own or navigated to within a Frame.
    /// </summary>
    public sealed partial class MainWindow : Window
    {
        private PopupStackHost? _popups;
        private readonly CoreIpcClient _coreStatus;
        private readonly CancellationTokenSource _healthLifetime = new();
        private bool _closed;
        private ConfirmationController? _confirmations;
        private Task _confirmationTask = Task.CompletedTask;
        private readonly EventFeedController _events;
        private Task _eventTask = Task.CompletedTask;
        private readonly TaskCompletionSource _closedDrain = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly CommandController _commands;
        private readonly DispatcherQueue _dispatcher;
        private string? _lastStopMessage;
        public PopupStackHost Popups
        {
            get
            {
                ObjectDisposedException.ThrowIf(_closed, this);
                return _popups ??= new PopupStackHost(this);
            }
        }

        public MainWindow() : this(CoreIpcOptions.ForCurrentUser()) { }
        internal MainWindow(CoreIpcOptions options)
        {
            _coreStatus = new CoreIpcClient(options);
            InitializeComponent();
            _dispatcher = DispatcherQueue;
            _commands = new CommandController(new CoreCommandClient(_coreStatus));
            _commands.Changed += OnCommandChanged;
            _events = new EventFeedController(new CoreEventFeedClient(_coreStatus));
            _events.Notice += OnEventNotice;
            _events.Surface += OnActivitySurface;
            _runtime = new RuntimeController(_coreStatus.GetRuntimeAsync);
            _runtime.Changed += OnRuntimeChanged;
            _runtime.WorkerTerminated += OnWorkerTerminated;

            // Extend content into the title bar so we can show a subtle app title
            // while retaining the native caption buttons. Register the AppTitleBar
            // element as the draggable title region.
            ExtendsContentIntoTitleBar = true;
            SetTitleBar(AppTitleBar);

            // Navigate to the default page (Dashboard)
            NavigateDashboard();
            ContentFrame.Loaded += (_, _) =>
            {
                if (_closed || _confirmations is not null) return;
                _confirmations = new ConfirmationController(new CoreConfirmationClient(_coreStatus),
                    new NativeConfirmationPresenter(() => ContentFrame.XamlRoot));
                _confirmationTask = _confirmations.RunAsync(_healthLifetime.Token);
                _eventTask = _events.RunAsync(_healthLifetime.Token);
                _runtimeTask = _runtime.RunAsync(_healthLifetime.Token);
            };
            Closed += async (_, _) =>
            {
                _closed = true; _healthLifetime.Cancel(); _popups?.Dispose();
                _commands.Changed -= OnCommandChanged;
                _events.Notice -= OnEventNotice;
                _events.Surface -= OnActivitySurface;
                _runtime.Changed -= OnRuntimeChanged;
                _runtime.WorkerTerminated -= OnWorkerTerminated;
                await _commands.DisposeAsync();
                await _confirmationTask;
                await _eventTask;
                await _runtimeTask;
                await _coreStatus.DisposeAsync(); _healthLifetime.Dispose();
                _closedDrain.TrySetResult();
            };
        }

        private void NavigateDashboard()
        {
            ContentFrame.Navigate(typeof(DashboardPage));
            if (ContentFrame.Content is DashboardPage dashboard)
            {
                dashboard.AttachCommandController(_commands);
                dashboard.AttachCoreClient(_coreStatus, _healthLifetime.Token);
                dashboard.AttachEventController(_events);
                dashboard.AttachRuntimeController(_runtime);
            }
        }

        private readonly RuntimeController _runtime;
        internal Task ObservationLifetime => _closedDrain.Task;
        internal event Action<string, int, bool>? NotificationPresented;
        internal DashboardPage? Dashboard => ContentFrame.Content as DashboardPage;
        internal void NavigateForAcceptance(bool dashboard)
        { if (dashboard) NavigateDashboard(); else ContentFrame.Navigate(typeof(SettingsPage)); }
        private void OnWorkerTerminated(CoreRequestProtocol.WorkerTermination proof)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnWorkerTerminated(proof)); return; }
            if (_closed) return;
            PresentNotification(proof.Key, 21, new WorkerTerminationFlash { IsOpen = true,
                WorkerPid = proof.Pid.ToString(System.Globalization.CultureInfo.InvariantCulture),
                ElapsedTime = "Unavailable", Heading = "Owned worker terminated",
                Message = "The owned tool worker exited; its absence was verified." }, TimeSpan.FromSeconds(4));
        }
        private Task _runtimeTask = Task.CompletedTask;
        private readonly System.Collections.Generic.HashSet<string> _runtimeKeys = new();
        private readonly System.Collections.Generic.HashSet<string> _terminalTasks = new();
        private readonly System.Collections.Generic.Queue<string> _terminalOrder = new();
        private int _runtimeOffset;
        private void OnRuntimeChanged(RuntimeView view)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnRuntimeChanged(_runtime.View)); return; }
            if (_closed) return;
            var current = new System.Collections.Generic.HashSet<string>();
            var pending = new System.Collections.Generic.List<(string Key, int Surface, CoreRequestProtocol.RuntimeTask Task)>();
            foreach (var task in view.Tasks)
            {
                if (_terminalTasks.Contains(task.TaskId)) continue;
                foreach (var item in RuntimePresentation.Keys(task))
                {
                    current.Add(item.Key);
                    pending.Add((item.Key, item.Surface, task));
                }
            }
            // Bound UI work even when many tasks are active. Rotate fairly;
            // host refusal never becomes a claim that a card was displayed.
            for (int count = 0; count < Math.Min(12, pending.Count); count++)
            {
                    var item = pending[(_runtimeOffset + count) % pending.Count];
                    var task = item.Task;
                    if (!Popups.Update(item.Key, control => RuntimePresentation.Apply(control, item.Surface, task)))
                        if (Popups.Count < 32)
                            Popups.Present(item.Key, item.Surface, RuntimePresentation.Create(item.Surface, task), persistent: true);
            }
            _runtimeOffset = pending.Count == 0 ? 0 : (_runtimeOffset + 12) % pending.Count;
            foreach (string key in _runtimeKeys) if (!current.Contains(key)) Popups.Dismiss(key);
            _runtimeKeys.Clear(); foreach (string key in current) _runtimeKeys.Add(key);
        }

        private void OnActivitySurface(ActivitySurfaceFact fact)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnActivitySurface(fact)); return; }
            if (_closed) return;
            PresentNotification(fact.Key, fact.Surface, ActivitySurfacePresentation.Create(fact), TimeSpan.FromSeconds(fact.Surface == 6 ? 2 : 4));
        }

        private void PresentNotification(string key, int surface, FrameworkElement content, TimeSpan lifetime)
        {
            // Keep one admission slot for priority STOP feedback. Refused transient
            // cards remain factual feed/history entries; no unbounded toast queue.
            bool accepted = Popups.Count < PopupStackState.Capacity - 1 &&
                Popups.Present(key, surface, content, persistent: false, lifetime: lifetime);
            NotificationPresented?.Invoke(key, surface, accepted);
        }

        private void OnEventNotice(EventFeedEntry entry)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnEventNotice(entry)); return; }
            if (_closed) return;
            if (entry.Terminal && _terminalTasks.Add(entry.TaskId))
            {
                _terminalOrder.Enqueue(entry.TaskId);
                if (_terminalOrder.Count > 512) _terminalTasks.Remove(_terminalOrder.Dequeue());
                foreach (string key in _runtimeKeys)
                    if (key.EndsWith(entry.TaskId, StringComparison.Ordinal)) Popups.Dismiss(key);
            }
            PresentNotification("ledger-notice-" + entry.TaskId, 24, EventNoticePresentation.Create(entry), TimeSpan.FromSeconds(4));
        }

        private void OnCommandChanged(CommandView view)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnCommandChanged(_commands.View)); return; }
            if (_closed || view.StopMessage == _lastStopMessage) return;
            _lastStopMessage = view.StopMessage;
            if (view.StopMessage is null) { _popups?.Dismiss("command-stop"); return; }
            Popups.Present("command-stop", 20, new CancellationAnimation
            {
                Heading = view.StopPending ? "Requesting STOP" : "STOP status",
                Message = view.StopMessage, TaskId = view.TaskId ?? "All tasks",
                ElapsedTime = (DateTimeOffset.UtcNow - (view.StopRequestedAt ?? DateTimeOffset.UtcNow)).TotalSeconds.ToString("0.0", CultureInfo.CurrentCulture) + "s"
            }, persistent: false, lifetime: TimeSpan.FromSeconds(4));
        }

        private void NavView_ItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
        {
            if (args.IsSettingsInvoked)
            {
                ContentFrame.Navigate(typeof(SettingsPage));
                return;
            }

            if (args.InvokedItemContainer is NavigationViewItem invokedItem && invokedItem.Tag is string tag)
            {
                switch (tag)
                {
                    case "dashboard":
                        NavigateDashboard();
                        break;
                    case "history":
                        ContentFrame.Navigate(typeof(HistoryPage));
                        break;
                }
            }
        }
    }
}
