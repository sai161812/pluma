using System;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Dispatching;
using Microsoft.UI;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using WinRT.Interop;
using Windows.Graphics;
using Windows.Foundation;

namespace PLUMA.UI
{
    /// <summary>
    /// Temporary preview host for Surfaces 11–14. Positions a compact overlay
    /// in the bottom-right work area. Capture starts only after explicit consent.
    /// </summary>
    public sealed partial class VoiceOverlayPreviewWindow : Window
    {
        private const int ContentWidth = 460;
        private const int ContentHeight = 276;
        private MicrophoneSpectrumSource? _microphone;
        private readonly DispatcherQueueTimer _audioTimer;
        private ContentDialog? _prompt;
        private bool _closed;
        private bool _prompted;
        private AppWindow? _appWindow;
        private bool _correctingClientSize;

        public VoiceOverlayPreviewWindow()
        {
            InitializeComponent();

            ExtendsContentIntoTitleBar = true;
            SetTitleBar(RootGrid);

            _audioTimer = DispatcherQueue.CreateTimer();
            _audioTimer.Interval = TimeSpan.FromMilliseconds(16);
            _audioTimer.Tick += OnAudioTick;
            RootGrid.Loaded += OnPreviewLoaded;
            Overlay.VoiceState = VoiceOverlayState.ListeningSilence;
            Overlay.SetPreviewStatus("Preview");
            Overlay.FinalTranscript = "Microphone preview. No transcription or command execution.";

            Activated += OnActivated;
            Closed += OnClosed;
        }

        private void RootGrid_SizeChanged(object sender, SizeChangedEventArgs e)
        {
            RootGrid.Clip = new RectangleGeometry
            {
                Rect = new Rect(0, 0, RootGrid.ActualWidth, RootGrid.ActualHeight)
            };

            EnsureClientSize();
        }

        private void OnActivated(object sender, WindowActivatedEventArgs args)
        {
            if (_appWindow != null)
            {
                return;
            }

            ConfigurePlacement();

        }

        private async void OnPreviewLoaded(object sender, RoutedEventArgs e)
        {
            if (_prompted || _closed) return;
            _prompted = true;
            try
            {
                _prompt = new ContentDialog
                {
                    XamlRoot = RootGrid.XamlRoot,
                    Title = "Test microphone",
                    Content = "Use your microphone for this preview? Audio stays in memory. Close the preview to stop.",
                    PrimaryButtonText = "Start",
                    CloseButtonText = "Cancel",
                    DefaultButton = ContentDialogButton.Close
                };
                var result = await _prompt.ShowAsync();
                _prompt = null;
                if (_closed) return;
                if (result != ContentDialogResult.Primary)
                {
                    Overlay.SetPreviewStatus("Stopped");
                    Overlay.IsAnimating = false;
                    return;
                }
                _microphone = new MicrophoneSpectrumSource();
                _microphone.Start();
                Overlay.SetPreviewStatus("Listening");
                _audioTimer.Start();
            }
            catch (Exception)
            {
                if (!_closed) ShowMicrophoneError();
                _microphone?.Dispose();
                _microphone = null;
            }
        }

        private void OnAudioTick(DispatcherQueueTimer sender, object args)
        {
            if (_closed || _microphone == null) return;
            if (_microphone.Error != null)
            {
                ShowMicrophoneError();
                _microphone.Dispose();
                _microphone = null;
                return;
            }
            var frame = _microphone.TakeLatest();
            if (frame != null) Overlay.SetAudioSpectrum(frame);
        }

        private void ShowMicrophoneError()
        {
            _audioTimer.Stop();
            Overlay.IsAnimating = false;
            Overlay.SetPreviewStatus("Unavailable");
            Overlay.FinalTranscript = "Check microphone access and the Windows input device, then reopen this preview.";
        }

        private void OnClosed(object sender, WindowEventArgs args)
        {
            _closed = true;
            _prompt?.Hide();
            _audioTimer.Stop();
            _audioTimer.Tick -= OnAudioTick;
            RootGrid.Loaded -= OnPreviewLoaded;
            Overlay.IsAnimating = false;
            _microphone?.Dispose();
            _microphone = null;
        }

        private void ConfigurePlacement()
        {
            nint hwnd = WindowNative.GetWindowHandle(this);
            WindowId windowId = Win32Interop.GetWindowIdFromWindow(hwnd);
            _appWindow = AppWindow.GetFromWindowId(windowId);

            if (_appWindow.Presenter is OverlappedPresenter presenter)
            {
                presenter.IsAlwaysOnTop = true;
                presenter.IsResizable = false;
                presenter.IsMaximizable = false;
                presenter.IsMinimizable = false;
            }

            DisplayArea displayArea = DisplayArea.GetFromWindowId(windowId, DisplayAreaFallback.Primary);
            RectInt32 workArea = displayArea.WorkArea;

            const int margin = 20;

            var bounds = new RectInt32(
                workArea.X + workArea.Width - ContentWidth - margin,
                workArea.Y + workArea.Height - ContentHeight - margin,
                ContentWidth,
                ContentHeight);

            _appWindow.MoveAndResize(bounds);
            EnsureClientSize();
        }

        private void EnsureClientSize()
        {
            if (_appWindow == null || _correctingClientSize || RootGrid.ActualWidth <= 0 || RootGrid.ActualHeight <= 0)
            {
                return;
            }

            int actualWidth = (int)Math.Round(RootGrid.ActualWidth);
            int actualHeight = (int)Math.Round(RootGrid.ActualHeight);
            int widthDelta = ContentWidth - actualWidth;
            int heightDelta = ContentHeight - actualHeight;

            if (widthDelta == 0 && heightDelta == 0)
            {
                return;
            }

            _correctingClientSize = true;
            SizeInt32 currentSize = _appWindow.Size;
            _appWindow.Resize(new SizeInt32(
                Math.Max(1, currentSize.Width + widthDelta),
                Math.Max(1, currentSize.Height + heightDelta)));
            _correctingClientSize = false;
        }
    }
}
