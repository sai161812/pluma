using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal interface ICommandClient
{
    Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request, string text, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request, string? submissionRequest, CancellationToken token);
}

internal sealed class CoreCommandClient(CoreIpcClient client) : ICommandClient
{
    public async Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request, string text, CancellationToken token)
    {
        // A legacy status reply alone cannot establish that this core supports
        // fencing a not-yet-acknowledged submission. Probe read-only first.
        try
        {
            var capability = await client.GetSettingsAsync(Guid.NewGuid().ToString("D"), token);
            if (!capability.IsSuccess || capability.Response is not { SubmissionStopFence: true })
                return CoreRequestResult<CoreRequestProtocol.SubmissionAck>.Failed(CoreConnectionFailure.Protocol);
            token.ThrowIfCancellationRequested();
            return await client.SubmitTextAsync(request, text, token);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            // The transport returns OutcomeUnknown rather than throwing after
            // a submission write. This cancellation occurred before that write.
            return CoreRequestResult<CoreRequestProtocol.SubmissionAck>.Failed(CoreConnectionFailure.Timeout);
        }
    }
    public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token) =>
        client.GetTerminalReadbackAsync(request, task, token);
    public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, CancellationToken token) =>
        client.GetHistoryAsync(request, null, 100, token);
    public Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request, string? submissionRequest, CancellationToken token) =>
        client.StopAsync(request, null, token, submissionRequest);
}

internal sealed record CommandView(string? RequestId, string? TaskId, string State, string Message,
    string Route, bool CanSubmit, bool Pending, bool StopPending, string? StopMessage, DateTimeOffset? StopRequestedAt);

/// <summary>One shell-owned command. Admission is sent once; recovery only reads evidence.
/// STOP has a separate owned operation and cancels a not-yet-acknowledged submission first.</summary>
internal sealed class CommandController(ICommandClient client, TimeSpan? pollInterval = null) : IAsyncDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenSource _lifetime = new();
    private readonly TimeSpan _poll = pollInterval ?? TimeSpan.FromMilliseconds(250);
    private CancellationTokenSource? _submission;
    private Task _work = Task.CompletedTask, _stop = Task.CompletedTask;
    private Task? _disposal;
    private bool _closed, _connected, _pending, _stopPending;
    private string? _requestId, _taskId, _stopMessage;
    private DateTimeOffset? _stopRequestedAt;
    private string _state = "Idle", _message = "Enter a command.", _route = "Unavailable";
    internal event Action<CommandView>? Changed;
    internal CommandView View { get { lock (_gate) return Snapshot(); } }
    private static string Id() => Guid.NewGuid().ToString("D");
    private CommandView Snapshot() => new(_requestId, _taskId, _state, _message, _route,
        !_closed && _connected && !_pending && !_stopPending, _pending, _stopPending, _stopMessage, _stopRequestedAt);
    private void Publish() { CommandView view; lock (_gate) view = Snapshot(); Changed?.Invoke(view); }

    internal void SetConnected(bool connected)
    {
        lock (_gate)
        {
            if (_closed) return;
            _connected = connected;
            if (_requestId is null) _message = connected ? "Enter a command." : "Connect to PLUMA to enter a command.";
        }
        Publish();
    }

    internal Task SubmitAsync(string text)
    {
        lock (_gate)
        {
            if (!Snapshot().CanSubmit || !_work.IsCompleted) return Task.CompletedTask;
            if (string.IsNullOrWhiteSpace(text) || text.Length > 4096)
            { _message = "Enter between 1 and 4096 characters."; }
            else
            {
                _requestId = Id(); _taskId = null; _pending = true; _stopMessage = null;
                _state = "Submitting"; _message = "Sending the request. Execution is not yet confirmed."; _route = "Unavailable";
                _submission = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
                _work = SubmitAndObserveAsync(text, _requestId, _submission);
            }
        }
        Publish();
        lock (_gate) return _work;
    }

    private async Task SubmitAndObserveAsync(string text, string request, CancellationTokenSource submission)
    {
        await Task.Yield(); // Publish/own the operation before any client call, including synchronous fixtures.
        bool attempted = false;
        try
        {
            submission.Token.ThrowIfCancellationRequested();
            attempted = true;
            var result = await client.SubmitAsync(request, text, submission.Token);
            if (result.OutcomeUnknown)
            {
                Uncertain("The submission outcome is unknown. Checking saved task identity.");
            }
            else if (!result.IsSuccess || result.Response is not { Accepted: true })
            {
                lock (_gate)
                {
                    _pending = false; _state = "Not accepted";
                    _message = "The request was not accepted. Refresh the connection before trying again.";
                    if (!result.IsSuccess) _connected = false;
                }
                Publish(); return;
            }
            else
            {
                lock (_gate) { _taskId = result.Response.TaskId; _state = "Accepted"; _message = "Request accepted. Waiting for verified task results."; }
                Publish();
            }
            await ObserveAsync();
        }
        catch (OperationCanceledException) when (submission.IsCancellationRequested)
        {
            if (!attempted)
            {
                lock (_gate) { _pending = false; _state = "Not submitted"; _message = "The request was cancelled before submission."; }
                Publish();
            }
            else if (!_lifetime.IsCancellationRequested)
            {
                Uncertain("No task acknowledgement was received. Refresh to check saved task identity.");
                await ObserveSafelyAsync();
            }
        }
        catch (Exception) { Uncertain("Task state could not be confirmed. Refresh to check it without resubmitting."); }
        finally
        {
            lock (_gate) { if (ReferenceEquals(_submission, submission)) _submission = null; }
            submission.Dispose();
        }
    }

    internal Task ReconcileAsync()
    {
        lock (_gate)
        {
            if (_closed || !_pending || !_work.IsCompleted) return _work;
            _work = ObserveSafelyAsync();
            return _work;
        }
    }

    private async Task ObserveSafelyAsync()
    {
        await Task.Yield();
        try { await ObserveAsync(); }
        catch (OperationCanceledException) when (_lifetime.IsCancellationRequested) { }
        catch (Exception) { Uncertain("Task state could not be confirmed. Refresh to check it without resubmitting."); }
    }

    private async Task ObserveAsync()
    {
        string request; string? task;
        lock (_gate) { request = _requestId!; task = _taskId; }
        CancellationToken token = _lifetime.Token;
        token.ThrowIfCancellationRequested();
        if (task is null)
        {
            var history = await client.HistoryAsync(Id(), token);
            var matches = history.Response?.Tasks.Where(item => item.RequestId == request).ToArray();
            if (!history.IsSuccess || matches is not { Length: 1 })
            {
                Uncertain("No unique saved task was found. Do not repeat the command; refresh or check activity."); return;
            }
            task = matches[0].TaskId;
            lock (_gate) _taskId = task;
        }
        while (!token.IsCancellationRequested)
        {
            var result = await client.ReadAsync(request, task, token);
            if (!result.IsSuccess)
            { Uncertain("Task connection lost. Refresh to read its outcome without resubmitting."); return; }
            var actual = result.Response!;
            lock (_gate)
            {
                _connected = true;
                _route = actual.Route switch { "FAST" => "Fast", "SCREEN" => "Screen", "SMART" => "Smart", "DEEP" => "Deep", _ => "Unavailable" };
                if (!actual.Terminal)
                {
                    _state = actual.FinalState is "STOPPING" or "ROLLING_BACK" ? "Stopping" : "Running";
                    _message = "Execution or cleanup is in progress. Completion is not yet confirmed.";
                }
                else
                {
                    _pending = actual.TerminalPersisted != true;
                    if (_pending) { _state = "Unverified"; _message = "The task ended, but its saved outcome is not confirmed. Refresh to check it."; }
                    else if (actual.HasResidual || actual.FinalState == "STOPPED_WITH_RESIDUAL")
                    { _state = "Remaining effects"; _message = "The task ended with remaining effects. Check activity before further changes."; }
                    else if (actual.FinalState == "SUCCEEDED" && actual.CompletionVerified)
                    { _state = "Completed"; _message = "Task completed and verified."; }
                    else if (actual.FinalState == "SUCCEEDED")
                    { _state = "Unverified"; _message = "Saved task completion is available, but detailed verification is unavailable. Check activity."; }
                    else if (actual.FinalState == "STOPPED")
                    { _state = "Stopped"; _message = "The task stopped. Its terminal outcome is saved."; }
                    else { _state = "Failed"; _message = "The task did not complete successfully. Check activity for details."; }
                    if (!_pending && _stopMessage is not null && !_stopPending)
                        _stopMessage = actual.HasResidual || actual.FinalState == "STOPPED_WITH_RESIDUAL"
                            ? "Remaining effects are recorded. Check activity." : "The task terminal outcome is saved.";
                }
            }
            Publish();
            if (actual.Terminal) return;
            await Task.Delay(_poll, token);
        }
    }

    private void Uncertain(string message)
    {
        lock (_gate) { _connected = false; _state = "Unconfirmed"; _message = message; }
        Publish();
    }

    internal Task StopAsync()
    {
        lock (_gate)
        {
            if (_closed || !_stop.IsCompleted) return _stop;
            _stopPending = true; _stopMessage = "Sending STOP. Cleanup is not yet confirmed.";
            _stopRequestedAt = DateTimeOffset.UtcNow;
            // Cancel before the priority request can run: no queued UI submission may start afterward.
            _submission?.Cancel();
            string? submissionRequest = _pending ? _requestId : null;
            // The tracked priority operation must not wait for the UI dispatcher
            // to lay out/animate its cancellation feedback or an approval dialog.
            _stop = Task.Run(() => SendStopAsync(submissionRequest));
        }
        Publish();
        lock (_gate) return _stop;
    }

    private async Task SendStopAsync(string? submissionRequest)
    {
        await Task.Yield();
        try
        {
            var result = await client.StopAsync(Id(), submissionRequest, _lifetime.Token);
            lock (_gate) _stopMessage = !result.IsSuccess || result.Response!.Status != "ok"
                ? "STOP was not confirmed. Refresh and check task state."
                : result.Response.LatchAcknowledgedCount > 0
                    ? "STOP acknowledged. Cleanup may still be running."
                    : "No active task acknowledged STOP. Check task state.";
        }
        catch (Exception) { lock (_gate) _stopMessage = "STOP was not confirmed. Refresh and check task state."; }
        finally { lock (_gate) _stopPending = false; Publish(); }
        // Read-only reconciliation is safe; the side effect is never replayed.
        if (!_lifetime.IsCancellationRequested) _ = ReconcileAsync(); // tracked in _work; STOP never awaits task completion
    }

    public ValueTask DisposeAsync()
    {
        lock (_gate)
        {
            if (_disposal is null)
            {
                _closed = true; _connected = false; _lifetime.Cancel();
                _disposal = DrainAsync(_work, _stop);
            }
            return new(_disposal);
        }
    }

    private async Task DrainAsync(Task work, Task stop)
    {
        await Task.Yield();
        try { await Task.WhenAll(work, stop); }
        finally { Changed = null; _lifetime.Dispose(); }
    }
}
