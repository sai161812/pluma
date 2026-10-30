using System.IO;
using System.Text.Json;
using PLUMA.UI;

internal static class SurfaceFactChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static CoreRequestResult<T> Ok<T>(T value) where T : class => new(value, CoreConnectionFailure.None, false, null, null);
    internal static async Task RunAsync(Action<bool, string> check)
    {
        var source = new Client(); var owner = new EventFeedController(source);
        var facts = new List<ActivitySurfaceFact>(); owner.Surface += facts.Add;
        await owner.PollOnceAsync(default);
        check(facts.Count == 0, "historical route snapshot cannot replay a route popup");
        source.Route = "SMART";
        source.Next = source.Batch(3, false, source.Event(1, "task_recorded"), source.Event(2, "action_recorded", 10), source.Event(3, "action_recorded", 20));
        source.FailAfter = 19;
        try { await owner.PollOnceAsync(default); throw new Exception("Missing action accepted."); } catch (IOException) { }
        check(facts.Count == 0, "a failed action readback publishes no partial route or result surfaces");
        source.FailAfter = null;
        await owner.PollOnceAsync(default);
        check(facts.Select(f => f.Surface).SequenceEqual(new[] { 6, 8, 8 }) && source.ReadAfter.Contains(19),
            "exact action identities are read independently and routed to native route/result surfaces");
        string key = facts.Last().Key;
        await owner.PollOnceAsync(default);
        check(facts.Count == 3, "event replay cannot repeat native surface facts");
        source.Actions[20] = source.Actions[20] with { Verified = true };
        source.Next = source.Batch(4, false, source.Event(4, "action_changed", 20));
        await owner.PollOnceAsync(default);
        check(facts.Count == 4 && facts.Last() is { Surface: 8, Action.Verified: true } && facts.Last().Key == key,
            "new material verification replaces the same action surface key");
        source.Actions[20] = source.Actions[20] with { Verified = false, ErrorRecorded = true, PolicyDenied = true };
        source.Next = source.Batch(5, false, source.Event(5, "action_changed", 20));
        await owner.PollOnceAsync(default);
        check(facts.Last().Surface == 19 && facts.Last().Key == key && facts.Last().Action!.PolicyDenied,
            "an explicit saved policy denial selects the denial surface without executing a tool");
        source.Stream = Id(); source.Next = source.Batch(10, true);
        await owner.PollOnceAsync(default);
        source.Next = source.Batch(11, false, source.Event(11, "task_changed"));
        await owner.PollOnceAsync(default);
        check(facts.Count == 5, "stream reset and unchanged saved route suppress historical surface replay");
        source.Next = source.Batch(12, false, source.Event(12, "action_changed"));
        try { await owner.PollOnceAsync(default); throw new Exception("Unidentified action accepted."); } catch (JsonException) { }
        check(facts.Count == 5, "an action event without its saved action identity fails closed before presentation");

        var racing = new Client { EmptySnapshot = true };
        var coherent = new EventFeedController(racing);
        var delivered = new List<string>();
        coherent.Surface += _ => delivered.Add("surface"); coherent.Notice += _ => delivered.Add("terminal");
        await coherent.PollOnceAsync(default);
        racing.Next = racing.Batch(1, false, racing.Event(1, "task_recorded"));
        racing.AdvanceOnRead = true;
        await coherent.PollOnceAsync(default);
        check(delivered.SequenceEqual(new[] { "surface", "surface", "surface", "terminal" }),
            "journal coherence retry delivers committed action facts before terminal notice when readback races events");
    }

    private sealed class Client : IEventFeedClient
    {
        internal string Stream = Id();
        internal string Route = "FAST";
        private readonly string _task = Id(), _request = Id();
        internal CoreRequestProtocol.EventBatch Next;
        internal long? FailAfter;
        internal bool EmptySnapshot, AdvanceOnRead;
        internal readonly List<long> ReadAfter = [];
        internal readonly Dictionary<long, CoreRequestProtocol.ActivityAction> Actions = new()
        { [10] = new(10, 0, "fixture_read", "READ", false, false, false, false, false, null),
          [20] = new(20, 1, "fixture_read", "READ", false, false, false, false, false, null) };
        internal Client() { Next = Batch(0, true); }
        internal CoreRequestProtocol.EventBatch Batch(long last, bool reset, params CoreRequestProtocol.LedgerEvent[] items) =>
            new(1, "event_batch", Id(), Stream, last == 0 ? 0 : 1, last, last, reset, false, items);
        internal CoreRequestProtocol.LedgerEvent Event(long sequence, string kind, long? action = null) =>
            new(sequence, kind, DateTimeOffset.UtcNow.ToString("O"), _task, _request, action);
        public Task<CoreRequestResult<CoreRequestProtocol.EventBatch>> EventsAsync(string request, string? stream, long after, CancellationToken token) =>
            Task.FromResult(Ok(Next));
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, string? task, CancellationToken token) =>
            Task.FromResult(Ok(new CoreRequestProtocol.HistoryReply(1, "history_reply", request, null,
                EmptySnapshot ? [] : [new(_task, _request, "text", "PRIVATE_SURFACE_PAYLOAD", DateTimeOffset.UtcNow.ToString("O"), null, null, null, Route, null, null)], [])));
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token)
        {
            if (AdvanceOnRead)
            {
                AdvanceOnRead = false;
                Next = Batch(3, false, Event(1, "task_recorded"), Event(2, "action_recorded", 10), Event(3, "action_recorded", 20));
            }
            return Task.FromResult(Ok(new CoreRequestProtocol.TerminalReadback(1, "terminal_readback", request, task, true, "SUCCEEDED", true, true, false, Route, "PRIVATE_SURFACE_PAYLOAD", 1)));
        }
        public Task<CoreRequestResult<CoreRequestProtocol.ActivityPage>> ActivityAsync(string request, string task, CancellationToken token, long afterActionId = 0)
        {
            ReadAfter.Add(afterActionId);
            return Task.FromResult(afterActionId == FailAfter
                ? CoreRequestResult<CoreRequestProtocol.ActivityPage>.Failed(CoreConnectionFailure.Unavailable)
                : Ok(new CoreRequestProtocol.ActivityPage(1, "activity_page", request, task, _request, "SUCCEEDED", Route,
                    Actions.Values.Where(a => a.ActionId > afterActionId).OrderBy(a => a.ActionId).Take(1).ToArray(),
                    Actions.Keys.Where(id => id > afterActionId).DefaultIfEmpty(afterActionId).Min(), Actions.Keys.Count(id => id > afterActionId) > 1, null)));
        }
    }
}
