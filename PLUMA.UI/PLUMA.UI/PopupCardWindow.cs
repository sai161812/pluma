using System;
using System.ComponentModel;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.Graphics;
using WinRT.Interop;

namespace PLUMA.UI
{
    /// <summary>A card-sized PLUMA-owned window; no invisible desktop-sized input surface.</summary>
    internal sealed class PopupCardWindow : Window
    {
        internal Grid Root { get; }
        internal nint Handle { get; }
        internal new PopupRect Bounds { get; private set; }
        internal double Alpha { get; private set; }
        internal bool WasShown { get; private set; }
        internal bool IsClosed { get; private set; }
        internal bool IsLayoutReady
        {
            get
            {
                if (!Root.IsLoaded || _content is not { IsLoaded: true } || Root.XamlRoot is not { } xamlRoot || Root.ActualWidth <= 0 || Root.ActualHeight <= 0) return false;
                if (!PopupDesktopPlacement.Native.GetClientRect(Handle, out var client)) throw new Win32Exception("Could not verify popup client layout.");
                return Math.Abs(Root.ActualWidth*xamlRoot.RasterizationScale-(client.Right-client.Left)) <= 1 &&
                    Math.Abs(Root.ActualHeight*xamlRoot.RasterizationScale-(client.Bottom-client.Top)) <= 1;
            }
        }
        internal FrameworkElement? HostedContent => _content;
        internal (double Width, double Height) ChromePixels
        {
            get
            {
                PopupRect outer = ReadBounds();
                if (!PopupDesktopPlacement.Native.GetClientRect(Handle, out var client)) throw new Win32Exception("Could not verify popup client bounds.");
                return (Math.Max(0,outer.Width-(client.Right-client.Left)),Math.Max(0,outer.Height-(client.Bottom-client.Top)));
            }
        }
        private readonly ScrollViewer _viewport;
        private readonly Action _changed;
        private readonly Action<bool> _reading;
        private FrameworkElement? _content;
        private XamlRoot? _xamlRoot;
        private bool _pointer, _focus, _activated;

        internal PopupCardWindow(Action changed, Action<bool> reading)
        {
            Title = "PLUMA";
            _changed = changed; _reading = reading;
            Root = (Grid)Microsoft.UI.Xaml.Markup.XamlReader.Load(
                "<Grid xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' RequestedTheme='Dark' Background='{ThemeResource ApplicationPageBackgroundThemeBrush}'/>");
            _viewport = new ScrollViewer { HorizontalScrollMode = ScrollMode.Disabled,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                VerticalScrollMode = ScrollMode.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalContentAlignment = HorizontalAlignment.Stretch, ZoomMode = ZoomMode.Disabled };
            _viewport.VerticalContentAlignment = VerticalAlignment.Stretch;
            Root.Children.Add(_viewport);
            Content = Root;
            try
            {
                Handle = WindowNative.GetWindowHandle(this);
                AppWindow.IsShownInSwitchers = false;
                if (AppWindow.Presenter is OverlappedPresenter presenter)
                {
                    presenter.SetBorderAndTitleBar(false, false);
                    presenter.IsAlwaysOnTop = true;
                    presenter.IsResizable = presenter.IsMaximizable = presenter.IsMinimizable = false;
                }
                nint style = PopupDesktopPlacement.Native.GetWindowLongPtr(Handle, -20);
                PopupDesktopPlacement.Native.SetWindowLongPtr(Handle, -20, style | 0x80000 | 0x80); // layered opacity + tool window
                int corner = 2;
                PopupDesktopPlacement.Native.DwmSetWindowAttribute(Handle, 33, ref corner, 4);
                SetAlpha(0);
            }
            catch { Close(); throw; }
            Root.PointerEntered += (_, _) => { _pointer = true; UpdateReading(); };
            Root.PointerExited += (_, _) => { _pointer = false; UpdateReading(); };
            Root.Loaded += (_, _) =>
            {
                if (_xamlRoot != null) _xamlRoot.Changed -= OnXamlRootChanged;
                _xamlRoot = Root.XamlRoot;
                if (_xamlRoot != null) _xamlRoot.Changed += OnXamlRootChanged;
                _changed();
            };
            Root.SizeChanged += OnContentSizeChanged;
            Activated += (_, args) =>
            {
                _activated = args.WindowActivationState != WindowActivationState.Deactivated;
                _focus = _activated && Root.XamlRoot != null && FocusManager.GetFocusedElement(Root.XamlRoot) != null;
                UpdateReading();
            };
            Root.GotFocus += (_, _) => { _focus = _activated; UpdateReading(); };
            Root.LostFocus += (_, _) =>
            {
                Root.DispatcherQueue.TryEnqueue(() =>
                {
                    if (IsClosed) return;
                    _focus = _activated && Root.XamlRoot != null && FocusManager.GetFocusedElement(Root.XamlRoot) != null;
                    UpdateReading();
                });
            };
            Closed += (_, _) =>
            {
                IsClosed = true;
                if (_content != null) _content.SizeChanged -= OnContentSizeChanged;
                Root.SizeChanged -= OnContentSizeChanged;
                if (_xamlRoot != null) _xamlRoot.Changed -= OnXamlRootChanged;
                _xamlRoot = null;
            };
        }

        private void UpdateReading() => _reading(_pointer || _focus);
        private void OnContentSizeChanged(object sender, SizeChangedEventArgs args) => _changed();
        private void OnXamlRootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => _changed();

        internal void SetContent(FrameworkElement content)
        {
            if (_content != null) _content.SizeChanged -= OnContentSizeChanged;
            _content = content;
            _viewport.Content = content;
            content.SizeChanged += OnContentSizeChanged;
        }

        internal void Place(PopupRect bounds)
        {
            if (IsClosed || !bounds.IsValid) return;
            var native = new RectInt32((int)Math.Round(bounds.X), (int)Math.Round(bounds.Y),
                Math.Max(1, (int)Math.Round(bounds.Width)), Math.Max(1, (int)Math.Round(bounds.Height)));
            if (Bounds != bounds)
            {
                AppWindow.MoveAndResize(native);
                Bounds = new(native.X, native.Y, native.Width, native.Height);
            }
        }

        internal void Reveal()
        {
            if (!WasShown && !IsClosed) { AppWindow.Show(false); WasShown = true; }
        }

        internal void SetAlpha(double alpha)
        {
            if (IsClosed) return;
            byte value = (byte)Math.Round(Math.Clamp(alpha, 0, 1) * 255);
            if (!PopupDesktopPlacement.Native.SetLayeredWindowAttributes(Handle, 0, value, 2))
                throw new Win32Exception("Could not set popup window opacity.");
            Alpha = value / 255.0;
        }

        internal PopupRect ReadBounds()
        {
            if (!PopupDesktopPlacement.Native.GetWindowRect(Handle, out var r)) throw new Win32Exception("Could not verify popup bounds.");
            return new(r.Left, r.Top, r.Right-r.Left, r.Bottom-r.Top);
        }

        internal byte ReadAlpha()
        {
            if (!PopupDesktopPlacement.Native.GetLayeredWindowAttributes(Handle, out _, out byte alpha, out _))
                throw new Win32Exception("Could not verify popup opacity.");
            return alpha;
        }
    }
}
