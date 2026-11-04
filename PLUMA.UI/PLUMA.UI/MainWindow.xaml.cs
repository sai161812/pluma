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
        private NativeConfirmationPresenter? _confirmationPresenter;
        internal CommandView CurrentCommandForAcceptance => _commands.View;
        internal RiskApprovalDialog? ApprovalForAcceptance => _confirmationPresenter?.ActiveDialog;
        private Task _confirmationTask = Task.CompletedTask, _observerStartupTask = Task.CompletedTask;
        private readonly EventFeedController _events;
        private Task _eventTask = Task.CompletedTask, _activityNavigationTask = Task.CompletedTask;
        private NativeActivityTray? _activityTray;
        private readonly HashSet<string> _activityRequests = new();
        private readonly Queue<string> _activityRequestOrder = new();
        private readonly TaskCompletionSource _closedDrain = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly CommandController _commands;
        private readonly DispatcherQueue _dispatcher;
        private readonly PerceptionFeedbackHost _feedback;
        internal PerceptionFeedbackHost FeedbackForAcceptance => _feedback;
        internal Task StopForAcceptance() => _commands.StopAsync();
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
            _feedback = new PerceptionFeedbackHost(this);
            _commands = new CommandController(new CoreCommandClient(_coreStatus));
            _commands.Changed += OnCommandChanged;
            _events = new EventFeedController(new CoreEventFeedClient(_coreStatus));
            _events.Notice += OnEventNotice;
            _events.Surface += OnActivitySurface;
            _runtime = new RuntimeController(_coreStatus.GetRuntimeAsync, perception: _coreStatus.GetPerceptionAsync);
            _runtime.PerceptionChanged += OnPerception;
            _runtime.Changed += OnRuntimeChanged;
            _runtime.TextRequested += OpenCommandEntry;
            _runtime.WorkerTerminated += OnWorkerTerminated;
            _voice = new VoiceController(_coreStatus.GetVoiceAsync);
            _voice.Changed += OnVoiceChanged;
            _history = new HistoryController(_coreStatus.GetHistoryPageAsync);
            _savedDetail = new SavedDetailController(_coreStatus);
            _health=new HealthController(_coreStatus.GetHealthAsync,_commands);
            _commands.Changed+=_health.OnCommand;
            _health.Changed+=OnHealthChanged;
            _settings = new SettingsController(_coreStatus.GetSettingsEditAsync, _coreStatus.GetSettingsAsync, _commands);
            _commands.Changed += _settings.OnCommandChanged;

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
                _confirmationPresenter = new NativeConfirmationPresenter(() => ContentFrame.XamlRoot);
                _confirmations = new ConfirmationController(new CoreConfirmationClient(_coreStatus), _confirmationPresenter);
                _activityTray = new NativeActivityTray(this, OpenActivity);
                _observerStartupTask = StartObserversAsync(Dashboard?.InitialHealthReadback ?? Task.CompletedTask, _healthLifetime.Token);
            };
            Closed += async (_, _) =>
            {
                _closed = true; _healthLifetime.Cancel(); _feedback.Dispose(); _popups?.Dispose(); _activityTray?.Dispose();
                _commands.Changed -= OnCommandChanged;
                _events.Notice -= OnEventNotice;
                _events.Surface -= OnActivitySurface;
                _runtime.Changed -= OnRuntimeChanged;
                _runtime.PerceptionChanged -= OnPerception;
                _runtime.TextRequested -= OpenCommandEntry;
                _runtime.WorkerTerminated -= OnWorkerTerminated;
                _voice.Changed -= OnVoiceChanged;
                await _commands.DisposeAsync();
                _commands.Changed -= _settings.OnCommandChanged;
                await _settings.DisposeAsync();
                _commands.Changed-=_health.OnCommand;
                _health.Changed-=OnHealthChanged;
                _critical?.Hide();
                await _health.DisposeAsync();
                await _recoveryTask;
                await _healthDialogTask;
                await _observerStartupTask;
                await _confirmationTask;
                await _eventTask;
                await _runtimeTask;
                await _voiceTask;
                await _activityNavigationTask;
                await _history.DisposeAsync();
                await _savedDetail.DisposeAsync();
                await _coreStatus.DisposeAsync(); _healthLifetime.Dispose();
                _closedDrain.TrySetResult();
            };
        }

        private void NavigateDashboard()
        {
            ContentFrame.Navigate(typeof(DashboardPage));
            if (ContentFrame.Content is DashboardPage dashboard)
            {
                dashboard.AttachHealth(_health);
                dashboard.SetupRequested+=OpenSetup;
                dashboard.RecoveryRequested+=OpenRecovery;
                dashboard.AttachCommandController(_commands);
                dashboard.AttachCoreClient(_coreStatus, _healthLifetime.Token);
                dashboard.AttachEventController(_events);
                dashboard.AttachRuntimeController(_runtime);
            }
        }

        private readonly HealthController _health;
        private CriticalErrorDialog? _critical;
        private Task _healthDialogTask=Task.CompletedTask,_recoveryTask=Task.CompletedTask;
        internal SetupWizard? Setup=>ContentFrame.Content as SetupWizard;
        internal CriticalErrorDialog? CriticalForAcceptance=>_critical;
        internal HealthView HealthForAcceptance=>_health.View;
        internal void OpenSetupForAcceptance()=>OpenSetup();
        private async void OpenSetup()
        {
            ContentFrame.Navigate(typeof(SetupWizard));
            if(Setup is {} page)
            {
                page.AttachHealth(_health,_commands,_healthLifetime.Token);
                page.ContinueRequested+=async (_,_)=>{if(await _health.VerifyContinueAsync(_healthLifetime.Token)&&!_closed)NavigateDashboard();};
                await _health.RefreshAsync(_healthLifetime.Token);
            }
        }
        private void OpenRecovery(){if(_healthDialogTask.IsCompleted)_healthDialogTask=ShowRecoveryAsync();}
        private async Task ShowRecoveryAsync()
        {
            await _health.RefreshAsync(_healthLifetime.Token);
            if(_closed||_confirmationPresenter?.ActiveDialog is not null)return;
            var dialog=new CriticalErrorDialog{XamlRoot=ContentFrame.XamlRoot,Title="Core recovery",ErrorMessage=_health.View.Message,
                SanitizedDetails=_health.View.Snapshot?.Code??"Authenticated Core identity unavailable. Start Core manually; no replacement is launched.",CanRestart=_health.View.CanRestart};
            _critical=dialog;
            dialog.RestartRequested+=(_,_)=>{if(_recoveryTask.IsCompleted)_recoveryTask=RestartFromDialog(dialog);};
            try{await dialog.ShowAsync();}finally{if(ReferenceEquals(_critical,dialog))_critical=null;}
        }
        private async Task RestartFromDialog(CriticalErrorDialog dialog)
        {
            // Let the exact existing policy approval surface own the modal root.
            // Dashboard health remains factual while the approval is displayed.
            dialog.Hide();await _healthDialogTask;
            await _health.RestartAsync(_healthLifetime.Token);
            if(!_closed&&_health.View.Snapshot?.State!="READY")_healthDialogTask=ShowRecoveryAsync();
        }
        private void OnHealthChanged(HealthView view)
        {
            if(!_dispatcher.HasThreadAccess){_dispatcher.TryEnqueue(()=>OnHealthChanged(_health.View));return;}
            if(_closed)return;
            if(_critical is {} dialog){dialog.ErrorMessage=view.Message;dialog.CanRestart=view.CanRestart;}
        }
        private readonly RuntimeController _runtime;
        private readonly HistoryController _history;
        private readonly SavedDetailController _savedDetail;
        private readonly SettingsController _settings;
        internal SettingsPage? Settings => ContentFrame.Content as SettingsPage;
        internal void NavigateSettingsForAcceptance() => NavigateSettings();
        private void NavigateSettings()
        {
            ContentFrame.Navigate(typeof(SettingsPage));
            if (ContentFrame.Content is SettingsPage page) page.AttachSettings(_settings, _commands, _healthLifetime.Token);
        }
        internal HistoryPage? History => ContentFrame.Content as HistoryPage;
        internal void NavigateHistoryForAcceptance() => NavigateHistory();
        private void NavigateHistory()
        {
            ContentFrame.Navigate(typeof(HistoryPage));
            if (ContentFrame.Content is HistoryPage page) page.AttachHistory(_history, _healthLifetime.Token);
            if (ContentFrame.Content is HistoryPage history) history.AttachDetail(_savedDetail, _commands);
        }
        private readonly VoiceController _voice;
        private Task _voiceTask = Task.CompletedTask;
        private async Task StartObserversAsync(Task initialHealth, CancellationToken token)
        {
            try
            {
                // Initial admission health is user-facing. Drain it before the
                // four ordinary background readers contend for the same slots.
                await initialHealth.WaitAsync(token);
                token.ThrowIfCancellationRequested();
                _confirmationTask = _coreStatus.RunBackgroundAsync(() => _confirmations!.RunAsync(token));
                _eventTask = _coreStatus.RunBackgroundAsync(() => _events.RunAsync(token));
                _runtimeTask = _coreStatus.RunBackgroundAsync(() => _runtime.RunAsync(token));
                _voiceTask = _coreStatus.RunBackgroundAsync(() => _voice.RunAsync(token));
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        }
        private void OnVoiceChanged(VoiceObservation observation)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnVoiceChanged(_voice.View)); return; }
            if (_closed) return;
            if (observation.Voice is not { } value)
            {
                _popups?.Update("voice", control => ((VoiceOverlay)control).ClearTransient());
                _popups?.Dismiss("voice");
                return;
            }
            if (!Popups.Update("voice", control => ((VoiceOverlay)control).ApplyVoice(value)) &&
                Popups.Count < PopupStackState.Capacity - 1)
            {
                var overlay = new VoiceOverlay(); overlay.ApplyVoice(value);
                Popups.Present("voice", 11, overlay, persistent: true);
            }
        }
        internal Task ObservationLifetime => _closedDrain.Task;
        internal event Action<string, int, bool>? NotificationPresented;
        internal DashboardPage? Dashboard => ContentFrame.Content as DashboardPage;
        internal void NavigateForAcceptance(bool dashboard)
        { if (dashboard) NavigateDashboard(); else NavigateSettings(); }
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
        private void OpenCommandEntry(DateTimeOffset requested)
        {
            if(!_dispatcher.HasThreadAccess){_dispatcher.TryEnqueue(()=>OpenCommandEntry(requested));return;}
            var age=DateTimeOffset.UtcNow-requested;
            if(_closed || age<TimeSpan.Zero || age>TimeSpan.FromSeconds(3))return;
            Activate(); NavigateDashboard();
            if(Dashboard?.FindName("CommandInput") is Microsoft.UI.Xaml.Controls.AutoSuggestBox input)
                input.Focus(FocusState.Programmatic);
        }
        private void OnRuntimeChanged(RuntimeView view)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnRuntimeChanged(_runtime.View)); return; }
            if (_closed) return;
            _feedback.Runtime(view);
            if(view.CoreReady is not null)_commands.SetCoreReady(view.CoreReady);
            _health.OnRuntime(view);
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

        internal NativeActivityTray? ActivityTrayForAcceptance => _activityTray;
        private void OpenActivity()
        {
            if (_closed) return;
            Activate(); NavigateHistory();
            if (_activityNavigationTask.IsCompleted)
                _activityNavigationTask = _history.RefreshAsync(_history.View.Search, _healthLifetime.Token);
        }

        private void OnActivitySurface(ActivitySurfaceFact fact)
        {
            if (!_dispatcher.HasThreadAccess)
            { _dispatcher.TryEnqueue(() => OnActivitySurface(fact)); return; }
            if (_closed) return;
            if (fact.Action is { Tool: "show_activity", Verified: true, ErrorRecorded: false, PolicyDenied: false } action &&
                _activityRequests.Add(fact.TaskId + "/" + action.ActionId))
            {
                _activityRequestOrder.Enqueue(fact.TaskId + "/" + action.ActionId);
                if (_activityRequestOrder.Count > 512) _activityRequests.Remove(_activityRequestOrder.Dequeue());
                OpenActivity();
            }
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
                _runtime.NotePerceptionActivity();
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
            if (_closed) return;
            if (view.StopPending) _feedback.Stop();
            if (view.StopMessage == _lastStopMessage) return;
            _lastStopMessage = view.StopMessage;
            if (view.StopMessage is null) { _popups?.Dismiss("command-stop"); return; }
            Popups.Present("command-stop", 20, new CancellationAnimation
            {
                Heading = view.StopPending ? "Requesting STOP" : "STOP status",
                Message = view.StopMessage, TaskId = view.TaskId ?? "All tasks",
                ElapsedTime = (DateTimeOffset.UtcNow - (view.StopRequestedAt ?? DateTimeOffset.UtcNow)).TotalSeconds.ToString("0.0", CultureInfo.CurrentCulture) + "s"
            }, persistent: false, lifetime: TimeSpan.FromSeconds(4));
        }

        private void OnPerception(CoreRequestProtocol.PerceptionSnapshot? frame)
        {
            if (!_dispatcher.HasThreadAccess) { _dispatcher.TryEnqueue(() => OnPerception(frame)); return; }
            if (!_closed) _feedback.Observe(frame);
        }

        private void NavView_ItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
        {
            if (args.IsSettingsInvoked)
            {
                NavigateSettings();
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
                        NavigateHistory();
                        break;
                }
            }
        }
    }
}
