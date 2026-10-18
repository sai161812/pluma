using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace PLUMA.UI
{
    /// <summary>Display only. The host supplies fresh host-local DIPs and desktop metadata.</summary>
    public sealed partial class OcrMatchIndicator : UserControl
    {
        private readonly DispatcherTimer _expiryTimer = new();
        private Rect _bounds;
        private DateTimeOffset _expiresAt;

        public OcrMatchIndicator()
        {
            InitializeComponent();
            _expiryTimer.Tick += (_, _) => HideMatch();
            SizeChanged += (_, _) => ApplyLayout();
            Loaded += (_, _) => ApplyLayout();
            Unloaded += (_, _) => HideMatch();
        }

        public bool IsMatchVisible => Visibility == Visibility.Visible;

        public void ShowMatch(string sanitizedText, double confidence, Rect hostBounds,
                              Point desktopPosition, DateTimeOffset snapshotExpiresAt)
        {
            HideMatch();
            DateTimeOffset now = DateTimeOffset.UtcNow;
            TimeSpan remaining = snapshotExpiresAt - now;
            if (string.IsNullOrWhiteSpace(sanitizedText) || !double.IsFinite(confidence) || confidence < 0 || confidence > 1 ||
                !Finite(hostBounds.X, hostBounds.Y, hostBounds.Width, hostBounds.Height, desktopPosition.X, desktopPosition.Y) ||
                hostBounds.X < 0 || hostBounds.Y < 0 || hostBounds.Width <= 0 || hostBounds.Height <= 0 || remaining <= TimeSpan.Zero)
                return;

            // Never extend a snapshot's lifetime. The host must also hide on target/window changes.
            _expiresAt = remaining > TimeSpan.FromSeconds(3) ? now.AddSeconds(3) : snapshotExpiresAt;
            remaining = _expiresAt - now;
            _bounds = hostBounds;
            MatchText.Text = PopupText.Message(sanitizedText);
            MetadataText.Text = $"Confidence {confidence:0.00} · Desktop ({desktopPosition.X:0}, {desktopPosition.Y:0})";
            Visibility = Visibility.Visible;
            _expiryTimer.Interval = remaining;
            _expiryTimer.Start();
            ApplyLayout();
        }

        public void HideMatch()
        {
            _expiryTimer.Stop();
            Visibility = Visibility.Collapsed;
            if (MatchText == null) return;
            MatchText.Text = string.Empty;
            MetadataText.Text = string.Empty;
            _bounds = default;
        }

        private void ApplyLayout()
        {
            if (!IsMatchVisible) return;
            if (_expiresAt <= DateTimeOffset.UtcNow) { HideMatch(); return; }
            if (ActualWidth <= 0 || ActualHeight <= 0) return;
            if (_bounds.Right > ActualWidth || _bounds.Bottom > ActualHeight) { HideMatch(); return; }
            OverlayCanvas.Clip = new RectangleGeometry { Rect = new Rect(0, 0, ActualWidth, ActualHeight) };
            TargetOutline.Width = _bounds.Width;
            TargetOutline.Height = _bounds.Height;
            Canvas.SetLeft(TargetOutline, _bounds.X);
            Canvas.SetTop(TargetOutline, _bounds.Y);
            MatchCallout.Width = Math.Min(320, ActualWidth);
            MatchCallout.Measure(new Size(MatchCallout.Width, double.PositiveInfinity));
            double top = _bounds.Bottom + 8;
            if (top + MatchCallout.DesiredSize.Height > ActualHeight)
                top = Math.Max(0, _bounds.Top - MatchCallout.DesiredSize.Height - 8);
            Canvas.SetLeft(MatchCallout, Math.Max(0, Math.Min(_bounds.X, ActualWidth - MatchCallout.Width)));
            Canvas.SetTop(MatchCallout, top);
        }

        private static bool Finite(params double[] values) => Array.TrueForAll(values, double.IsFinite);
    }
}
