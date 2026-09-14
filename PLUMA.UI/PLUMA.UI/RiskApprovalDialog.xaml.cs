using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class RiskApprovalDialog : ContentDialog
    {
        public static readonly DependencyProperty ToolNameProperty =
            DependencyProperty.Register(
                nameof(ToolName),
                typeof(string),
                typeof(RiskApprovalDialog),
                new PropertyMetadata(string.Empty, OnDisplayPropertyChanged));

        public static readonly DependencyProperty RiskClassProperty =
            DependencyProperty.Register(
                nameof(RiskClass),
                typeof(string),
                typeof(RiskApprovalDialog),
                new PropertyMetadata(string.Empty, OnDisplayPropertyChanged));

        public static readonly DependencyProperty SanitizedArgumentsProperty =
            DependencyProperty.Register(
                nameof(SanitizedArguments),
                typeof(string),
                typeof(RiskApprovalDialog),
                new PropertyMetadata(string.Empty, OnDisplayPropertyChanged));

        public RiskApprovalDialog()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        public event EventHandler? ApprovalRequested;
        public event EventHandler? DenialRequested;

        public string ToolName
        {
            get => (string)GetValue(ToolNameProperty);
            set => SetValue(ToolNameProperty, value);
        }

        public string RiskClass
        {
            get => (string)GetValue(RiskClassProperty);
            set => SetValue(RiskClassProperty, value);
        }

        public string SanitizedArguments
        {
            get => (string)GetValue(SanitizedArgumentsProperty);
            set => SetValue(SanitizedArgumentsProperty, value);
        }

        private static void OnDisplayPropertyChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is RiskApprovalDialog dialog)
            {
                dialog.ApplyDisplayValues();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            ApplyDisplayValues();
        }

        private void ApplyDisplayValues()
        {
            if (ToolNameText == null)
            {
                return;
            }

            ToolNameText.Text = ToolName ?? string.Empty;
            RiskClassText.Text = RiskClass ?? string.Empty;
            SanitizedArgumentsText.Text = SanitizedArguments ?? string.Empty;
        }

        private void OnPrimaryButtonClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
        {
            ApprovalRequested?.Invoke(this, EventArgs.Empty);
        }

        private void OnSecondaryButtonClick(ContentDialog sender, ContentDialogButtonClickEventArgs args)
        {
            DenialRequested?.Invoke(this, EventArgs.Empty);
        }

        private void OnClosing(ContentDialog sender, ContentDialogClosingEventArgs args)
        {
            if (args.Result == ContentDialogResult.None)
            {
                DenialRequested?.Invoke(this, EventArgs.Empty);
            }
        }
    }
}
