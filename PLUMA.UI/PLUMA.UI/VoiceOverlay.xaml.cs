using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System;

namespace PLUMA.UI
{
    /// <summary>
    /// Reusable PLUMA voice overlay.
    /// Surfaces 11–14 are represented as visual states.
    /// </summary>
    public sealed partial class VoiceOverlay : UserControl
    {
        public static readonly DependencyProperty VoiceStateProperty =
            DependencyProperty.Register(
                nameof(VoiceState),
                typeof(VoiceOverlayState),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    VoiceOverlayState.Hidden,
                    OnVoiceStateChanged));

        public static readonly DependencyProperty IsListeningProperty =
            DependencyProperty.Register(
                nameof(IsListening),
                typeof(bool),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    false,
                    OnIsListeningChanged));

        public static readonly DependencyProperty AmplitudeProperty =
            DependencyProperty.Register(
                nameof(Amplitude),
                typeof(double),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    0.0,
                    OnAmplitudeChanged));

        public static readonly DependencyProperty IsAnimatingProperty =
            DependencyProperty.Register(
                nameof(IsAnimating),
                typeof(bool),
                typeof(VoiceOverlay),
                new PropertyMetadata(true, OnIsAnimatingChanged));

        public static readonly DependencyProperty FinalTranscriptProperty =
            DependencyProperty.Register(
                nameof(FinalTranscript),
                typeof(string),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    string.Empty,
                    OnTranscriptChanged));

        public static readonly DependencyProperty PartialTranscriptProperty =
            DependencyProperty.Register(
                nameof(PartialTranscript),
                typeof(string),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    string.Empty,
                    OnTranscriptChanged));

        public static readonly DependencyProperty SilenceProgressProperty =
            DependencyProperty.Register(
                nameof(SilenceProgress),
                typeof(double),
                typeof(VoiceOverlay),
                new PropertyMetadata(
                    0.0,
                    OnSilenceProgressChanged));

        private bool _suppressListeningCallback;

        public VoiceOverlay()
        {
            InitializeComponent();
            Loaded += OnLoaded;
        }

        public bool IsAnimating
        {
            get => (bool)GetValue(IsAnimatingProperty);
            set => SetValue(IsAnimatingProperty, value);
        }

        public VoiceOverlayState VoiceState
        {
            get => (VoiceOverlayState)GetValue(VoiceStateProperty);
            set => SetValue(VoiceStateProperty, value);
        }

        private static void OnIsAnimatingChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay && overlay.ListeningRing != null)
            {
                overlay.ListeningRing.IsAnimating = (bool)e.NewValue;
            }
        }

        public bool IsListening
        {
            get => (bool)GetValue(IsListeningProperty);
            set => SetValue(IsListeningProperty, value);
        }

        public double Amplitude
        {
            get => (double)GetValue(AmplitudeProperty);
            set => SetValue(AmplitudeProperty, value);
        }

        public string FinalTranscript
        {
            get => (string)GetValue(FinalTranscriptProperty);
            set => SetValue(FinalTranscriptProperty, value);
        }

        public string PartialTranscript
        {
            get => (string)GetValue(PartialTranscriptProperty);
            set => SetValue(PartialTranscriptProperty, value);
        }

        public double SilenceProgress
        {
            get => (double)GetValue(SilenceProgressProperty);
            set => SetValue(SilenceProgressProperty, value);
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            ApplyVoiceState(useTransitions: false);
            ApplyTranscript();
            ApplyAmplitude();
            ApplySilenceProgress();
        }

        private static void OnVoiceStateChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay)
            {
                overlay.SyncListeningFromState();
                overlay.ApplyVoiceState(useTransitions: true);
            }
        }

        private static void OnIsListeningChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay)
            {
                overlay.ApplyListeningHint();
            }
        }

        private static void OnAmplitudeChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay)
            {
                overlay.ApplyAmplitude();
            }
        }

        private static void OnTranscriptChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay)
            {
                overlay.ApplyTranscript();
            }
        }

        private static void OnSilenceProgressChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceOverlay overlay)
            {
                overlay.ApplySilenceProgress();
            }
        }

        private void SyncListeningFromState()
        {
            bool listening =
                VoiceState is VoiceOverlayState.ListeningSilence
                or VoiceOverlayState.ListeningSpeech
                or VoiceOverlayState.SilenceTimeout;

            _suppressListeningCallback = true;
            IsListening = listening;
            _suppressListeningCallback = false;
        }

        private void ApplyListeningHint()
        {
            if (_suppressListeningCallback)
            {
                return;
            }

            if (IsListening &&
                VoiceState == VoiceOverlayState.Hidden)
            {
                VoiceState = VoiceOverlayState.ListeningSilence;
            }
            else if (!IsListening &&
                     VoiceState is
                         VoiceOverlayState.ListeningSilence
                         or VoiceOverlayState.ListeningSpeech
                         or VoiceOverlayState.SilenceTimeout)
            {
                VoiceState = VoiceOverlayState.Hidden;
            }
        }

        private void ApplyVoiceState(bool useTransitions)
        {
            string stateName = VoiceState switch
            {
                VoiceOverlayState.ListeningSilence => "ListeningSilence",
                VoiceOverlayState.ListeningSpeech => "ListeningSpeech",
                VoiceOverlayState.SilenceTimeout => "SilenceTimeout",
                VoiceOverlayState.Committed => "Committed",
                _ => "Hidden"
            };

            VisualStateManager.GoToState(
                this,
                stateName,
                useTransitions);

            if (ListeningRing != null)
            {
                IsAnimating = VoiceState != VoiceOverlayState.Hidden;
            }

            Visibility =
                VoiceState == VoiceOverlayState.Hidden
                    ? Visibility.Collapsed
                    : Visibility.Visible;
        }

        private void ApplyAmplitude()
        {
            if (ListeningRing != null)
            {
                ListeningRing.Amplitude =
                    Math.Clamp(Amplitude, 0.0, 1.0);
            }
        }

        private void ApplySilenceProgress()
        {
            if (TimeoutBar != null)
            {
                TimeoutBar.Progress =
                    Math.Clamp(SilenceProgress, 0.0, 1.0);
            }
        }

        private void ApplyTranscript()
        {
            if (LiveTranscriptHost == null)
            {
                return;
            }

            LiveTranscriptHost.FinalTranscript = FinalTranscript;
            LiveTranscriptHost.PartialTranscript = PartialTranscript;
        }
    }
}