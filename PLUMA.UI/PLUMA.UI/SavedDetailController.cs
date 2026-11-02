using System;
using System.Linq;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

public sealed class SavedActionRow
{
    internal CoreRequestProtocol.SavedAction Original { get; }
    internal SavedActionRow(CoreRequestProtocol.SavedAction original) => Original = original;
    public string Heading => $"Action {Original.ActionId}: {PopupText.Label(Original.Tool)}";
    private static string Time(string? value) => value is null ? "Unavailable" :
        DateTimeOffset.Parse(value, CultureInfo.InvariantCulture).ToLocalTime().ToString("g",CultureInfo.CurrentCulture);
    public string Facts => $"Step {Original.StepIndex+1} ? Risk: {PopupText.Label(Original.Risk)} · Approval: {PopupText.Label(Original.Approval ?? "Unavailable")}\n" +
        $"Adapter: {PopupText.Label(Original.Adapter ?? "Unavailable")} · Duration: {(Original.DurationMs is double ms ? ms.ToString("N0") + " ms" : "Unavailable")}\n" +
        $"Started: {Time(Original.StartedAt)} · Ended: {Time(Original.EndedAt)}\n" +
        $"Verification: {(Original.VerificationMethod is null ? "Evidence unavailable" : Original.Verified ? "Verified" : "Not verified")}\n" +
        (Original.VerificationMethod is null ? "" : PopupText.Label(Original.VerificationMethod) + ": " + Original.VerificationDetail + "\n") +
        (Original.FactualMessage ?? "No executor message recorded.") + "\n" +
        (Original.PolicyReason is null ? "" : "Policy: " + Original.PolicyReason + "\n") +
        (Original.ErrorCode is null ? "" : "Error: " + PopupText.Label(Original.ErrorCode) + "\n") +
        (Original.EffectState is null ? "" : "Non-undoable effect: " + PopupText.Label(Original.EffectState) + "\n") +
        $"Undo evidence reference: action {Original.ActionId}\n" +
        $"Undo: {(Original.Selection is not null ? "Available with confirmation" : Original.ClaimState is not null ? PopupText.Label(Original.ClaimState) : Original.UndoAvailable ? "Unavailable or later actions remain" : "No available inverse")}\n" +
        $"Rollback: {(!Original.RollbackAttempted ? "Not attempted" : Original.RollbackOk is true ? "Verified" : "Unverified; retained for manual resolution")}" +
        (Original.RollbackCode is null ? "" : "\nRollback result: " + PopupText.Label(Original.RollbackCode));
    public string Arguments => Original.Arguments;
}

internal sealed record SavedDetailView(string? TaskId, string? RequestId, SavedActionRow[] Actions,
    string Context, string Status, bool Busy, bool HasMore, long Cursor);

/// <summary>One cancellable saved-detail reader, shared across native navigation.</summary>
internal sealed class SavedDetailController(CoreIpcClient client) : IAsyncDisposable
{
    private readonly CancellationTokenSource _lifetime = new();
    private Task _work = Task.CompletedTask;
    private bool _closed;
    internal SavedDetailView View { get; private set; } = new(null, null, [], "", "Select a saved task.", false, false, 0);
    internal event Action<SavedDetailView>? Changed;
    internal Task ReadAsync(string task, long after = 0)
    {
        if (_closed || !_work.IsCompleted) return _work;
        View = new(task, null, [], "", "Reading saved detail...", true, false, after);
        Changed?.Invoke(View);
        return _work = LoadAsync(task, after);
    }
    private async Task LoadAsync(string task, long after)
    {
        await Task.Yield();
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
        budget.CancelAfter(TimeSpan.FromSeconds(3));
        try
        {
            string request = Guid.NewGuid().ToString("D");
            var reply = await client.GetTaskDetailAsync(request, task, after, budget.Token);
            for (int retry = 0; reply.Failure == CoreConnectionFailure.Busy && retry < 2; retry++)
            { await Task.Delay(50, budget.Token); reply = await client.GetTaskDetailAsync(request, task, after, budget.Token); }
            budget.Token.ThrowIfCancellationRequested();
            if (!reply.IsSuccess) throw new InvalidOperationException();
            var saved = reply.Response!;
            View = new(task, saved.TaskRequestId, saved.Actions.Select(a => new SavedActionRow(a)).ToArray(),
                "Original voice input: " + (saved.OriginalTranscript ?? "Unavailable or not voice input") + "\n" +
                "App: " + (saved.ActiveProcess ?? "Unavailable") + "\nWindow: " + (saved.ActiveWindow ?? "Unavailable") + "\n" +
                "Cleanup: " + (saved.CleanupComplete is null ? "Evidence unavailable" : saved.CleanupComplete is true ? "Verified" : $"Unresolved entries: {saved.CleanupUnresolved}") + (saved.ResidualCodes.Length == 0 ? "" : "\nResidual: " + string.Join(", ", saved.ResidualCodes.Select(code => PopupText.Label(code)))),
                "Saved detail for task " + task + ". Irreversible commits have no inverse.", false, saved.HasMore, saved.NextActionId);
        }
        catch (Exception) { View = new(task, null, [], "", "Saved detail is unavailable. Select the task to retry.", false, false, 0); }
        if (!_closed) Changed?.Invoke(View);
    }
    public async ValueTask DisposeAsync()
    {
        if (_closed) return;
        _closed = true; _lifetime.Cancel(); await _work; _lifetime.Dispose();
    }
}
