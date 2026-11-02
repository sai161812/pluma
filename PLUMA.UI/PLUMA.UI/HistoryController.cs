using System;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

public sealed class HistoryRow
{
    internal CoreRequestProtocol.SavedHistoryTask Original { get; }
    public string TaskId => Original.TaskId;
    public string CommandText => Original.CommandText ?? "Command unavailable";
    public string StateText => "Saved: " + (Original.FinalState is null ? "Outcome unavailable" : PopupText.Label(Original.FinalState));
    public string TimestampText => Time(Original.CreatedAt);
    private static string Time(string? value) => value is null ? "Unavailable" :
        DateTimeOffset.Parse(value, CultureInfo.InvariantCulture).ToLocalTime().ToString("g", CultureInfo.CurrentCulture);
    public string MetadataText => $"Input: {PopupText.Label(Original.InputMode)}  ·  Route: {PopupText.Label(Original.Route ?? "Unavailable")}\n" +
        $"Started: {Time(Original.StartedAt)}  ·  Completed: {Time(Original.CompletedAt)}" +
        (Original.StopReason is null ? "" : "\nSTOP: " + PopupText.Label(Original.StopReason)) +
        (Original.ErrorCode is null ? "" : "\nError: " + PopupText.Label(Original.ErrorCode));
    internal HistoryRow(CoreRequestProtocol.SavedHistoryTask original) => Original = original;
}

internal sealed record HistoryView(HistoryRow[] Rows, string Search, string? NextCursor,
    bool HasMore, bool Busy, bool Connected, string Message);

/// <summary>One shell-owned read. A page replaces its predecessor; memory stays bounded.</summary>
internal sealed class HistoryController(Func<CoreRequestProtocol.HistoryPageRequest, CancellationToken,
    Task<CoreRequestResult<CoreRequestProtocol.HistoryPageReply>>> read) : IAsyncDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenSource _lifetime = new();
    private Task _work = Task.CompletedTask;
    private bool _closed;
    internal HistoryView View { get; private set; } = new([], "", null, false, false, false, "Refresh to read saved history.");
    internal event Action<HistoryView>? Changed;
    internal Task RefreshAsync(string search, CancellationToken token) => Start(search, null, token);
    internal Task OlderAsync(CancellationToken token)
    {
        lock (_gate)
            return !View.HasMore || !View.Connected ? Task.CompletedTask : Start(View.Search, View.NextCursor, token);
    }
    private Task Start(string search, string? before, CancellationToken token)
    {
        lock (_gate)
        {
            if (_closed || View.Busy || !_work.IsCompleted) return Task.CompletedTask;
            var prior = View;
            View = new([], search, null, false, true, false, "Reading saved history...");
            Changed?.Invoke(View);
            _work = LoadAsync(search, before, prior, token);
            return _work;
        }
    }
    private async Task LoadAsync(string search, string? before, HistoryView prior, CancellationToken token)
    {
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(token, _lifetime.Token);
        budget.CancelAfter(TimeSpan.FromSeconds(3));
        HistoryView result;
        try
        {
            var query = new CoreRequestProtocol.HistoryPageRequest(Guid.NewGuid().ToString("D"), search, before);
            var reply = await read(query, budget.Token);
            for (int retry = 0; reply.Failure == CoreConnectionFailure.Busy && retry < 2; retry++)
            {
                // Read-only retry within the same owned budget; never resubmit
                // a command or advance a cursor without a validated response.
                await Task.Delay(50, budget.Token);
                reply = await read(query, budget.Token);
            }
            budget.Token.ThrowIfCancellationRequested();
            if (!reply.IsSuccess) throw new InvalidOperationException("Saved history is unavailable.");
            var page = reply.Response!;
            if (page.RequestId != query.RequestId || page.BeforeTaskId != before || page.Tasks.Length > query.Limit ||
                before is not null && prior.Rows.Length > 0 && page.Tasks.Length > 0 &&
                CoreRequestProtocol.CompareHistory(prior.Rows[^1].Original, page.Tasks[0]) <= 0)
                throw new InvalidOperationException("Saved history scope changed.");
            var rows = Array.ConvertAll(page.Tasks, task => new HistoryRow(task));
            result = new(rows, search, page.NextBeforeTaskId, page.HasMore, false, true,
                rows.Length == 0 ? (search.Length == 0 ? "No saved tasks." : "No matching saved tasks.") :
                $"Showing {rows.Length} saved tasks." + (page.HasMore ? " Older records are available." : ""));
        }
        catch (Exception) { result = new([], search, null, false, false, false, "Saved history is unavailable. Refresh to try again."); }
        lock (_gate)
        {
            if (_closed) return;
            View = result;
        }
        Changed?.Invoke(result);
    }
    public async ValueTask DisposeAsync()
    {
        Task pending;
        lock (_gate) { if (_closed) return; _closed = true; _lifetime.Cancel(); pending = _work; }
        await pending;
        _lifetime.Dispose();
    }
}
