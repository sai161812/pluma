using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal interface IEventFeedClient
{
    Task<CoreRequestResult<CoreRequestProtocol.EventBatch>> EventsAsync(string request, string? stream, long after, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, string? task, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token);
}

internal sealed class CoreEventFeedClient(CoreIpcClient client) : IEventFeedClient
{
    public Task<CoreRequestResult<CoreRequestProtocol.EventBatch>> EventsAsync(string request, string? stream, long after, CancellationToken token) =>
        client.GetEventsAsync(new(request, stream, after, 25), token);
    public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, string? task, CancellationToken token) =>
        client.GetHistoryAsync(request, task, task is null ? 25 : 100, token);
    public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token) =>
        client.GetTerminalReadbackAsync(request, task, token);
}

public sealed record EventFeedEntry(string Identity, string TaskId, DateTimeOffset Timestamp,
    string Message, bool Terminal, bool Warning, bool Verified)
{
    public string DisplayText => "Task " + TaskId + ": " + Message;
}
internal sealed record EventFeedView(EventFeedEntry[] Entries, string Status);

/// <summary>One shell-owned read-only consumer; event identities trigger independent evidence readback.</summary>
internal sealed class EventFeedController(IEventFeedClient client, TimeSpan? pollInterval = null)
{
    private readonly object _gate = new();
    private readonly List<EventFeedEntry> _entries = [];
    private readonly Dictionary<string, Observation> _known = new();
    private readonly Queue<string> _knownOrder = new();
    private CoreEventCursor _cursor = new();
    private string _status = "Live activity is not connected.";
    private int _running, _polling, _refreshOffset;
    internal event Action<EventFeedView>? Changed;
    internal event Action<EventFeedEntry>? Notice;
    internal EventFeedView View { get { lock (_gate) return new(_entries.ToArray(), _status); } }
    private static string Id() => Guid.NewGuid().ToString("D");
    private sealed record Observation(string Fingerprint, EventFeedEntry Entry, string RequestId,
        string BaseIdentity, int ReadsRemaining, bool NotifyTransitions);

    internal async Task RunAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _running, 1) != 0) throw new InvalidOperationException("Activity consumer is already owned.");
        try
        {
            while (!token.IsCancellationRequested)
            {
                bool failed = false;
                try { await PollOnceAsync(token); }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch (Exception error)
                {
                    // A malformed/gapped stream needs a new snapshot. Transport/readback
                    // failure retains the cursor, so its entire batch can be retried.
                    if (error is JsonException) _cursor = new();
                    lock (_gate) _status = "Activity connection unavailable. Saved entries may be stale.";
                    Changed?.Invoke(View); failed = true;
                }
                await Task.Delay(failed ? TimeSpan.FromSeconds(1) : pollInterval ?? TimeSpan.FromMilliseconds(250), token);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        finally { Interlocked.Exchange(ref _running, 0); }
    }

    // Serialized also for deterministic fixture checks. Never commit a cursor
    // before all of that batch's independent material readbacks have succeeded.
    internal async Task PollOnceAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _polling, 1) != 0) throw new InvalidOperationException("Activity poll already in progress.");
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(token);
        budget.CancelAfter(TimeSpan.FromSeconds(30));
        try
        {
            token = budget.Token;
            var reply = await client.EventsAsync(Id(), _cursor.StreamId, _cursor.Sequence, token);
            if (!reply.IsSuccess) throw new IOException("Activity readback unavailable.");
            var batch = reply.Response!;
            var stagedCursor = _cursor.Fork();
            var fresh = stagedCursor.Apply(batch);
            var observations = new List<Observation>();
            if (batch.ResetRequired)
            {
                var history = await client.HistoryAsync(Id(), null, token);
                if (!history.IsSuccess) throw new IOException("Activity snapshot unavailable.");
                foreach (var task in history.Response!.Tasks.Reverse())
                    observations.Add(await ObserveAsync(task.TaskId, task.RequestId, batch.StreamId + "/snapshot/" + task.TaskId,
                        DateTimeOffset.Parse(task.CompletedAt ?? task.CreatedAt), token, notify: false));
                stagedCursor.SnapshotRead();
            }
            else
            {
                foreach (var group in fresh.GroupBy(item => item.TaskId).OrderBy(group => group.Last().Sequence))
                {
                    var history = await client.HistoryAsync(Id(), group.Key, token);
                    if (!history.IsSuccess || history.Response!.Tasks is not { Length: 1 })
                        throw new IOException("Task evidence unavailable.");
                    var task = history.Response.Tasks[0];
                    if (task.TaskId != group.Key || group.Any(item => item.RequestId is not null && item.RequestId != task.RequestId))
                        throw new JsonException("Event and task identities differ.");
                    var last = group.Last();
                    observations.Add(await ObserveAsync(task.TaskId, task.RequestId, batch.StreamId + "/" + last.Sequence,
                        DateTimeOffset.Parse(last.OccurredAt), token));
                }
                // Ledger commits can precede terminal-ready/cached verification.
                // Recheck active observations and give settled-but-unverified success
                // three extra reads; no endless refresh of historical completions.
                Observation[] settling;
                lock (_gate)
                {
                    var eligible = _known.Values.Where(item => item.ReadsRemaining != 0 &&
                        observations.All(next => next.Entry.TaskId != item.Entry.TaskId)).ToArray();
                    int start = _refreshOffset % Math.Max(1, eligible.Length);
                    settling = eligible.Skip(start).Concat(eligible.Take(start)).Take(25 - observations.Count).ToArray();
                    _refreshOffset = (start + settling.Length) % Math.Max(1, eligible.Length);
                }
                foreach (var item in settling)
                    observations.Add(await ObserveAsync(item.Entry.TaskId, item.RequestId, item.BaseIdentity,
                        item.Entry.Timestamp, token, item.ReadsRemaining < 0 ? 3 : item.ReadsRemaining - 1, item.NotifyTransitions));
            }
            token.ThrowIfCancellationRequested();
            var notices = new List<EventFeedEntry>();
            bool changed;
            lock (_gate)
            {
                changed = batch.ResetRequired || _status != "Live activity connected.";
                if (batch.ResetRequired) { _entries.Clear(); _known.Clear(); _knownOrder.Clear(); }
                foreach (var item in observations)
                {
                    var entry = item.Entry;
                    _known.TryGetValue(entry.TaskId, out var previous);
                    if (previous?.Fingerprint == item.Fingerprint) { _known[entry.TaskId] = item; continue; }
                    changed = true;
                    if (!batch.ResetRequired && item.NotifyTransitions && entry.Terminal &&
                        (previous is not null && (!previous.Entry.Terminal || previous.Entry.Verified != entry.Verified ||
                            previous.Entry.Warning != entry.Warning || previous.Entry.Message != entry.Message) ||
                         previous is null && fresh.Any(e => e.TaskId == entry.TaskId && e.Kind == "task_recorded")))
                        notices.Add(entry);
                    if (!_known.ContainsKey(entry.TaskId))
                    {
                        if (_known.Count == 512) _known.Remove(_knownOrder.Dequeue());
                        _knownOrder.Enqueue(entry.TaskId);
                    }
                    _known[entry.TaskId] = item;
                    if (_entries.Count == 200) _entries.RemoveAt(0);
                    _entries.Add(entry);
                }
                _cursor = stagedCursor;
                _status = "Live activity connected.";
            }
            if (changed) Changed?.Invoke(View);
            foreach (var entry in notices) Notice?.Invoke(entry);
        }
        finally { Interlocked.Exchange(ref _polling, 0); }
    }

    private async Task<Observation> ObserveAsync(string taskId, string requestId, string identity,
        DateTimeOffset timestamp, CancellationToken token, int retries = 3, bool notify = true)
    {
        var response = await client.ReadAsync(requestId, taskId, token);
        if (!response.IsSuccess) throw new IOException("Task outcome unavailable.");
        var result = response.Response!;
        if (result.RequestId != requestId || result.TaskId != taskId) throw new JsonException("Task outcome identity differs.");
        bool terminal = result.Terminal && result.TerminalPersisted == true;
        bool verified = terminal && result.FinalState == "SUCCEEDED" && result.CompletionVerified && !result.HasResidual;
        bool warning = result.HasResidual || result.FinalState == "STOPPED_WITH_RESIDUAL" || terminal && (result.FinalState == "FAILED" || result.FinalState == "ABORTED_BY_CRASH");
        string message = !terminal ? "Execution or cleanup is pending; its saved outcome is not confirmed."
            : result.HasResidual || result.FinalState == "STOPPED_WITH_RESIDUAL" ? "Task ended with remaining effects. Check activity."
            : verified ? "Task completed and verified."
            : result.FinalState == "SUCCEEDED" ? "Task completion is saved; detailed verification is unavailable."
            : result.FinalState == "STOPPED" ? "Task stopped. Its terminal outcome is saved."
            : "Task did not complete successfully. Check activity.";
        string fingerprint = string.Join("/", result.FinalState, result.Terminal, result.TerminalPersisted,
            result.CompletionVerified, result.HasResidual, result.Route);
        // No command, transcript, arguments, result/error body or server prose
        // enters transient display state, notices or logs in this packet.
        return new(fingerprint, new(identity + "/" + fingerprint, taskId, timestamp, message, terminal, warning, verified),
            requestId, identity, !terminal ? -1 : result.FinalState == "SUCCEEDED" && !verified ? retries : 0, notify);
    }
}
