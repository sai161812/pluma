using PLUMA.UI;

internal static class PerceptionPresentationChecks
{
    private sealed class Clock : TimeProvider
    {
        internal DateTimeOffset Utc = new(2026, 11, 4, 12, 0, 0, TimeSpan.Zero);
        internal long Ticks;
        public override DateTimeOffset GetUtcNow() => Utc;
        public override long GetTimestamp() => Ticks;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;
    }

    internal static void Run(Action<bool, string> check)
    {
        string Id() => Guid.NewGuid().ToString("D");
        var clock = new Clock();
        var observation = new CoreRequestProtocol.PerceptionObservation(Id(), Id(), 1, Id(), Id(), 123, 456, 789,
            "OwnedClass", "sha256:" + new string('a', 64), new(-1200, -100, -800, 100), 1.25,
            new(20, 10, 220, 110), clock.Utc.ToString("O"), clock.Utc.AddSeconds(3).ToString("O"), "UNIQUE",
            new(Id(), new(30, 20, 80, 50), .97), true);
        var task = new CoreRequestProtocol.RuntimeTask(observation.TaskId, observation.TaskRequestId, "RUNNING",
            0, 0, null, null, null, null, null, null, null, null, null, null);
        var runtime = new RuntimeView([task], true, 1, Id(), true);
        var target = new PerceptionTargetState(123, 456, 789, observation.WindowClass, observation.TitleHash,
            observation.WindowBounds, 1.25, 100, true, true);
        PerceptionPresentation New() => PerceptionPresentation.TryCreate(observation, runtime, false, _ => target, clock)
            ?? throw new Exception("Fresh evidence refused.");
        var placement = New().Revalidate(runtime, false, _ => target)!;
        var completed=observation with {TaskPhase="SUCCEEDED"};
        check(PerceptionPresentation.TryCreate(completed,runtime with {Tasks=[]},false,_=>target,clock) is not null &&
            PerceptionPresentation.TryCreate(completed,runtime with {Tasks=[]},true,_=>target,clock) is null &&
            PerceptionPresentation.TryCreate(completed,runtime with {Tasks=[task with {State="STOPPING"}]},false,_=>target,clock) is null,
            "persisted successful observation tail remains transient and rejects priority STOP or a conflicting task phase");
        check(placement is { DesktopX: -1180, DesktopY: -90, Width: 160, Height: 80,
            MatchX: 8, MatchY: 8, MatchWidth: 40, MatchHeight: 24, Confidence: .97 },
            "presentation uses captured ROI pixels, negative desktop origin and actual DPI/confidence without rounding guesses");

        foreach (string fault in new[] { "missing", "hwnd", "pid", "creation", "class", "title", "move", "resize", "dpi",
            "monitor", "hidden", "foreground", "legacy-coordinates", "exception" })
        {
            PerceptionTargetState? changed = fault switch
            {
                "missing" => null, "hwnd" => target with { Hwnd = 124 }, "pid" => target with { Pid = 457 },
                "creation" => target with { CreationTime = 790 }, "class" => target with { WindowClass = "Changed" },
                "title" => target with { TitleHash = "sha256:" + new string('b', 64) },
                "move" => target with { Bounds = new(-1199, -100, -799, 100) },
                "resize" => target with { Bounds = new(-1200, -100, -799, 100) }, "dpi" => target with { DpiScale = 1.5 },
                "monitor" => target with { Monitor = 101 }, "hidden" => target with { Visible = false },
                "foreground" => target with { Foreground = false }, "legacy-coordinates" => target with { CoordinatesArePhysical = false }, _ => target
            };
            var lease = New();
            check(lease.Revalidate(runtime, false, _ => fault == "exception" ? throw new Exception("Probe failed") : changed) is null &&
                lease.Revalidate(runtime, false, _ => target) is null,
                "target change revokes lease permanently: " + fault);
        }
        foreach (string fault in new[] { "stop", "disconnect", "not-ready", "unknown-ready", "missing-task", "request", "stopping", "terminal", "duplicate" })
        {
            var changed = fault switch
            {
                "disconnect" => runtime with { Connected = false }, "not-ready" => runtime with { CoreReady = false },
                "unknown-ready" => runtime with { CoreReady = null }, "missing-task" or "terminal" => runtime with { Tasks = [] },
                "request" => runtime with { Tasks = [task with { TaskRequestId = Id() }] },
                "stopping" => runtime with { Tasks = [task with { State = "STOPPING" }] },
                "duplicate" => runtime with { Tasks = [task, task] }, _ => runtime
            };
            var lease = New();
            check(lease.Revalidate(changed, fault == "stop", _ => target) is null &&
                lease.Revalidate(runtime, false, _ => target) is null, "task/STOP change revokes presentation: " + fault);
        }
        foreach (string state in new[] { "NONE", "AMBIGUOUS" })
            check(PerceptionPresentation.TryCreate(observation with { MatchState = state, Match = null }, runtime, false, _ => target, clock) is null,
                "missing or ambiguous OCR target cannot create visual feedback: " + state);
        check(PerceptionPresentation.TryCreate(observation with { MatchState = "NOT_REQUESTED", Match = null }, runtime, false, _ => target, clock) is not null,
            "capture-only receipt may supply flash geometry without inventing a match");
        check(PerceptionPresentation.TryCreate(observation with { DpiScale = double.NaN }, runtime, false, _ => target, clock) is null,
            "malformed observation fails closed before native read");
        var monotonic = New();
        clock.Ticks += TimeSpan.FromSeconds(3).Ticks;
        check(monotonic.Revalidate(runtime, false, _ => target) is null, "monotonic TTL expires even if wall clock stalls");
        clock.Ticks = 0;
        var wall = New(); clock.Utc += TimeSpan.FromSeconds(3);
        check(wall.Revalidate(runtime, false, _ => target) is null, "wall expiry is exclusive at exact boundary");
        clock.Utc -= TimeSpan.FromSeconds(3);
        var backwards = New(); clock.Utc -= TimeSpan.FromMilliseconds(1);
        check(backwards.Revalidate(runtime, false, _ => target) is null, "wall clock reversal revokes existing lease");
        check(PerceptionPresentation.TryCreate(observation, runtime, false, _ => target, clock) is null,
            "future observation is refused rather than extending its lifetime");
        clock.Utc += TimeSpan.FromMilliseconds(1);
        var revoked = New(); revoked.Revoke();
        check(revoked.Revalidate(runtime, false, _ => throw new Exception("Must not probe")) is null,
            "explicit revoke prevents further native probes");
        var slow = PerceptionPresentation.TryCreate(observation, runtime, false, _ =>
        { clock.Ticks += TimeSpan.FromSeconds(3).Ticks; return target; }, clock);
        check(slow is null, "initial native probe duration consumes monotonic lease budget");
        clock.Ticks = 0;
        var repeated = New(); clock.Ticks += TimeSpan.FromSeconds(2).Ticks;
        check(repeated.Revalidate(runtime, false, _ => target) is not null, "fresh lease can be checked again without a new observation");
        clock.Ticks += TimeSpan.FromSeconds(1).Ticks;
        check(repeated.Revalidate(runtime, false, _ => target) is null, "rechecking a lease never renews original TTL");
        check(NativePerceptionTarget.Read(0) is null && NativePerceptionTarget.Read(-1) is null,
            "native probe refuses invalid handles without OS mutations");
        clock.Ticks=0;
        var legacy=target with {CoordinatesArePhysical=false};
        var converted=PerceptionPresentation.TryCreate(observation,runtime,false,_=>legacy,clock,
            _=>new(-1180,-90,200,100,10,10,50,30,.97));
        check(converted is not null && converted.Revalidate(runtime,false,_=>legacy) is {MatchWidth:50},
            "legacy presentation requires an explicit conversion provider rather than guessed DPI multiplication");
        bool moved=false;
        var duringMap=PerceptionPresentation.TryCreate(observation,runtime,false,_=>moved?target with {Monitor=101}:target,clock,
            _=>{moved=true;return new(-1180,-90,200,100,10,10,50,30,.97);});
        check(duringMap is null,"target is re-read after native point conversion; movement during mapping cannot grant a lease");
    }
}
