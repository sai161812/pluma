using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class VoiceSilenceTimeoutIndicator : UserControl
    {
        public static readonly DependencyProperty ProgressProperty =
            DependencyProperty.Register(
                nameof(Progress),
                typeof(double),
                typeof(VoiceSilenceTimeoutIndicator),
                new PropertyMetadata(0.0, OnProgressChanged));

        public VoiceSilenceTimeoutIndicator()
        {
            InitializeComponent();
        }

        public double Progress
        {
            get => (double)GetValue(ProgressProperty);
            set => SetValue(ProgressProperty, value);
        }

        private static void OnProgressChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceSilenceTimeoutIndicator indicator && indicator.TimeoutBar != null)
            {
                indicator.TimeoutBar.Value = Math.Clamp(indicator.Progress, 0.0, 1.0);
            }
        }
    }
}
