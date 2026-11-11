using System;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace PLUMA.UI;

/// <summary>Read-only native target probe. No window activation, capture, hooks or process termination.</summary>
internal static class NativePerceptionTarget
{
    internal static long Foreground => GetForegroundWindow();
    internal static double WindowScale(nint hwnd) => GetDpiForWindow(hwnd) / 96.0;

    internal static PerceptionPlacement? Map(CoreRequestProtocol.PerceptionObservation observation, double hostScale)
    {
        if (!double.IsFinite(hostScale) || hostScale < .25 || hostScale > 8) return null;
        observation.Validate();
        nint hwnd = (nint)observation.Hwnd;
        nint context = GetWindowDpiAwarenessContext(hwnd);
        if (context == 0) return null;
        nint previous = SetThreadDpiAwarenessContext(context);
        if (previous == 0) return null;
        try
        {
            Point Convert(int x, int y)
            {
                var point = new Point { X = checked(observation.WindowBounds.Left + x), Y = checked(observation.WindowBounds.Top + y) };
                if (!LogicalToPhysicalPointForPerMonitorDPI(hwnd, ref point))
                    throw new System.ComponentModel.Win32Exception("Target point conversion unavailable.");
                return point;
            }
            var roi = observation.Region;
            Point origin = Convert(roi.Left, roi.Top), end = Convert(roi.Right, roi.Bottom);
            if (end.X <= origin.X || end.Y <= origin.Y) return null;
            double x = 0, y = 0, width = 0, height = 0;
            if (observation.Match is { } match)
            {
                Point start = Convert(match.Bounds.Left, match.Bounds.Top), finish = Convert(match.Bounds.Right, match.Bounds.Bottom);
                if (start.X < origin.X || start.Y < origin.Y || finish.X > end.X || finish.Y > end.Y || finish.X <= start.X || finish.Y <= start.Y) return null;
                x = ((long)start.X - origin.X) / hostScale; y = ((long)start.Y - origin.Y) / hostScale;
                width = ((long)finish.X - start.X) / hostScale; height = ((long)finish.Y - start.Y) / hostScale;
            }
            return new(origin.X, origin.Y, ((long)end.X-origin.X)/hostScale, ((long)end.Y-origin.Y)/hostScale,
                x, y, width, height, observation.Match?.Confidence);
        }
        finally
        {
            if (SetThreadDpiAwarenessContext(previous) == 0)
                throw new System.ComponentModel.Win32Exception("Could not restore target conversion DPI context.");
        }
    }
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
        string? title = Caption(hwnd,pid);
        if (title is null) return null;
        string hash = "sha256:" + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(title))).ToLowerInvariant();
        var finalClass = new StringBuilder(257);
        // Reject changes observed during the probe; never fall back to cached identity/DPI.
        if (!IsWindow(hwnd) || !IsWindowVisible(hwnd) || IsIconic(hwnd) ||
            GetWindowThreadProcessId(hwnd, out uint finalPid) != thread || finalPid != pid ||
            !GetWindowRect(hwnd, out var finalBounds) || !bounds.Equals(finalBounds) ||
            GetDpiForWindow(hwnd) != dpi || GetWindowDpiAwarenessContext(hwnd) != context || MonitorFromWindow(hwnd, 0) != monitor ||
            GetClassName(hwnd, finalClass, finalClass.Capacity) != classLength || finalClass.ToString() != className.ToString() ||
            Caption(hwnd,pid) != title) return null;
        return new(value, (int)pid, created, className.ToString(), hash,
            new(bounds.Left, bounds.Top, bounds.Right, bounds.Bottom), dpi / 96.0,
            monitor, true, GetForegroundWindow() == hwnd, GetAwarenessFromDpiAwarenessContext(context) == 2);
    }

    private static string? Caption(nint hwnd,uint pid)
    {
        if(pid==(uint)Environment.ProcessId)
        {
            // The documented Windows cache accessor does not send WM_GETTEXT.
            // If unavailable, refuse feedback; never fall back to a synchronous
            // same-thread window message whose timeout Windows would ignore.
            try
            {
                var buffer=new StringBuilder(32769);
                int count=InternalGetWindowText(hwnd,buffer,buffer.Capacity);
                return count<0||count>=32768||(count==0&&Marshal.GetLastWin32Error()!=0) ? null : buffer.ToString();
            }
            catch(EntryPointNotFoundException){return null;}
        }
        int length=GetWindowTextLength(hwnd);
        if(length<0||length>32767||(length==0&&Marshal.GetLastWin32Error()!=0))return null;
        var text=new StringBuilder(length+2);
        int copied=GetWindowText(hwnd,text,text.Capacity);
        if(copied!=length||(copied==0&&Marshal.GetLastWin32Error()!=0))return null;
        int finalLength=GetWindowTextLength(hwnd);
        return finalLength==length&&(finalLength!=0||Marshal.GetLastWin32Error()==0)?text.ToString():null;
    }

    [StructLayout(LayoutKind.Sequential)] private struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] private struct Point { public int X, Y; }
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool LogicalToPhysicalPointForPerMonitorDPI(nint hwnd, ref Point point);
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
    [DllImport("user32.dll", EntryPoint = "GetWindowTextLengthW", CharSet = CharSet.Unicode,SetLastError=true)] private static extern int GetWindowTextLength(nint hwnd);
    [DllImport("user32.dll", EntryPoint = "GetWindowTextW", CharSet = CharSet.Unicode,SetLastError=true)] private static extern int GetWindowText(nint hwnd, StringBuilder text, int count);
    [DllImport("user32.dll",CharSet=CharSet.Unicode,ExactSpelling=true,SetLastError=true)] private static extern int InternalGetWindowText(nint hwnd,StringBuilder text,int count);
    [DllImport("kernel32.dll")] private static extern nint OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint pid);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetProcessTimes(Microsoft.Win32.SafeHandles.SafeProcessHandle process, out long creation, out long exit, out long kernel, out long user);
}
