using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class CriticalErrorDialog : ContentDialog
    {
        public static readonly DependencyProperty ErrorMessageProperty = DependencyProperty.Register(
            nameof(ErrorMessage), typeof(string), typeof(CriticalErrorDialog), new PropertyMetadata(string.Empty, OnDisplayChanged));
        public static readonly DependencyProperty SanitizedDetailsProperty = DependencyProperty.Register(
            nameof(SanitizedDetails), typeof(string), typeof(CriticalErrorDialog), new PropertyMetadata(string.Empty, OnDisplayChanged));
        public static readonly DependencyProperty CanRestartProperty = DependencyProperty.Register(
            nameof(CanRestart), typeof(bool), typeof(CriticalErrorDialog), new PropertyMetadata(false, OnDisplayChanged));

        public CriticalErrorDialog()
        {
            InitializeComponent();
            Opened += (_, _) => { DetailsExpander.IsExpanded = false; ApplyDisplay(); };
            ApplyDisplay();
        }

        // The host enables recovery only when it can handle the request under core ownership.
        public event EventHandler? RestartRequested;
        public string ErrorMessage { get => (string)GetValue(ErrorMessageProperty); set => SetValue(ErrorMessageProperty, value); }
        public string SanitizedDetails { get => (string)GetValue(SanitizedDetailsProperty); set => SetValue(SanitizedDetailsProperty, value); }
        public bool CanRestart { get => (bool)GetValue(CanRestartProperty); set => SetValue(CanRestartProperty, value); }

        private static void OnDisplayChanged(DependencyObject d, DependencyPropertyChangedEventArgs e) =>
            ((CriticalErrorDialog)d).ApplyDisplay();

        private void ApplyDisplay()
        {
            if (ErrorText == null) return;
            ErrorText.Text = PopupText.Message(ErrorMessage);
            DetailsText.Text = PopupText.Message(SanitizedDetails);
            DetailsExpander.Visibility = string.IsNullOrWhiteSpace(SanitizedDetails) ? Visibility.Collapsed : Visibility.Visible;
            IsPrimaryButtonEnabled = CanRestart;
        }

        private void OnRestartClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
        {
            // Keep the failure visible until the host has verified recovery and calls Hide().
            args.Cancel = true;
            if (!CanRestart || RestartRequested == null) return;
            CanRestart = false;
            RestartRequested.Invoke(this, EventArgs.Empty);
        }
    }
}
