using System;
using System.Runtime.InteropServices;
using Microsoft.UI.Xaml;

namespace PLUMA.UI;

/// <summary>One shell-owned native tray entry. Never owns Explorer or a global hook.</summary>
internal sealed class NativeActivityTray : IDisposable
{
    private const uint Message = 0x8000 + 41;
    private const nuint SubclassId = 0x504c554d;
    private readonly nint _window;
    private readonly Action _activity;
    private readonly SubclassProc _callback;
    private readonly uint _taskbarCreated;
    private bool _closed, _subclassed;
    internal bool IsAvailable { get; private set; }
    internal bool IsDisposed => _closed;
    internal NativeActivityTray(Window window, Action activity)
    {
        _window = WinRT.Interop.WindowNative.GetWindowHandle(window); _activity = activity;
        _callback = HandleMessage; _taskbarCreated = RegisterWindowMessage("TaskbarCreated");
        _subclassed = SetWindowSubclass(_window, _callback, SubclassId, 0);
        if (_subclassed) Add();
    }
    private NotifyIcon Icon() => new() { Size = (uint)Marshal.SizeOf<NotifyIcon>(), Window = _window,
        Id = 1, Flags = 1 | 2 | 4, Callback = Message, Icon = LoadIcon(0, (nint)32512), Tip = "PLUMA" };
    private void Add() { var data = Icon(); IsAvailable = ShellNotifyIcon(0, ref data); }
    private nint HandleMessage(nint hwnd, uint message, nuint wparam, nint lparam, nuint id, nuint data)
    {
        if (!_closed && _taskbarCreated != 0 && message == _taskbarCreated) Add();
        if (!_closed && message == Message && wparam == 1)
        {
            if ((uint)lparam == 0x202) _activity(); // Left release.
            if ((uint)lparam == 0x205) ShowMenu();
            return 0;
        }
        return DefSubclassProc(hwnd, message, wparam, lparam);
    }
    private void ShowMenu()
    {
        nint menu = CreatePopupMenu();
        if (menu == 0) return;
        try
        {
            if (!AppendMenu(menu, 0, 1, "Activity")) return;
            if (!GetCursorPos(out Point point)) return;
            SetForegroundWindow(_window);
            uint command = TrackPopupMenu(menu, 0x100 | 2, point.X, point.Y, 0, _window, 0);
            Select(command);
        }
        finally { DestroyMenu(menu); }
    }
    internal void Select(uint command) { if (!_closed && command == 1) _activity(); }
    public void Dispose()
    {
        if (_closed) return;
        _closed = true;
        var data = Icon(); ShellNotifyIcon(2, ref data); IsAvailable = false;
        if (_subclassed) { RemoveWindowSubclass(_window, _callback, SubclassId); _subclassed = false; }
    }
    private delegate nint SubclassProc(nint hwnd, uint message, nuint wparam, nint lparam, nuint id, nuint data);
    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)] private struct NotifyIcon
    {
        public uint Size; public nint Window; public uint Id, Flags, Callback; public nint Icon;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)] public string Tip;
        public uint State, StateMask;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 256)] public string Info;
        public uint Timeout;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 64)] public string InfoTitle;
        public uint InfoFlags; public Guid Guid; public nint BalloonIcon;
    }
    [DllImport("shell32.dll", EntryPoint = "Shell_NotifyIconW", CharSet = CharSet.Unicode)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ShellNotifyIcon(uint operation, ref NotifyIcon data);
    [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool SetWindowSubclass(nint hwnd, SubclassProc callback, nuint id, nuint data);
    [DllImport("comctl32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool RemoveWindowSubclass(nint hwnd, SubclassProc callback, nuint id);
    [DllImport("comctl32.dll")] private static extern nint DefSubclassProc(nint hwnd, uint message, nuint wparam, nint lparam);
    [DllImport("user32.dll", EntryPoint = "RegisterWindowMessageW", CharSet = CharSet.Unicode)] private static extern uint RegisterWindowMessage(string name);
    [DllImport("user32.dll", EntryPoint = "LoadIconW")] private static extern nint LoadIcon(nint instance, nint icon);
    [DllImport("user32.dll")] private static extern nint CreatePopupMenu();
    [DllImport("user32.dll", EntryPoint = "AppendMenuW", CharSet = CharSet.Unicode)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool AppendMenu(nint menu, uint flags, nuint id, string text);
    [DllImport("user32.dll")] private static extern uint TrackPopupMenu(nint menu, uint flags, int x, int y, int reserved, nint window, nint area);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DestroyMenu(nint menu);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetCursorPos(out Point point);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool SetForegroundWindow(nint window);
}
