using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class WorkerTerminationFlash : UserControl, IHostedPopup
    {
        public bool IsHosted { get; set; }
        public event EventHandler? DismissRequested;
        public static readonly DependencyProperty HeadingProperty = RegisterTextProperty(nameof(Heading), "Worker terminated");
        public static readonly DependencyProperty MessageProperty = RegisterTextProperty(nameof(Message), "The isolated tool worker was closed safely");
        public static readonly DependencyProperty WorkerPidProperty = RegisterTextProperty(nameof(WorkerPid), "18432");
        public static readonly DependencyProperty ElapsedTimeProperty = RegisterTextProperty(nameof(ElapsedTime), "00:12");
        public static readonly DependencyProperty IsOpenProperty =
            DependencyProperty.Register(nameof(IsOpen), typeof(bool), typeof(WorkerTerminationFlash), new PropertyMetadata(false, OnIsOpenChanged));

        public WorkerTerminationFlash()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        public string Heading { get => (string)GetValue(HeadingProperty); set => SetValue(HeadingProperty, value); }
        public string Message { get => (string)GetValue(MessageProperty); set => SetValue(MessageProperty, value); }
        public string WorkerPid { get => (string)GetValue(WorkerPidProperty); set => SetValue(WorkerPidProperty, value); }
        public string ElapsedTime { get => (string)GetValue(ElapsedTimeProperty); set => SetValue(ElapsedTimeProperty, value); }
        public bool IsOpen { get => (bool)GetValue(IsOpenProperty); set => SetValue(IsOpenProperty, value); }

        public void Show()
        {
            IsOpen = true;
            FadeOutStoryboard.Stop();
            if (IsHosted) { FadeInStoryboard.Stop(); RootBorder.Opacity = 1; Visibility = Visibility.Visible; return; }
            Visibility = Visibility.Visible;
            RootBorder.Opacity = 0;
            FadeInStoryboard.Begin();
        }

        public void Hide()
        {
            if (IsHosted) { DismissRequested?.Invoke(this, EventArgs.Empty); return; }
            IsOpen = false;
            if (Visibility != Visibility.Visible) return;
            FadeInStoryboard.Stop();
            FadeOutStoryboard.Begin();
        }

        private static DependencyProperty RegisterTextProperty(string name, string defaultValue) =>
            DependencyProperty.Register(name, typeof(string), typeof(WorkerTerminationFlash), new PropertyMetadata(defaultValue, OnTextChanged));

        private static void OnTextChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is WorkerTerminationFlash control) control.ApplyText();
        }

        private static void OnIsOpenChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is WorkerTerminationFlash control && control.IsLoaded)
            {
                if ((bool)e.NewValue) control.Show(); else control.Hide();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            ApplyText();
            if (IsOpen) Show();
        }

        private void ApplyText()
        {
            if (HeadingText == null) return;
            HeadingText.Text = PopupText.Message(Heading);
            MessageText.Text = PopupText.Message(Message);
            MetadataText.Text = PopupText.Message($"Worker {WorkerPid} · Elapsed {ElapsedTime}");
        }

        private void OnFadeOutCompleted(object? sender, object e)
        {
            RootBorder.Opacity = 0;
            Visibility = Visibility.Collapsed;
        }
    }
}
