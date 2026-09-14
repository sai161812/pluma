using System;
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
    /// in the bottom-right work area and drives VoiceOverlay with mock frames.
    /// </summary>
    public sealed partial class VoiceOverlayPreviewWindow : Window
    {
        private const int ContentWidth = 400;
        private const int ContentHeight = 270;
        private readonly VoiceOverlayPreviewGenerator _generator;
        private AppWindow? _appWindow;
        private bool _correctingClientSize;

        public VoiceOverlayPreviewWindow()
        {
            InitializeComponent();

            ExtendsContentIntoTitleBar = true;
            SetTitleBar(RootGrid);

            _generator = new VoiceOverlayPreviewGenerator(DispatcherQueue);
            _generator.FrameReady += OnFrameReady;

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
            _generator.Start();
        }

        private void OnClosed(object sender, WindowEventArgs args)
        {
            _generator.Stop();
            _generator.FrameReady -= OnFrameReady;
        }

        private void OnFrameReady(object? sender, VoiceOverlayPreviewFrame frame)
        {
            Overlay.VoiceState = frame.VoiceState;
            Overlay.Amplitude = frame.Amplitude;
            Overlay.FinalTranscript = frame.FinalTranscript;
            Overlay.PartialTranscript = frame.PartialTranscript;
            Overlay.SilenceProgress = frame.SilenceProgress;
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
