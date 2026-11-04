using System;
using System.Runtime.InteropServices;
using Microsoft.UI.Composition;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;
using Windows.Graphics;

namespace PLUMA.UI;

/// <summary>One owned, transparent, nonactivating window, exactly the captured ROI.</summary>
internal sealed class PerceptionFeedbackWindow : Window
{
    internal nint Handle { get; }
    internal Grid Root { get; } = new() { RequestedTheme = ElementTheme.Dark, IsHitTestVisible = false };
    internal ScreenCaptureFlash Flash { get; } = new();
    internal OcrMatchIndicator Marker { get; } = new();
    internal double Scale => NativePerceptionTarget.WindowScale(Handle);
    private bool _closed;

    internal PerceptionFeedbackWindow(Window owner)
    {
        Root.Children.Add(Flash); Root.Children.Add(Marker); Content = Root;
        try
        {
            Handle = WinRT.Interop.WindowNative.GetWindowHandle(this);
            SystemBackdrop = new ClearBackdrop();
            AppWindow.IsShownInSwitchers = false;
            var presenter = (OverlappedPresenter)AppWindow.Presenter;
            presenter.SetBorderAndTitleBar(false, false);
            presenter.IsAlwaysOnTop = true;
            presenter.IsResizable = presenter.IsMaximizable = presenter.IsMinimizable = false;
            int noNonClientRendering=1;
            if(PopupDesktopPlacement.Native.DwmSetWindowAttribute(Handle,2,ref noNonClientRendering,4)<0)
                throw new InvalidOperationException("Target feedback non-client rendering could not be disabled.");
            nint style = PopupDesktopPlacement.Native.GetWindowLongPtr(Handle, -20);
            PopupDesktopPlacement.Native.SetWindowLongPtr(Handle, -20, style | 0x80000 | 0x20 | 0x80 | 0x08000000);
            PopupDesktopPlacement.Native.SetWindowLongPtr(Handle, -8, WinRT.Interop.WindowNative.GetWindowHandle(owner));
            Alpha(0);
            Closed += (_, _) => { _closed = true; Marker.HideMatch(); SystemBackdrop = null; };
        }
        catch { Close(); throw; }
    }

    internal void Place(PerceptionPlacement pixels) => AppWindow.MoveAndResize(new RectInt32(
        checked((int)pixels.DesktopX), checked((int)pixels.DesktopY), checked((int)pixels.Width), checked((int)pixels.Height)));
    internal void ShowHidden() => AppWindow.Show(false);
    internal bool LayoutReady => !_closed && Root.IsLoaded && Root.XamlRoot is { } root &&
        Math.Abs(root.RasterizationScale-Scale)<.000001 &&
        PopupDesktopPlacement.Native.GetClientRect(Handle, out var rect) &&
        Math.Abs(Root.ActualWidth*Scale-(rect.Right-rect.Left))<=1 &&
        Math.Abs(Root.ActualHeight*Scale-(rect.Bottom-rect.Top))<=1;
    internal bool Matches(PerceptionPlacement pixels) => !_closed && PopupDesktopPlacement.Native.GetWindowRect(Handle,out var rect) &&
        rect.Left==pixels.DesktopX && rect.Top==pixels.DesktopY && rect.Right-rect.Left==pixels.Width && rect.Bottom-rect.Top==pixels.Height;
    internal void Render(CoreRequestProtocol.PerceptionObservation observation, PerceptionPlacement local, bool flash)
    {
        Marker.Width = local.Width; Marker.Height = local.Height;
        if (observation.Match is not null)
            Marker.ShowMatch("Matched visible text", observation.Match.Confidence,
                new Rect(local.MatchX,local.MatchY,local.MatchWidth,local.MatchHeight),
                new Point(local.DesktopX+local.MatchX*Scale,local.DesktopY+local.MatchY*Scale),DateTimeOffset.Parse(observation.ExpiresUtc));
        if (flash) Flash.Play();
        Alpha(255);
    }
    private void Alpha(byte value)
    {
        if (!PopupDesktopPlacement.Native.SetLayeredWindowAttributes(Handle,0,value,2))
            throw new System.ComponentModel.Win32Exception("Could not set feedback visibility.");
    }

    // SystemBackdrop removes the default opaque HWND background. Only the
    // unchanged controls draw pixels. Composition resources follow the target.
    private sealed class ClearBackdrop : SystemBackdrop
    {
        private Windows.UI.Composition.Compositor? _compositor;
        private Windows.UI.Composition.CompositionColorBrush? _brush;
        protected override void OnTargetConnected(ICompositionSupportsSystemBackdrop target, XamlRoot root)
        {
            base.OnTargetConnected(target,root);
            _compositor = new(); _brush = _compositor.CreateColorBrush(Windows.UI.Color.FromArgb(0,0,0,0));
            target.SystemBackdrop = _brush;
        }
        protected override void OnTargetDisconnected(ICompositionSupportsSystemBackdrop target)
        {
            target.SystemBackdrop = null; _brush?.Dispose(); _brush=null; _compositor?.Dispose(); _compositor=null;
            base.OnTargetDisconnected(target);
        }
    }
}
