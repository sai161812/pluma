using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    /// <summary>In-app notice, consistent with PolicyBlockNotice; no shell registration.</summary>
    public sealed partial class ToastNotification : UserControl, IHostedPopup
    {
        private bool _isHosted;
        public bool IsHosted
        {
            get => _isHosted;
            set { _isHosted = value; if (value) _dismissTimer.Stop(); }
        }
        public event EventHandler? DismissRequested;
        private readonly DispatcherTimer _dismissTimer = new();

        public ToastNotification()
        {
            InitializeComponent();
            Notice.Closing += (_, args) =>
            {
                if (!IsHosted) return;
                args.Cancel = true;
                DismissRequested?.Invoke(this, EventArgs.Empty);
            };
            _dismissTimer.Tick += (_, _) => Hide();
            Loaded += (_, _) => StartDismissTimer();
            Unloaded += (_, _) => { _dismissTimer.Stop(); if (!IsHosted) Hide(); };
        }

        public bool IsOpen => Notice.IsOpen;

        // Display content must already be redacted by the host. Empty messages close the notice.
        public void Show(string sanitizedMessage, InfoBarSeverity severity = InfoBarSeverity.Informational,
                         TimeSpan? duration = null)
        {
            TimeSpan timeout = duration ?? TimeSpan.FromSeconds(4);
            if (timeout <= TimeSpan.Zero || timeout > TimeSpan.FromMinutes(1))
                throw new ArgumentOutOfRangeException(nameof(duration));

            _dismissTimer.Stop();
            string message = PopupText.Message(sanitizedMessage);
            if (IsHosted && string.IsNullOrWhiteSpace(message)) { Hide(); return; }
            NoticeText.Text = message;
            Notice.Severity = severity;
            Notice.IsOpen = !string.IsNullOrWhiteSpace(NoticeText.DisplayText);
            Visibility = Notice.IsOpen ? Visibility.Visible : Visibility.Collapsed;
            _dismissTimer.Interval = timeout;
            StartDismissTimer();
        }

        public void Hide()
        {
            _dismissTimer.Stop();
            if (IsHosted) { DismissRequested?.Invoke(this, EventArgs.Empty); return; }
            Notice.IsOpen = false;
            Visibility = Visibility.Collapsed;
        }

        private void StartDismissTimer()
        {
            if (!IsHosted && IsLoaded && IsOpen) _dismissTimer.Start();
        }

        private void OnCloseButtonClick(InfoBar sender, object args) => Hide();
    }
}
