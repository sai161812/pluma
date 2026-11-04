using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace PLUMA.UI;

/// <summary>Read-only native target probe. No window activation, capture, hooks or process termination.</summary>
internal static class NativePerceptionTarget
{
    internal static PerceptionTargetState? Read(long value)
    {
        if (!OperatingSystem.IsWindows() || value <= 0 || IntPtr.Size != 8) return null;
        // Match the existing backend's window_dpi coordinate contract. A legacy
        // target's native units must never be compared with physical pixels.
        nint context = GetWindowDpiAwarenessContext((nint)value);
        if (context == 0) return null;
        nint previous = SetThreadDpiAwarenessContext(context);
        if (previous == 0) return null;
        try { return ReadTargetCoordinates(value, context); }
        finally
        {
            if (SetThreadDpiAwarenessContext(previous) == 0)
                throw new System.ComponentModel.Win32Exception("Could not restore native target probe DPI context.");
        }
    }

    private static PerceptionTargetState? ReadTargetCoordinates(long value, nint context)
    {
        nint hwnd = (nint)value;
        if (!IsWindow(hwnd) || !IsWindowVisible(hwnd) || IsIconic(hwnd)) return null;
        uint thread = GetWindowThreadProcessId(hwnd, out uint pid);
        if (thread == 0 || pid == 0 || pid > int.MaxValue) return null;
        using var process = new Microsoft.Win32.SafeHandles.SafeProcessHandle(OpenProcess(0x1000, false, pid), true);
        if (process.IsInvalid || !GetProcessTimes(process, out long created, out _, out _, out _)) return null;
        var className = new StringBuilder(257);
        int classLength = GetClassName(hwnd, className, className.Capacity);
        if (classLength <= 0 || classLength > 256 || !GetWindowRect(hwnd, out var bounds)) return null;
        uint dpi = GetDpiForWindow(hwnd);
        if (dpi < 24 || dpi > 768) return null;
        nint monitor = MonitorFromWindow(hwnd, 0);
        if (monitor == 0 || bounds.Right <= bounds.Left || bounds.Bottom <= bounds.Top) return null;
        // Reading another process's caption uses the OS caption cache. Refuse our own
        // process: GetWindowText would send synchronous WM_GETTEXT into the UI thread.
        if (pid == (uint)Environment.ProcessId) return null;
        int length = GetWindowTextLength(hwnd);
        if (length < 0 || length > 32767) return null;
        var title = new StringBuilder(length + 2);
        int copied = GetWindowText(hwnd, title, title.Capacity);
        if (copied != length || GetWindowTextLength(hwnd) != length) return null;
        string hash = "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(title.ToString()))).ToLowerInvariant();
        var finalTitle = new StringBuilder(length + 2);
        var finalClass = new StringBuilder(257);
        // Reject changes observed during the probe; never fall back to cached identity/DPI.
        if (!IsWindow(hwnd) || !IsWindowVisible(hwnd) || IsIconic(hwnd) ||
            GetWindowThreadProcessId(hwnd, out uint finalPid) != thread || finalPid != pid ||
            !GetWindowRect(hwnd, out var finalBounds) || !bounds.Equals(finalBounds) ||
            GetDpiForWindow(hwnd) != dpi || GetWindowDpiAwarenessContext(hwnd) != context || MonitorFromWindow(hwnd, 0) != monitor ||
            GetClassName(hwnd, finalClass, finalClass.Capacity) != classLength || finalClass.ToString() != className.ToString() ||
            GetWindowText(hwnd, finalTitle, finalTitle.Capacity) != length || finalTitle.ToString() != title.ToString()) return null;
        return new(value, (int)pid, created, className.ToString(), hash,
            new(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom), dpi / 96.0,
            monitor, true, GetForegroundWindow() == hwnd, GetAwarenessFromDpiAwarenessContext(context) == 2);
    }

    [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd, out uint pid);
    [DllImport("user32.dll")] private static extern uint GetDpiForWindow(nint hwnd);
    [DllImport("user32.dll")] private static extern nint MonitorFromWindow(nint hwnd, uint flags);
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern nint SetThreadDpiAwarenessContext(nint context);
    [DllImport("user32.dll")] private static extern nint GetWindowDpiAwarenessContext(nint hwnd);
    [DllImport("user32.dll")] private static extern int GetAwarenessFromDpiAwarenessContext(nint context);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetWindowRect(nint hwnd, out Rect rect);
    [DllImport("user32.dll", EntryPoint = "GetClassNameW", CharSet = CharSet.Unicode)] private static extern int GetClassName(nint hwnd, StringBuilder text, int count);
    [DllImport("user32.dll", EntryPoint = "GetWindowTextLengthW", CharSet = CharSet.Unicode)] private static extern int GetWindowTextLength(nint hwnd);
    [DllImport("user32.dll", EntryPoint = "GetWindowTextW", CharSet = CharSet.Unicode)] private static extern int GetWindowText(nint hwnd, StringBuilder text, int count);
    [DllImport("kernel32.dll")] private static extern nint OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint pid);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetProcessTimes(Microsoft.Win32.SafeHandles.SafeProcessHandle process, out long creation, out long exit, out long kernel, out long user);
}
