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
    private bool _compositionValid=true;
    private readonly PopupDesktopPlacement.Native.SubclassProc _messages;

    internal PerceptionFeedbackWindow(Window owner)
    {
        _messages=OnMessage;
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
            // Presenter flags alone leave a native resize frame on this SDK.
            nint frame=PopupDesktopPlacement.Native.GetWindowLongPtr(Handle,-16);
            PopupDesktopPlacement.Native.SetWindowLongPtr(Handle,-16,frame & ~(nint)0x00CF0000);
            if(!PopupDesktopPlacement.Native.SetWindowSubclass(Handle,_messages,0x50464C41,0))
                throw new InvalidOperationException("Feedback frame observation could not be installed.");
            if(!SetWindowPos(Handle,0,0,0,0,0,0x37))throw new InvalidOperationException("Feedback frame could not be removed.");
            ConfigureComposition();
            nint style = PopupDesktopPlacement.Native.GetWindowLongPtr(Handle, -20);
            PopupDesktopPlacement.Native.SetWindowLongPtr(Handle, -20, style | 0x80000 | 0x20 | 0x80 | 0x08000000);
            PopupDesktopPlacement.Native.SetWindowLongPtr(Handle, -8, WinRT.Interop.WindowNative.GetWindowHandle(owner));
            // This HWND presents facts only. Disable native input as well as
            // XAML hit testing: WinUI's input-site child must not intercept the
            // target's pointer just because the top-level style is transparent.
            EnableWindow(Handle,false);
            if(IsWindowEnabled(Handle))throw new InvalidOperationException("Feedback input could not be disabled.");
            Alpha(0);
            Closed += (_, _) => { _closed = true; Marker.HideMatch(); SystemBackdrop = null;
                PopupDesktopPlacement.Native.RemoveWindowSubclass(Handle,_messages,0x50464C41); };
        }
        catch { Close(); throw; }
    }

    internal void Place(PerceptionPlacement pixels) => AppWindow.MoveAndResize(new RectInt32(
        checked((int)pixels.DesktopX), checked((int)pixels.DesktopY), checked((int)pixels.Width), checked((int)pixels.Height)));
    internal void ShowHidden() => AppWindow.Show(false);
    internal bool LayoutReady => !_closed && _compositionValid && Root.IsLoaded && Root.XamlRoot is { } root &&
        Math.Abs(root.RasterizationScale-Scale)<.000001 &&
        PopupDesktopPlacement.Native.GetClientRect(Handle, out var rect) &&
        Math.Abs(Root.ActualWidth*Scale-(rect.Right-rect.Left))<=1 &&
        Math.Abs(Root.ActualHeight*Scale-(rect.Bottom-rect.Top))<=1;
    internal bool Matches(PerceptionPlacement pixels) => !_closed && _compositionValid && PopupDesktopPlacement.Native.GetWindowRect(Handle,out var rect) &&
        rect.Left==pixels.DesktopX && rect.Top==pixels.DesktopY && rect.Right-rect.Left==pixels.Width && rect.Bottom-rect.Top==pixels.Height &&
        PopupDesktopPlacement.Native.GetClientRect(Handle,out var client) && client.Right-client.Left==pixels.Width && client.Bottom-client.Top==pixels.Height;
    internal void Render(CoreRequestProtocol.PerceptionObservation observation, PerceptionPlacement local, bool flash)
    {
        Marker.Width = local.Width; Marker.Height = local.Height;
        if (observation.Match is not null)
            Marker.ShowMatch("Matched visible text", observation.Match.Confidence,
                new Rect(local.MatchX,local.MatchY,local.MatchWidth,local.MatchHeight),
                new Point(local.DesktopX+local.MatchX*Scale,local.DesktopY+local.MatchY*Scale),DateTimeOffset.Parse(observation.ExpiresUtc));
        if (flash)
        {
            // Arrange the previously collapsed control before starting its
            // unchanged 220ms storyboard, rather than spending it at zero size.
            Flash.Visibility=Visibility.Visible;Flash.UpdateLayout();
            if(Math.Abs(Flash.ActualWidth-Root.ActualWidth)>.5||Math.Abs(Flash.ActualHeight-Root.ActualHeight)>.5)
                throw new InvalidOperationException("Capture flash layout is not ready.");
            Flash.Play();
        }
        Alpha(255);
    }
    private void Alpha(byte value)
    {
        if (!PopupDesktopPlacement.Native.SetLayeredWindowAttributes(Handle,0,value,2))
            throw new System.ComponentModel.Win32Exception("Could not set feedback visibility.");
    }
    [DllImport("user32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool EnableWindow(nint hwnd,bool enabled);
    [DllImport("user32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool IsWindowEnabled(nint hwnd);

    private void ConfigureComposition()
    {
        // Enable client alpha over an empty blur region. No desktop pixels are
        // copied into the host. A transparent brush alone leaves a theme matte.
        nint region=CreateRectRgn(-2,-2,-1,-1);
        if(region==0)throw new InvalidOperationException("Feedback alpha region unavailable.");
        try
        {
            var margins=new Margins();var blur=new BlurBehind{Flags=3,Enabled=true,Region=region};
            if(DwmExtendFrameIntoClientArea(Handle,ref margins)<0||DwmEnableBlurBehindWindow(Handle,ref blur)<0)
                throw new InvalidOperationException("Feedback client alpha is unavailable.");
        }
        finally{DeleteObject(region);}
    }
    private nint OnMessage(nint hwnd,uint message,nuint wParam,nint lParam,nuint id,nuint data)
    {
        if(message==0x83 && wParam!=0)return 0; // Entire HWND is the captured client ROI.
        if(message==0x14 && PopupDesktopPlacement.Native.GetClientRect(hwnd,out var rect))
            return FillRect((nint)wParam,ref rect,GetStockObject(4))!=0 ? 1 : 0; // Borrowed BLACK_BRUSH, alpha zero.
        if(message==0x31E)
        {
            try{ConfigureComposition();}
            catch{_compositionValid=false;PopupDesktopPlacement.Native.SetLayeredWindowAttributes(hwnd,0,0,2);}
        }
        return PopupDesktopPlacement.Native.DefSubclassProc(hwnd,message,wParam,lParam);
    }
    [StructLayout(LayoutKind.Sequential)] private struct Margins{public int Left,Right,Top,Bottom;}
    [StructLayout(LayoutKind.Sequential)] private struct BlurBehind{public uint Flags;[MarshalAs(UnmanagedType.Bool)]public bool Enabled;public nint Region;[MarshalAs(UnmanagedType.Bool)]public bool Transition;}
    [DllImport("dwmapi.dll")] private static extern int DwmExtendFrameIntoClientArea(nint hwnd,ref Margins margins);
    [DllImport("dwmapi.dll")] private static extern int DwmEnableBlurBehindWindow(nint hwnd,ref BlurBehind blur);
    [DllImport("gdi32.dll")] private static extern nint CreateRectRgn(int left,int top,int right,int bottom);
    [DllImport("gdi32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool DeleteObject(nint value);
    [DllImport("gdi32.dll")] private static extern nint GetStockObject(int index);
    [DllImport("user32.dll")] private static extern int FillRect(nint dc,ref PopupDesktopPlacement.Native.Rect rect,nint brush);
    [DllImport("user32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool SetWindowPos(nint hwnd,nint after,int x,int y,int width,int height,uint flags);

    // SystemBackdrop removes the default opaque HWND background. Only the
    // unchanged controls draw pixels. Composition resources follow the target.
    private sealed class ClearBackdrop : SystemBackdrop
    {
        private Windows.UI.Composition.Compositor? _compositor;
        private Windows.UI.Composition.CompositionColorBrush? _brush;
        protected override void OnTargetConnected(ICompositionSupportsSystemBackdrop target, XamlRoot root)
        {
            _compositor = new(); _brush = _compositor.CreateColorBrush(Windows.UI.Color.FromArgb(0,0,0,0));
            target.SystemBackdrop = _brush;
            base.OnTargetConnected(target,root);
        }
        protected override void OnTargetDisconnected(ICompositionSupportsSystemBackdrop target)
        {
            target.SystemBackdrop = null; _brush?.Dispose(); _brush=null; _compositor?.Dispose(); _compositor=null;
            base.OnTargetDisconnected(target);
        }
    }
}
