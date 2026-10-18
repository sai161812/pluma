using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using Microsoft.UI.Dispatching;

namespace PLUMA.UI
{
    public interface IPopupDesktopPlacement : IDisposable
    {
        event EventHandler? Changed;
        PopupDesktop Read(nint referenceWindow);
        void Watch(bool enabled);
    }

    /// <summary>Read-only shell/monitor adapter. The only modified windows belong to PopupCardWindow.</summary>
    internal sealed class PopupDesktopPlacement : IPopupDesktopPlacement
    {
        private readonly nint _owner;
        private readonly DispatcherQueue _dispatcher;
        private readonly Native.SubclassProc _subclass;
        private readonly Native.WinEventProc _winEvent;
        private readonly HashSet<nint> _bars = new();
        private readonly Dictionary<(nint, uint), double> _thickness = new();
        private readonly uint _taskbarCreated;
        private nint _monitor, _locationHook, _visibilityHook;
        private bool _disposed, _queued, _watching;
        public event EventHandler? Changed;
        internal int HookCount => (_locationHook == 0 ? 0 : 1) + (_visibilityHook == 0 ? 0 : 1);

        public PopupDesktopPlacement(nint owner, DispatcherQueue dispatcher)
        {
            _owner = owner; _dispatcher = dispatcher;
            _subclass = OnMessage; _winEvent = OnWinEvent;
            _taskbarCreated = Native.RegisterWindowMessage("TaskbarCreated");
            if (!Native.SetWindowSubclass(owner, _subclass, 0x504C554D, 0)) throw new Win32Exception("Could not observe popup display changes.");
        }

        public PopupDesktop Read(nint referenceWindow)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            var info = new Native.MonitorInfo { Size = (uint)Marshal.SizeOf<Native.MonitorInfo>() };
            if (_monitor == 0 || !Native.GetMonitorInfo(_monitor, ref info))
            {
                _monitor = Native.MonitorFromWindow(Native.IsWindow(referenceWindow) ? referenceWindow : _owner, 2);
                if (_monitor == 0 || !Native.GetMonitorInfo(_monitor, ref info)) throw new Win32Exception("Could not read the popup monitor.");
            }
            uint dpi = 0;
            if (Native.GetDpiForMonitor(_monitor, 0, out uint x, out _) == 0) dpi = x;
            if (dpi == 0) dpi = Native.GetDpiForWindow(_owner);
            if (dpi == 0) throw new Win32Exception("Could not read display scaling.");
            double scale = dpi / 96.0;
            var reservations = new List<PopupAppBar>();
            _bars.Clear();
            bool verified = true;
            for (uint edge = 0; edge < 4; edge++)
            {
                var data = new Native.AppBarData { Size = (uint)Marshal.SizeOf<Native.AppBarData>(), Edge = edge, Rect = info.Monitor };
                nint bar = (nint)Native.SHAppBarMessage(0xB, ref data);
                if (bar == 0) continue;
                _bars.Add(bar);
                double measured = 0;
                if (Native.GetWindowRect(bar, out Native.Rect rectangle))
                    measured = edge is 0 or 2 ? rectangle.Right - rectangle.Left : rectangle.Bottom - rectangle.Top;
                // Query the system taskbar's full bounds as an additional source, including while auto-hidden.
                var taskbar = new Native.AppBarData { Size = (uint)Marshal.SizeOf<Native.AppBarData>() };
                if (Native.SHAppBarMessage(5, ref taskbar) != 0 && taskbar.Edge == edge && Native.MonitorFromRect(ref taskbar.Rect, 0) == _monitor)
                    measured = Math.Max(measured, edge is 0 or 2 ? taskbar.Rect.Right - taskbar.Rect.Left : taskbar.Rect.Bottom - taskbar.Rect.Top);
                if (measured >= 20 * scale && measured <= 200 * scale)
                    _thickness[(_monitor, edge)] = Math.Max(_thickness.GetValueOrDefault((_monitor, edge)), measured);
                if (!_thickness.TryGetValue((_monitor, edge), out double known)) { verified = false; known = 64 * scale; }
                reservations.Add(new((PopupScreenEdge)edge, Math.Max(known, 64 * scale)));
            }
            return new(ToRect(info.Monitor), ToRect(info.Work), scale, reservations, verified);
        }

        public void Watch(bool enabled)
        {
            if (_disposed || enabled == _watching) return;
            _watching = enabled;
            if (enabled)
            {
                _locationHook = Native.SetWinEventHook(0x800B, 0x800B, 0, _winEvent, 0, 0, 2);
                _visibilityHook = Native.SetWinEventHook(0x8002, 0x8003, 0, _winEvent, 0, 0, 2);
                if (_locationHook == 0 || _visibilityHook == 0) { Watch(false); throw new Win32Exception("Could not observe taskbar geometry changes."); }
            }
            else
            {
                if (_locationHook != 0) Native.UnhookWinEvent(_locationHook);
                if (_visibilityHook != 0) Native.UnhookWinEvent(_visibilityHook);
                _locationHook = _visibilityHook = 0;
                _monitor = 0;
            }
        }

        private void OnWinEvent(nint hook, uint kind, nint window, int objectId, int childId, uint thread, uint time)
        {
            if (!_disposed && objectId == 0 && childId == 0 && _bars.Contains(window)) QueueChange();
        }

        private nint OnMessage(nint window, uint message, nuint wParam, nint lParam, nuint id, nuint data)
        {
            nint result = Native.DefSubclassProc(window, message, wParam, lParam);
            if (_watching && (message is 0x001A or 0x007E or 0x02E0 || message == _taskbarCreated)) QueueChange();
            return result;
        }

        private void QueueChange()
        {
            if (_queued || _disposed) return;
            _queued = true;
            if (!_dispatcher.TryEnqueue(() => { _queued = false; if (!_disposed && _watching) Changed?.Invoke(this, EventArgs.Empty); })) _queued = false;
        }

        public void Dispose()
        {
            if (_disposed) return;
            Watch(false);
            Native.RemoveWindowSubclass(_owner, _subclass, 0x504C554D);
            _disposed = true;
            Changed = null; _bars.Clear(); _thickness.Clear();
        }

        private static PopupRect ToRect(Native.Rect r) => new(r.Left, r.Top, r.Right - r.Left, r.Bottom - r.Top);

        internal static class Native
        {
            [StructLayout(LayoutKind.Sequential)] internal struct Rect { public int Left, Top, Right, Bottom; }
            [StructLayout(LayoutKind.Sequential)] internal struct MonitorInfo { public uint Size; public Rect Monitor, Work; public uint Flags; }
            [StructLayout(LayoutKind.Sequential)] internal struct AppBarData { public uint Size; public nint Window; public uint Callback, Edge; public Rect Rect; public nint Parameter; }
            internal delegate nint SubclassProc(nint window, uint message, nuint wParam, nint lParam, nuint id, nuint data);
            internal delegate void WinEventProc(nint hook, uint kind, nint window, int objectId, int childId, uint thread, uint time);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool IsWindow(nint window);
            [DllImport("user32.dll")] internal static extern nint MonitorFromWindow(nint window, uint flags);
            [DllImport("user32.dll")] internal static extern nint MonitorFromRect(ref Rect rect, uint flags);
            [DllImport("user32.dll", EntryPoint="GetMonitorInfoW")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetMonitorInfo(nint monitor, ref MonitorInfo info);
            [DllImport("user32.dll")] internal static extern uint GetDpiForWindow(nint window);
            [DllImport("shcore.dll")] internal static extern int GetDpiForMonitor(nint monitor, int kind, out uint x, out uint y);
            [DllImport("shell32.dll")] internal static extern nuint SHAppBarMessage(uint message, ref AppBarData data);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetWindowRect(nint window, out Rect rect);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetClientRect(nint window, out Rect rect);
            [DllImport("user32.dll", CharSet=CharSet.Unicode)] internal static extern uint RegisterWindowMessage(string name);
            [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool SetWindowSubclass(nint window, SubclassProc proc, nuint id, nuint data);
            [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool RemoveWindowSubclass(nint window, SubclassProc proc, nuint id);
            [DllImport("comctl32.dll")] internal static extern nint DefSubclassProc(nint window, uint message, nuint wParam, nint lParam);
            [DllImport("user32.dll")] internal static extern nint SetWinEventHook(uint min, uint max, nint module, WinEventProc proc, uint process, uint thread, uint flags);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool UnhookWinEvent(nint hook);
            internal static nint GetWindowLongPtr(nint window,int index) => IntPtr.Size==8?GetWindowLongPtr64(window,index):GetWindowLong32(window,index);
            internal static nint SetWindowLongPtr(nint window,int index,nint value) => IntPtr.Size==8?SetWindowLongPtr64(window,index,value):SetWindowLong32(window,index,(int)value);
            [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] private static extern nint GetWindowLongPtr64(nint window, int index);
            [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW")] private static extern nint SetWindowLongPtr64(nint window, int index, nint value);
            [DllImport("user32.dll", EntryPoint="GetWindowLongW")] private static extern int GetWindowLong32(nint window,int index);
            [DllImport("user32.dll", EntryPoint="SetWindowLongW")] private static extern int SetWindowLong32(nint window,int index,int value);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool SetLayeredWindowAttributes(nint window, uint color, byte alpha, uint flags);
            [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] internal static extern bool GetLayeredWindowAttributes(nint window, out uint color, out byte alpha, out uint flags);
            [DllImport("user32.dll")] internal static extern nint GetForegroundWindow();
            [DllImport("dwmapi.dll")] internal static extern int DwmSetWindowAttribute(nint window, uint attribute, ref int value, uint size);
        }
    }
}
