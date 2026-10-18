using System;
using System.Globalization;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class CoreHealthIndicator : UserControl
    {
        public static readonly DependencyProperty IsConnectedProperty = DependencyProperty.Register(
            nameof(IsConnected), typeof(bool), typeof(CoreHealthIndicator), new PropertyMetadata(false, OnStateChanged));
        public static readonly DependencyProperty PingLatencyMsProperty = DependencyProperty.Register(
            nameof(PingLatencyMs), typeof(double), typeof(CoreHealthIndicator), new PropertyMetadata(double.NaN, OnStateChanged));

        public CoreHealthIndicator()
        {
            InitializeComponent();
            Loaded += (_, _) => ApplyState();
            ApplyState();
        }

        public bool IsConnected { get => (bool)GetValue(IsConnectedProperty); set => SetValue(IsConnectedProperty, value); }
        // NaN represents an unavailable measurement. No heartbeat or polling runs in this control.
        public double PingLatencyMs { get => (double)GetValue(PingLatencyMsProperty); set => SetValue(PingLatencyMsProperty, value); }

        private static void OnStateChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            var indicator = (CoreHealthIndicator)d;
            if (e.Property == IsConnectedProperty && !(bool)e.NewValue)
                indicator.PingLatencyMs = double.NaN;
            indicator.ApplyState();
        }

        private void ApplyState()
        {
            if (StatusText == null) return;
            StatusText.Text = IsConnected ? "Connected" : "Disconnected";
            VisualStateManager.GoToState(this, IsConnected ? "Connected" : "Disconnected", false);
            bool showLatency = IsConnected && double.IsFinite(PingLatencyMs) && PingLatencyMs >= 0;
            LatencyText.Text = showLatency ? PingLatencyMs.ToString("0", CultureInfo.CurrentCulture) + " ms" : string.Empty;
            LatencyText.Visibility = showLatency ? Visibility.Visible : Visibility.Collapsed;
            Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(StatusBadge, StatusText.Text);
        }
    }
}
