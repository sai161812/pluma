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
        private readonly CoreIpcClient _coreStatus = new();
        private readonly CancellationTokenSource _healthLifetime = new();
        private bool _closed;
        private ConfirmationController? _confirmations;
        private Task _confirmationTask = Task.CompletedTask;
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

        public MainWindow()
        {
            InitializeComponent();
            _dispatcher = DispatcherQueue;
            _commands = new CommandController(new CoreCommandClient(_coreStatus));
            _commands.Changed += OnCommandChanged;

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
            };
            Closed += async (_, _) =>
            {
                _closed = true; _healthLifetime.Cancel(); _popups?.Dispose();
                _commands.Changed -= OnCommandChanged;
                await _commands.DisposeAsync();
                await _confirmationTask;
                await _coreStatus.DisposeAsync(); _healthLifetime.Dispose();
            };
        }

        private void NavigateDashboard()
        {
            ContentFrame.Navigate(typeof(DashboardPage));
            if (ContentFrame.Content is DashboardPage dashboard)
            {
                dashboard.AttachCommandController(_commands);
                dashboard.AttachCoreClient(_coreStatus, _healthLifetime.Token);
            }
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
