using System;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    /// <summary>
    /// Surface 15 — brief visual acknowledgement that PLUMA captured the screen.
    /// This control renders feedback only; it performs no capture work.
    /// </summary>
    public sealed partial class ScreenCaptureFlash : UserControl
    {
        private bool _playWhenLoaded;

        public ScreenCaptureFlash()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += OnUnloaded;
        }

        /// <summary>
        /// Raised after the flash has faded out and the control has collapsed.
        /// </summary>
        public event EventHandler? FlashCompleted;

        /// <summary>
        /// Restarts and plays the 220 ms capture acknowledgement.
        /// Safe to call from a non-UI thread.
        /// </summary>
        public void Play()
        {
            if (!DispatcherQueue.HasThreadAccess)
            {
                DispatcherQueue.TryEnqueue(
                    DispatcherQueuePriority.High,
                    Play);
                return;
            }

            if (!IsLoaded)
            {
                _playWhenLoaded = true;
                return;
            }

            _playWhenLoaded = false;
            FlashStoryboard.Stop();
            FlashLayer.Opacity = 0;
            Visibility = Visibility.Visible;
            FlashStoryboard.Begin();
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            if (_playWhenLoaded)
            {
                Play();
            }
        }

        private void OnUnloaded(object sender, RoutedEventArgs e)
        {
            FlashStoryboard.Stop();
            FlashLayer.Opacity = 0;
            Visibility = Visibility.Collapsed;
        }

        private void FlashStoryboard_Completed(object? sender, object e)
        {
            FlashLayer.Opacity = 0;
            Visibility = Visibility.Collapsed;
            FlashCompleted?.Invoke(this, EventArgs.Empty);
        }
    }
}
