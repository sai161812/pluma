using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class CancellationAnimation : UserControl
    {
        public static readonly DependencyProperty HeadingProperty = RegisterTextProperty(nameof(Heading), "Stopping…");
        public static readonly DependencyProperty MessageProperty = RegisterTextProperty(nameof(Message), "Cancelling the current task safely");
        public static readonly DependencyProperty TaskIdProperty = RegisterTextProperty(nameof(TaskId), "TASK-2026-0204");
        public static readonly DependencyProperty ElapsedTimeProperty = RegisterTextProperty(nameof(ElapsedTime), "00:12");
        public static readonly DependencyProperty IsActiveProperty =
            DependencyProperty.Register(nameof(IsActive), typeof(bool), typeof(CancellationAnimation), new PropertyMetadata(false, OnIsActiveChanged));

        public CancellationAnimation()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        public string Heading { get => (string)GetValue(HeadingProperty); set => SetValue(HeadingProperty, value); }
        public string Message { get => (string)GetValue(MessageProperty); set => SetValue(MessageProperty, value); }
        public string TaskId { get => (string)GetValue(TaskIdProperty); set => SetValue(TaskIdProperty, value); }
        public string ElapsedTime { get => (string)GetValue(ElapsedTimeProperty); set => SetValue(ElapsedTimeProperty, value); }
        public bool IsActive { get => (bool)GetValue(IsActiveProperty); set => SetValue(IsActiveProperty, value); }

        public void Show()
        {
            IsActive = true;
            FadeOutStoryboard.Stop();
            Visibility = Visibility.Visible;
            RootBorder.Opacity = 0;
            FadeInStoryboard.Begin();
        }

        public void Hide()
        {
            IsActive = false;
            if (Visibility != Visibility.Visible)
            {
                return;
            }

            FadeInStoryboard.Stop();
            FadeOutStoryboard.Begin();
        }

        private static DependencyProperty RegisterTextProperty(string name, string defaultValue) =>
            DependencyProperty.Register(name, typeof(string), typeof(CancellationAnimation), new PropertyMetadata(defaultValue, OnTextChanged));

        private static void OnTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is CancellationAnimation control)
            {
                control.ApplyText();
            }
        }

        private static void OnIsActiveChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is CancellationAnimation control && control.IsLoaded)
            {
                if ((bool)e.NewValue) control.Show(); else control.Hide();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            ApplyText();
            if (IsActive) Show();
        }

        private void ApplyText()
        {
            if (HeadingText == null) return;
            HeadingText.Text = Heading ?? string.Empty;
            MessageText.Text = Message ?? string.Empty;
            MetadataText.Text = $"{TaskId ?? string.Empty} · {ElapsedTime ?? string.Empty}";
        }

        private void OnFadeOutCompleted(object? sender, object e)
        {
            RootBorder.Opacity = 0;
            Visibility = Visibility.Collapsed;
        }
    }
}
