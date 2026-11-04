using System;
using System.Linq;

namespace PLUMA.UI;

internal sealed record PerceptionTargetState(long Hwnd, int Pid, long CreationTime,
    string WindowClass, string TitleHash, CoreRequestProtocol.PerceptionBounds Bounds,
    double DpiScale, long Monitor, bool Visible, bool Foreground, bool CoordinatesArePhysical = true);

internal sealed record PerceptionPlacement(double DesktopX, double DesktopY, double Width,
    double Height, double MatchX, double MatchY, double MatchWidth, double MatchHeight,
    double? Confidence);

/// <summary>A revocable presentation lease. Never captures, executes or verifies an action.</summary>
internal sealed class PerceptionPresentation
{
    private readonly CoreRequestProtocol.PerceptionObservation _observation;
    private readonly TimeProvider _clock;
    private readonly long _started;
    private readonly TimeSpan _remaining;
    private readonly long _monitor;
    private DateTimeOffset _lastUtc;
    private bool _revoked;
    internal string ObservationId => _observation.ObservationId;

    private PerceptionPresentation(CoreRequestProtocol.PerceptionObservation observation,
        TimeProvider clock, DateTimeOffset now, long started, long monitor)
    {
        _observation = observation; _clock = clock; _started = started;
        _lastUtc = now; _remaining = DateTimeOffset.Parse(observation.ExpiresUtc) - now;
        _monitor = monitor;
    }

    internal static PerceptionPresentation? TryCreate(CoreRequestProtocol.PerceptionObservation observation,
        RuntimeView runtime, bool priorityStop, Func<long, PerceptionTargetState?> read,
        TimeProvider? clock = null)
    {
        try { observation.Validate(); }
        catch (System.Text.Json.JsonException) { return null; }
        var time = clock ?? TimeProvider.System;
        long started = time.GetTimestamp();
        var now = time.GetUtcNow();
        if (now < DateTimeOffset.Parse(observation.ObservedUtc) || now >= DateTimeOffset.Parse(observation.ExpiresUtc) ||
            !TaskCurrent(observation, runtime, priorityStop)) return null;
        // Ambiguous/missing OCR targets have no presentation lease, even for a flash.
        if (observation.MatchState is "NONE" or "AMBIGUOUS") return null;
        PerceptionTargetState? native;
        try { native = read(observation.Hwnd); }
        catch { return null; }
        if (native is null || native.Monitor == 0) return null;
        var lease = new PerceptionPresentation(observation, time, now, started, native.Monitor);
        return lease.Revalidate(runtime, priorityStop, _ => native) is null ? null : lease;
    }

    private static bool TaskCurrent(CoreRequestProtocol.PerceptionObservation observation,
        RuntimeView runtime, bool priorityStop) => !priorityStop && runtime.Connected && runtime.CoreReady == true &&
        runtime.Tasks.Count(task => task.TaskId == observation.TaskId &&
            task.TaskRequestId == observation.TaskRequestId && task.State == "RUNNING") == 1;

    internal void Revoke() => _revoked = true;

    internal PerceptionPlacement? Revalidate(RuntimeView runtime, bool priorityStop,
        Func<long, PerceptionTargetState?> read)
    {
        if (_revoked) return null;
        try
        {
            var now = _clock.GetUtcNow();
            if (now < _lastUtc || now >= DateTimeOffset.Parse(_observation.ExpiresUtc) ||
                _clock.GetElapsedTime(_started) >= _remaining || !TaskCurrent(_observation, runtime, priorityStop))
                return Reject();
            _lastUtc = now;
            var target = read(_observation.Hwnd);
            if (target is null || !target.Visible || !target.Foreground || !target.CoordinatesArePhysical || target.Monitor != _monitor ||
                target.Hwnd != _observation.Hwnd || target.Pid != _observation.Pid ||
                target.CreationTime != _observation.CreationTime || target.WindowClass != _observation.WindowClass ||
                target.TitleHash != _observation.TitleHash || target.Bounds != _observation.WindowBounds ||
                target.DpiScale != _observation.DpiScale) return Reject();
            // Native read duration counts against both clocks. Never grant a stale frame.
            var after = _clock.GetUtcNow();
            if (after < now || after >= DateTimeOffset.Parse(_observation.ExpiresUtc) ||
                _clock.GetElapsedTime(_started) >= _remaining) return Reject();
            _lastUtc = after;
            var region = _observation.Region;
            var match = _observation.Match;
            double scale = target.DpiScale;
            // Desktop placement stays physical pixels; control-local geometry is in DIPs.
            // The host occupies only the captured region, including on negative-coordinate monitors.
            return new((long)target.Bounds.Left + region.Left, (long)target.Bounds.Top + region.Top,
                region.Width / scale, region.Height / scale,
                match is null ? 0 : ((long)match.Bounds.Left - region.Left) / scale,
                match is null ? 0 : ((long)match.Bounds.Top - region.Top) / scale,
                match is null ? 0 : match.Bounds.Width / scale,
                match is null ? 0 : match.Bounds.Height / scale, match?.Confidence);
        }
        catch { return Reject(); }
    }

    private PerceptionPlacement? Reject() { _revoked = true; return null; }
}
