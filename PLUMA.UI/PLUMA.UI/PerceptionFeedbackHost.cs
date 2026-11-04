using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;

namespace PLUMA.UI;

/// <summary>Shell-owned target feedback. No image buffers, capture, input or task execution.</summary>
internal sealed class PerceptionFeedbackHost : IDisposable
{
    private readonly Window _owner;
    private readonly DispatcherQueueTimer _timer;
    private readonly HashSet<string> _seen = new(), _flashed = new(), _stopped = new();
    private readonly Queue<string> _seenOrder = new(), _flashOrder = new();
    private RuntimeView _runtime = new([], false, null);
    private PerceptionPresentation? _lease;
    private CoreRequestProtocol.PerceptionObservation? _observation;
    private PerceptionFeedbackWindow? _window;
    private bool _disposed, _drawn;
    internal bool IsDisposed => _disposed;
    internal nint Handle => _window?.Handle ?? 0;
    internal bool TimerRunning => _timer.IsRunning;
    internal bool MatchVisible => _window?.Marker.IsMatchVisible == true;
    internal CoreRequestProtocol.PerceptionObservation? ObservationForAcceptance => _observation;
    internal event Action<CoreRequestProtocol.PerceptionObservation, PerceptionPlacement>? Presented;
    internal string? LastFailure {get;private set;}

    internal PerceptionFeedbackHost(Window owner)
    {
        _owner = owner;
        _timer = owner.DispatcherQueue.CreateTimer();
        _timer.Interval = TimeSpan.FromMilliseconds(33);
        _timer.Tick += (_, _) => Draw();
        owner.Closed += OnClosed;
    }

    private static void Remember(string id, HashSet<string> set, Queue<string> order)
    {
        if (!set.Add(id)) return;
        order.Enqueue(id);
        if (order.Count > 512) set.Remove(order.Dequeue());
    }

    internal void Runtime(RuntimeView value)
    {
        if (_disposed) return;
        _runtime = value;
        _stopped.RemoveWhere(id => !value.Tasks.Any(task => task.TaskId == id));
        if (_lease is not null) Draw();
    }

    internal void Stop()
    {
        if (_disposed) return;
        foreach (var task in _runtime.Tasks) _stopped.Add(task.TaskId);
        Clear();
    }

    internal void Observe(CoreRequestProtocol.PerceptionSnapshot? frame)
    {
        if (_disposed) return;
        if (frame is null) { Clear(); return; }
        if (_observation is { } previous && !frame.Observations.Any(item => item.ObservationId == previous.ObservationId)) Clear();
        // Only one native foreground HWND can be highlighted. Select the newest
        // actual observation, never create a desktop-wide or multi-window layer.
        long foreground = NativePerceptionTarget.Foreground;
        var next = frame.Observations.Where(item => item.Hwnd == foreground && !_stopped.Contains(item.TaskId))
            .OrderByDescending(item => DateTimeOffset.Parse(item.ObservedUtc)).ThenByDescending(item => item.Sequence).FirstOrDefault();
        if (next is null) { Clear(); return; }
        if (_seen.Contains(next.ObservationId)) return;
        Remember(next.ObservationId, _seen, _seenOrder);
        Clear();
        try
        {
            _observation = next;
            _lease = PerceptionPresentation.TryCreate(next, _runtime, _stopped.Contains(next.TaskId), NativePerceptionTarget.Read,
                project: observation => NativePerceptionTarget.Map(observation, 1));
            if (_lease is null) { LastFailure="ADMISSION_REFUSED"; Clear(); return; }
            var pixels = _lease.Revalidate(_runtime, false, NativePerceptionTarget.Read);
            if (pixels is null) { Clear(); return; }
            _window = new PerceptionFeedbackWindow(_owner);
            _window.Flash.FlashCompleted += (_, _) => { if (!MatchVisible) Clear(); };
            _window.Place(pixels);
            _window.ShowHidden();
            _timer.Start();
        }
        catch(Exception error) { LastFailure=error.GetType().Name+":"+error.HResult.ToString("x8"); Clear(); }
    }

    private void Draw()
    {
        if (_disposed || _lease is null || _window is null || _observation is null) return;
        try
        {
            var pixels = _lease.Revalidate(_runtime, _stopped.Contains(_observation.TaskId), NativePerceptionTarget.Read);
            if (pixels is null || !_window.Matches(pixels)) { Clear(); return; }
            if (_drawn) return;
            if (!_window.LayoutReady) return;
            double scale = _window.Scale;
            var local = NativePerceptionTarget.Map(_observation, scale);
            if (local is null || _lease.Revalidate(_runtime, false, NativePerceptionTarget.Read) is null) { Clear(); return; }
            _window.Render(_observation, local, !_flashed.Contains(_observation.SnapshotId));
            Remember(_observation.SnapshotId, _flashed, _flashOrder);
            _drawn = true;
            Presented?.Invoke(_observation, local);
        }
        catch(Exception error) { LastFailure=error.GetType().Name+":"+error.HResult.ToString("x8"); Clear(); }
    }

    private void Clear()
    {
        _timer.Stop(); _lease?.Revoke(); _lease = null; _observation = null; _drawn = false;
        var window = _window; _window = null;
        window?.Close(); // Only this host's newly created HWND.
    }
    private void OnClosed(object sender, WindowEventArgs args) => Dispose();
    public void Dispose()
    {
        if (_disposed) return;
        Clear(); _disposed = true; _owner.Closed -= OnClosed;
        _seen.Clear(); _flashed.Clear(); _stopped.Clear(); _seenOrder.Clear(); _flashOrder.Clear();
    }
}
