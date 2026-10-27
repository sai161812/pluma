using System.IO;
using System.Text.Json;
using PLUMA.UI;

internal static class EventFeedChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static CoreRequestResult<T> Ok<T>(T value) where T : class => new(value, CoreConnectionFailure.None, false, null, null);
    private static CoreRequestProtocol.EventBatch Batch(string stream, long last, bool reset,
        params CoreRequestProtocol.LedgerEvent[] events) => new(1, "event_batch", Id(), stream,
            last == 0 ? 0 : 1, last, last, reset, false, events);

    internal static async Task RunAsync(Action<bool, string> check)
    {
        var source = new Client();
        string old = source.Add(); source.Snapshot = [old];
        var owner = new EventFeedController(source);
        var notices = new List<EventFeedEntry>(); owner.Notice += notices.Add;
        await owner.PollOnceAsync(default);
        check(owner.View.Entries.Single().Verified && notices.Count == 0,
            "activity reset reads independent saved outcome without replaying historical success notices");

        string a = source.Add(), b = source.Add();
        source.Next = Batch(source.Stream, 3, false, source.Event(1, a), source.Event(2, b), source.Event(3, a, "task_changed"));
        await owner.PollOnceAsync(default);
        check(owner.View.Entries.TakeLast(2).Select(x => x.TaskId).SequenceEqual(new[] { b, a }) && notices.Count == 2,
            "event bursts coalesce per task in sequence order and emit one evidence-backed notice each");
        await owner.PollOnceAsync(default);
        check(notices.Count == 2 && owner.View.Entries.Length == 3,
            "replayed event identities cannot duplicate feed entries or notices");
        check(owner.View.Entries.All(x => !x.DisplayText.Contains("PRIVATE_MARKER") && !x.Message.Contains('_') && !x.Message.Contains('—')),
            "private command, server message and result bodies never enter deterministic activity copy");

        var late = new Client(); var settling = new EventFeedController(late);
        await settling.PollOnceAsync(default);
        string lateTask = late.Add(verified: false);
        late.Next = Batch(late.Stream, 1, false, late.Event(1, lateTask));
        await settling.PollOnceAsync(default);
        late.Results[lateTask] = late.Results[lateTask] with { CompletionVerified = true };
        await settling.PollOnceAsync(default);
        check(settling.View.Entries.Last().Verified,
            "terminal cache settling without another ledger event receives bounded independent readback");

        string changed = source.Add();
        source.Next = Batch(source.Stream, 5, false, source.Event(4, changed), source.Event(5, a, "task_changed"));
        source.FailTask = a;
        int count = owner.View.Entries.Length;
        try { await owner.PollOnceAsync(default); throw new Exception("Missing evidence accepted."); } catch (IOException) { }
        check(owner.View.Entries.Length == count && notices.Count == 2,
            "failed material readback commits neither a partial burst nor a notification");
        source.FailTask = null;
        await owner.PollOnceAsync(default);
        check(source.After == 3 && notices.Count == 3 && owner.View.Entries.Last().TaskId == changed,
            "readback recovery retries the uncommitted cursor without repeating previous terminal notices");

        foreach (var scenario in new[] { ("SUCCEEDED", false, true, false), ("SUCCEEDED", true, false, false),
            ("STOPPED_WITH_RESIDUAL", false, true, true), ("FAILED", false, true, false) })
        {
            string task = source.Add(scenario.Item1, scenario.Item2, scenario.Item3, scenario.Item4);
            long sequence = source.Next.LastSequence + 1;
            source.Next = Batch(source.Stream, sequence, false, source.Event(sequence, task));
            int before = notices.Count;
            await owner.PollOnceAsync(default);
            var entry = owner.View.Entries.Last();
            check(!entry.Verified && !entry.Message.Contains("completed and verified") &&
                (scenario.Item3 ? notices.Count == before + 1 : notices.Count == before),
                "activity cannot invent verified completion from state or unpersisted terminal: " + scenario.Item1 + "/" + scenario.Item3);
        }

        source.Stream = Id(); source.Snapshot = [a];
        source.Next = Batch(source.Stream, 20, true);
        int beforeReset = notices.Count;
        await owner.PollOnceAsync(default);
        check(owner.View.Entries.Length == 1 && notices.Count == beforeReset,
            "stream replacement resynchronizes from saved evidence and suppresses old notices");
        source.Next = Batch(source.Stream, 22, false, source.Event(22, a, "task_changed"));
        try { await owner.PollOnceAsync(default); throw new Exception("Gap accepted."); } catch (JsonException) { }
        check(owner.View.Entries.Length == 1 && notices.Count == beforeReset,
            "event gaps fail before material state or notification mutation");

        var bounded = new Client(); var buffer = new EventFeedController(bounded);
        await buffer.PollOnceAsync(default);
        for (int index = 1; index <= 205; index++)
        {
            string task = bounded.Add(); bounded.Next = Batch(bounded.Stream, index, false, bounded.Event(index, task));
            await buffer.PollOnceAsync(default);
        }
        check(buffer.View.Entries.Length == 200 && buffer.View.Entries.Select(x => x.Identity).Distinct().Count() == 200,
            "transient event display remains bounded under sustained bursts");

        var many = new Client(); var active = new EventFeedController(many);
        await active.PollOnceAsync(default);
        for (int index = 1; index <= 26; index++)
        {
            string task = many.Add(persisted: false);
            many.Next = Batch(many.Stream, index, false, many.Event(index, task));
            await active.PollOnceAsync(default);
        }
        foreach (string task in many.Results.Keys.ToArray()) many.Results[task] = many.Results[task] with { TerminalPersisted = true };
        await active.PollOnceAsync(default); await active.PollOnceAsync(default);
        check(many.Results.Keys.All(task => active.View.Entries.Last(entry => entry.TaskId == task).Verified),
            "bounded settling batches rotate fairly across more than 25 active task identities");

        var stalled = new Client { Stall = true }; var closing = new EventFeedController(stalled);
        using var lifetime = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        await closing.RunAsync(lifetime.Token).WaitAsync(TimeSpan.FromSeconds(2));
        check(stalled.Cancelled && closing.View.Entries.Length == 0,
            "shell cancellation drains an outstanding read-only poll without claiming task cancellation");
    }

    private sealed class Client : IEventFeedClient
    {
        internal string Stream = Id();
        internal string[] Snapshot = [];
        internal readonly Dictionary<string, CoreRequestProtocol.TaskSummary> Tasks = [];
        internal readonly Dictionary<string, CoreRequestProtocol.TerminalReadback> Results = [];
        internal CoreRequestProtocol.EventBatch Next;
        internal string? FailTask;
        internal long After;
        internal bool Stall, Cancelled;
        internal Client() { Next = Batch(Stream, 0, true); }
        internal string Add(string state = "SUCCEEDED", bool verified = true, bool persisted = true, bool residual = false)
        {
            string task = Id(), request = Id(), now = DateTimeOffset.UtcNow.ToString("O");
            Tasks[task] = new(task, request, "text", "PRIVATE_MARKER command", now, now, now, state, "FAST", null, null);
            Results[task] = new(1, "terminal_readback", request, task, true, state, verified, persisted, residual, "FAST", "PRIVATE_MARKER server message", 1);
            return task;
        }
        internal CoreRequestProtocol.LedgerEvent Event(long sequence, string task, string kind = "task_recorded") =>
            new(sequence, kind, DateTimeOffset.UtcNow.ToString("O"), task, Tasks[task].RequestId, null);
        public async Task<CoreRequestResult<CoreRequestProtocol.EventBatch>> EventsAsync(string request, string? stream, long after, CancellationToken token)
        {
            After = after;
            if (Stall)
                try { await Task.Delay(Timeout.Infinite, token); }
                catch (OperationCanceledException) { Cancelled = true; throw; }
            return Ok(Next);
        }
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, string? task, CancellationToken token)
        {
            if (task is not null) throw new InvalidOperationException("The feed must not fetch complete task history for correlation.");
            return Task.FromResult(Ok(new CoreRequestProtocol.HistoryReply(1, "history_reply", request, null,
                Snapshot.Select(id => Tasks[id]).ToArray(), [])));
        }
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token) =>
            Task.FromResult(task == FailTask ? CoreRequestResult<CoreRequestProtocol.TerminalReadback>.Failed(CoreConnectionFailure.Unavailable) : Ok(Results[task]));
        public Task<CoreRequestResult<CoreRequestProtocol.ActivityPage>> ActivityAsync(string request, string task, CancellationToken token) =>
            Task.FromResult(Ok(new CoreRequestProtocol.ActivityPage(1, "activity_page", request, task,
                Tasks[task].RequestId, Tasks[task].FinalState, Tasks[task].Route, [], 0, false, null)));
    }
}
