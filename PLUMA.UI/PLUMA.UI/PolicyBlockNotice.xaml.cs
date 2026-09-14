using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class PolicyBlockNotice : InfoBar
    {
        public static readonly DependencyProperty ToolNameProperty =
            DependencyProperty.Register(
                nameof(ToolName),
                typeof(string),
                typeof(PolicyBlockNotice),
                new PropertyMetadata(string.Empty, OnDisplayPropertyChanged));

        public static readonly DependencyProperty MatchedRuleProperty =
            DependencyProperty.Register(
                nameof(MatchedRule),
                typeof(string),
                typeof(PolicyBlockNotice),
                new PropertyMetadata(string.Empty, OnDisplayPropertyChanged));

        public static readonly DependencyProperty IsNoticeOpenProperty =
            DependencyProperty.Register(
                nameof(IsNoticeOpen),
                typeof(bool),
                typeof(PolicyBlockNotice),
                new PropertyMetadata(false, OnIsNoticeOpenChanged));

        public PolicyBlockNotice()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        public string ToolName
        {
            get => (string)GetValue(ToolNameProperty);
            set => SetValue(ToolNameProperty, value);
        }

        public string MatchedRule
        {
            get => (string)GetValue(MatchedRuleProperty);
            set => SetValue(MatchedRuleProperty, value);
        }

        public bool IsNoticeOpen
        {
            get => (bool)GetValue(IsNoticeOpenProperty);
            set => SetValue(IsNoticeOpenProperty, value);
        }

        public void ShowNotice()
        {
            IsNoticeOpen = true;
        }

        public void HideNotice()
        {
            IsNoticeOpen = false;
        }

        private static void OnDisplayPropertyChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is PolicyBlockNotice notice)
            {
                notice.ApplyDisplayValues();
            }
        }

        private static void OnIsNoticeOpenChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is PolicyBlockNotice notice && notice != null)
            {
                notice.IsOpen = (bool)e.NewValue;
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            ApplyDisplayValues();
            IsOpen = IsNoticeOpen;
        }

        private void ApplyDisplayValues()
        {
            string toolName = ToolName ?? string.Empty;
            string matchedRule = MatchedRule ?? string.Empty;
            Message = string.IsNullOrWhiteSpace(toolName)
                ? matchedRule
                : $"{toolName} — {matchedRule}";
        }

        private void OnCloseButtonClick(InfoBar sender, object args)
        {
            IsNoticeOpen = false;
        }
    }
}
