using System.Text.Json;
using PLUMA.UI;

internal static class CommandControllerChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static CoreRequestResult<T> Ok<T>(T response) where T : class => new(response, CoreConnectionFailure.None, false, null, null);
    private static TaskCompletionSource<T> Source<T>() => new(TaskCreationOptions.RunContinuationsAsynchronously);
    private static CoreRequestProtocol.TerminalReadback Terminal(string request, string task, string state = "SUCCEEDED",
        bool verified = true, bool residual = false, bool persisted = true) => new(1, "terminal_readback", request, task,
            true, state, verified, persisted, residual, "FAST", "Fixture result", 1);

    internal static async Task RunAsync(Action<bool, string> check)
    {
        var client = new Client();
        await using (var owner = new CommandController(client, TimeSpan.FromMilliseconds(5)))
        {
            await owner.SubmitAsync("No connection");
            check(client.Submissions == 0 && !owner.View.CanSubmit, "command admission requires a verified connection");
            owner.SetConnected(true);
            foreach (string text in new[] { "", "  ", new string('x', 4097) }) await owner.SubmitAsync(text);
            check(client.Submissions == 0 && owner.View.CanSubmit, "empty and oversized command input cannot reach IPC");
            var finish = Source<CoreRequestResult<CoreRequestProtocol.TerminalReadback>>();
            var entered = Source<bool>();
            client.Read = (request, task, token) => { entered.TrySetResult(true); return finish.Task.WaitAsync(token); };
            Task run = owner.SubmitAsync("fixture request");
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            await owner.SubmitAsync("duplicate");
            check(client.Submissions == 1 && owner.View.Pending && !owner.View.CanSubmit && owner.View.State == "Accepted",
                "one submission owns one request/task and acknowledgement never implies success");
            Task stop = owner.StopAsync();
            await stop.WaitAsync(TimeSpan.FromSeconds(1));
            check(client.Stops == 1 && client.Fence == owner.View.RequestId && owner.View.Pending && owner.View.StopMessage!.Contains("Cleanup may still"),
                "priority STOP returns independently of a blocked result and does not claim cleanup completion");
            finish.SetResult(Ok(Terminal(owner.View.RequestId!, owner.View.TaskId!, "STOPPED", false)));
            await run.WaitAsync(TimeSpan.FromSeconds(2));
            check(owner.View.State == "Stopped" && owner.View.CanSubmit, "saved STOP terminal readback closes the command without success");
        }

        foreach (var scenario in new[] { ("SUCCEEDED", true, false, true, "Completed"),
            ("SUCCEEDED", false, false, true, "Unverified"), ("FAILED", false, false, true, "Failed"),
            ("ABORTED_BY_CRASH", false, false, true, "Failed"), ("STOPPED_WITH_RESIDUAL", false, true, true, "Remaining effects"),
            ("SUCCEEDED", true, false, false, "Unverified") })
        {
            var source = new Client { Read = (request, task, token) => Task.FromResult(Ok(Terminal(request, task,
                scenario.Item1, scenario.Item2, scenario.Item3, scenario.Item4))) };
            await using var owner = new CommandController(source);
            owner.SetConnected(true); await owner.SubmitAsync("fixture result");
            check(owner.View.State == scenario.Item5 && owner.View.Pending == !scenario.Item4 &&
                !owner.View.Message.Contains('_') && !owner.View.Message.Contains('—'),
                "terminal UI is factual about verification, persistence, failure and residuals: " + scenario.Item1 + "/" + scenario.Item2 + "/" + scenario.Item4);
        }

        foreach (bool discoverImmediately in new[] { true, false })
        {
            var source = new Client { Unknown = true, HasHistory = discoverImmediately };
            await using var owner = new CommandController(source);
            owner.SetConnected(true); await owner.SubmitAsync("uncertain request");
            if (!discoverImmediately)
            {
                check(owner.View.Pending && !owner.View.CanSubmit && source.Submissions == 1,
                    "missing history after uncertain write remains unresolved and cannot be resubmitted");
                source.HasHistory = true;
                await owner.ReconcileAsync();
            }
            check(owner.View.State == "Completed" && source.Submissions == 1 && owner.View.TaskId == source.TaskId &&
                source.ReadRequests.All(request => request == owner.View.RequestId),
                "uncertain admission/reconnect resolves exact request identity through history without replay: " + discoverImmediately);
        }

        {
            var source = new Client { Read = (request, task, token) => Task.FromResult(
                CoreRequestResult<CoreRequestProtocol.TerminalReadback>.Failed(CoreConnectionFailure.Unavailable)) };
            await using var owner = new CommandController(source);
            owner.SetConnected(true); await owner.SubmitAsync("disconnect after admission");
            string? requestId = owner.View.RequestId, taskId = owner.View.TaskId;
            check(owner.View.Pending && !owner.View.CanSubmit, "disconnect after admission preserves unresolved ownership");
            source.Read = (request, task, token) => Task.FromResult(Ok(Terminal(request, task)));
            await owner.ReconcileAsync();
            check(owner.View.State == "Completed" && source.Submissions == 1 && owner.View.RequestId == requestId && owner.View.TaskId == taskId,
                "reconnect reads the original task instead of submitting a replacement");
        }

        {
            var entered = Source<bool>();
            bool cancelled = false;
            var source = new Client { Read = async (request, task, token) =>
            {
                entered.TrySetResult(true);
                try { await Task.Delay(Timeout.Infinite, token); }
                catch (OperationCanceledException) { cancelled = true; throw; }
                throw new InvalidOperationException();
            }};
            var owner = new CommandController(source);
            owner.SetConnected(true); Task run = owner.SubmitAsync("owner close");
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(2));
            Task first = owner.DisposeAsync().AsTask(), second = owner.DisposeAsync().AsTask();
            await Task.WhenAll(first, second).WaitAsync(TimeSpan.FromSeconds(2));
            await owner.SubmitAsync("after close");
            check(cancelled && run.IsCompleted && source.Submissions == 1 && !owner.View.CanSubmit && source.Stops == 0,
                "window close drains observations idempotently without silently issuing global STOP or replaying work");
        }

        {
            var source = new Client { Reject = true };
            await using var owner = new CommandController(source);
            owner.SetConnected(true); await owner.SubmitAsync("refused request");
            check(owner.View.State == "Not accepted" && !owner.View.Pending && source.ReadRequests.Count == 0,
                "denied admission never turns into an executing task or a fabricated result");
        }

        {
            var transportEntered = Source<bool>();
            var releaseTransport = Source<bool>();
            var presentationEntered = Source<bool>();
            using var releasePresentation = new ManualResetEventSlim();
            var source = new Client { BeforeStop = async token =>
            { transportEntered.TrySetResult(true); await releaseTransport.Task.WaitAsync(token); } };
            await using var owner = new CommandController(source);
            owner.Changed += view =>
            {
                if (view.StopPending) { presentationEntered.TrySetResult(true); releasePresentation.Wait(TimeSpan.FromSeconds(3)); }
            };
            Task call = Task.Run(async () => await owner.StopAsync());
            try
            {
                await presentationEntered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                await transportEntered.Task.WaitAsync(TimeSpan.FromSeconds(2));
                check(!releasePresentation.IsSet && source.Stops == 1,
                    "owned priority STOP reaches transport while cancellation presentation is deliberately blocked");
            }
            finally { releasePresentation.Set(); releaseTransport.TrySetResult(true); }
            await call.WaitAsync(TimeSpan.FromSeconds(2));
        }
    }

    internal static async Task RunNativeAsync(CoreIpcClient core, Action<bool, string> check)
    {
        string queued = Id();
        var stopped = await core.StopAsync(Id(), null, default, queued);
        var refused = await core.SubmitTextAsync(queued, "fixture:approval", default);
        check(stopped.IsSuccess && refused.Response is { Accepted: false, ErrorCode: "SUBMISSION_STOPPED" },
            "actual Python/C# STOP fences an unknown queued submission before it can create a task or executor");
    }

    private sealed class Client : ICommandClient
    {
        internal int Submissions, Stops;
        internal bool Unknown, Reject, HasHistory = true;
        internal string TaskId = Id();
        internal string? RequestId;
        internal string? Fence;
        internal Func<CancellationToken, Task>? BeforeStop;
        internal readonly List<string> ReadRequests = [];
        internal Func<string, string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>>> Read =
            (request, task, token) => Task.FromResult(Ok(Terminal(request, task)));
        public Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request, string text, CancellationToken token)
        {
            Submissions++; RequestId = request;
            return Task.FromResult(Unknown ? CoreRequestResult<CoreRequestProtocol.SubmissionAck>.Failed(CoreConnectionFailure.Timeout, true)
                : Ok(new CoreRequestProtocol.SubmissionAck(1, "submission_ack", request, !Reject, Reject ? null : TaskId,
                    Reject ? "DENIED" : null, "Fixture acknowledgement")));
        }
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token)
        { ReadRequests.Add(request); return Read(request, task, token); }
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, CancellationToken token) =>
            Task.FromResult(Ok(new CoreRequestProtocol.HistoryReply(1, "history_reply", request, null,
                HasHistory ? [new(TaskId, RequestId!, "text", "Fixture", DateTimeOffset.UtcNow.ToString("O"), null, null, null, null, null, null)] : [], [])));
        public async Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request, string? submissionRequest, CancellationToken token)
        {
            Stops++;
            Fence = submissionRequest;
            if (BeforeStop != null) await BeforeStop(token);
            return Ok(new CoreRequestProtocol.StopAck(1, "stop_ack", request, "ok", "pluma.stop.v1", "Latch acknowledged",
                null, [], [], 0, 1));
        }
    }
}
