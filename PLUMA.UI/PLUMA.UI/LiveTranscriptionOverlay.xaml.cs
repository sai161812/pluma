using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class LiveTranscriptionOverlay : UserControl
    {
        public static readonly DependencyProperty FinalTranscriptProperty =
            DependencyProperty.Register(
                nameof(FinalTranscript),
                typeof(string),
                typeof(LiveTranscriptionOverlay),
                new PropertyMetadata(string.Empty, OnTranscriptChanged));

        public static readonly DependencyProperty PartialTranscriptProperty =
            DependencyProperty.Register(
                nameof(PartialTranscript),
                typeof(string),
                typeof(LiveTranscriptionOverlay),
                new PropertyMetadata(string.Empty, OnTranscriptChanged));

        public LiveTranscriptionOverlay()
        {
            InitializeComponent();
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

        private static void OnTranscriptChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is LiveTranscriptionOverlay overlay && overlay.LiveTranscript != null)
            {
                overlay.LiveTranscript.Text = overlay.GetTranscript();
            }
        }

        private string GetTranscript()
        {
            string finalText = (FinalTranscript ?? string.Empty).Trim();
            string partialText = (PartialTranscript ?? string.Empty).Trim();

            if (string.IsNullOrEmpty(finalText))
            {
                return partialText;
            }

            if (string.IsNullOrEmpty(partialText))
            {
                return finalText;
            }

            return $"{finalText} {partialText}";
        }
    }
}
