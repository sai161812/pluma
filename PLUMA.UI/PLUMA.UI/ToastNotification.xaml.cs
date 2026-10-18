using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    /// <summary>In-app notice, consistent with PolicyBlockNotice; no shell registration.</summary>
    public sealed partial class ToastNotification : UserControl
    {
        private readonly DispatcherTimer _dismissTimer = new();

        public ToastNotification()
        {
            InitializeComponent();
            _dismissTimer.Tick += (_, _) => Hide();
            Loaded += (_, _) => StartDismissTimer();
            Unloaded += (_, _) => Hide();
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
            NoticeText.Text = PopupText.Message(sanitizedMessage);
            Notice.Severity = severity;
            Notice.IsOpen = !string.IsNullOrWhiteSpace(sanitizedMessage);
            Visibility = Notice.IsOpen ? Visibility.Visible : Visibility.Collapsed;
            _dismissTimer.Interval = timeout;
            StartDismissTimer();
        }

        public void Hide()
        {
            _dismissTimer.Stop();
            Notice.IsOpen = false;
            Visibility = Visibility.Collapsed;
        }

        private void StartDismissTimer()
        {
            if (IsLoaded && IsOpen) _dismissTimer.Start();
        }

        private void OnCloseButtonClick(InfoBar sender, object args) => Hide();
    }
}
