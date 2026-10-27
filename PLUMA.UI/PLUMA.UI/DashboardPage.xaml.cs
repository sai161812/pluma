using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using System;
using System.Globalization;
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

        public DashboardPage()
        {
            this.InitializeComponent();
            Loaded += (_, _) => BeginRefresh();
            Unloaded += OnUnloaded;
        }

        internal void AttachCoreClient(ICoreStatusClient core, CancellationToken ownerLifetime = default)
        {
            _core = core;
            _ownerLifetime = ownerLifetime;
            _preview = false;
            CurrentActivityList.Items.Clear(); RecentActivityList.Items.Clear(); LiveMessagesList.Items.Clear();
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
            CurrentActivityList.Items.Add("Reading the active window");
            foreach (string text in new[] { "Opened Calculator", "Found quarterly report.pdf", "Closed Notepad" }) RecentActivityList.Items.Add(text);
            foreach (string text in new[] { "Captured active window", "Detected visible text", "Locating Downloads" }) LiveMessagesList.Items.Add(text);
        }

        private void OnRefreshCore(object sender, RoutedEventArgs args) => BeginRefresh();

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
        }

        private async void OnUnloaded(object sender, RoutedEventArgs args)
        {
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
