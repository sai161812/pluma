using System.Diagnostics;
using System.Text.Json;
using PLUMA.UI;

internal static class ConfirmationControllerChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static CoreRequestProtocol.ConfirmationView View(double expires = 3) => new(Id(), Id(), new string('a', 64),
        "fixture_read", "HIGH", JsonDocument.Parse("{\"path\":\"budget_2026.md\"}").RootElement.Clone(),
        "Read this exact owned file?", "Owned fixture", DateTimeOffset.UtcNow.AddSeconds(expires).ToString("O"));

    internal static async Task RunAsync(Action<bool, string> check)
    {
        string raw = "{\"file_path\":\"C:\\\\owned\\\\预算_2026—final.md\",\"text\":\"a  b\"}";
        string formatted = ConfirmationPresentation.Arguments(raw);
        check(formatted.Contains("预算_2026—final.md") && formatted.Contains("a  b") && formatted.Contains("file path:"),
            "approval display formats keys while preserving literal Unicode filenames and argument whitespace");
        foreach (string scenario in new[] { "approve", "deny", "stop", "changed", "expiry", "disconnect", "close", "uncertain", "fault" })
        {
            var source = new Client { Pending = View(scenario == "expiry" ? 0.15 : 3), Uncertain = scenario == "uncertain" };
            var presenter = new Presenter();
            var owner = new ConfirmationController(source, presenter, TimeSpan.FromMilliseconds(10));
            using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            Task run = owner.RunAsync(lifetime.Token);
            await presenter.Shown.Task.WaitAsync(TimeSpan.FromSeconds(1));
            string originalClient = owner.ClientId;
            if (scenario is "approve" or "uncertain") presenter.Decision.TrySetResult(true);
            else if (scenario == "deny") presenter.Decision.TrySetResult(false);
            else if (scenario == "stop") source.Pending = null;
            else if (scenario == "changed") source.Pending = source.Pending! with { Prompt = "A different operation" };
            else if (scenario == "disconnect") source.Unavailable = true;
            else if (scenario == "fault") presenter.Decision.TrySetException(new InvalidOperationException("fixture-only fault"));
            else if (scenario == "close") lifetime.Cancel();
            if (scenario is "approve" or "deny" or "uncertain")
                await Until(() => source.Decisions.Count == 1);
            else if (scenario is "stop" or "changed" or "expiry" or "disconnect")
                await Until(() => presenter.Cancelled);
            else if (scenario == "fault") await Until(() => owner.LastFailure is not null);
            await Task.Delay(35);
            lifetime.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(2));
            bool expected = scenario is "approve" or "deny" or "uncertain";
            check(source.Decisions.Count == (expected ? 1 : 0) && presenter.Count == 1 && source.Disconnections > 0,
                "window approval owner has one dialog, no stale/duplicate decision and owned cleanup: " + scenario);
            if (expected)
            {
                var actual = source.Decisions.Single();
                check(actual.TaskId == presenter.View!.TaskId && actual.ConfirmationId == presenter.View.ConfirmationId &&
                    actual.Binding == presenter.View.Binding && actual.Approved == (scenario != "deny"),
                    "decision uses the exact displayed task/call/binding: " + scenario);
            }
            if (scenario == "disconnect") check(originalClient != owner.ClientId, "reconnect uses a new logical approval client identity");
        }
    }

    internal static async Task RunNativeAsync(CoreIpcClient client, Action<bool, string> check)
    {
        foreach (bool stop in new[] { false, true })
        {
            var presenter = new Presenter();
            var owner = new ConfirmationController(new CoreConfirmationClient(client), presenter, TimeSpan.FromMilliseconds(10));
            using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            Task run = owner.RunAsync(lifetime.Token);
            try
            {
                var lease = await client.GetConfirmationsAsync(Id(), owner.ClientId, default);
                if (!lease.IsSuccess) throw new Exception("Native approval lease unavailable.");
                var submission = await client.SubmitTextAsync(Id(), "fixture:approval", default);
                if (submission.Response is not { Accepted: true }) throw new Exception("Native fixture was not admitted.");
                await presenter.Shown.Task.WaitAsync(TimeSpan.FromSeconds(2));
                if (stop)
                {
                    await client.StopAsync(Id(), submission.Response.TaskId, default);
                    await Until(() => presenter.Cancelled);
                }
                else presenter.Decision.TrySetResult(true);
                CoreRequestProtocol.TerminalReadback? terminal = null;
                await Until(async () =>
                {
                    terminal = (await client.GetTerminalReadbackAsync(submission.Response.RequestId, submission.Response.TaskId!, default)).Response;
                    return terminal?.Terminal == true;
                });
                var history = await client.GetHistoryAsync(Id(), submission.Response.TaskId, 100, default);
                check(history.IsSuccess && terminal!.TerminalPersisted == true &&
                    (stop ? !terminal.CompletionVerified && history.Response!.Actions.All(a => !a.Verified)
                          : terminal.CompletionVerified && history.Response!.Actions.Any(a => a.Verified && a.ApprovalState == "ALLOW")),
                    "window controller over native IPC has factual policy/verification/ledger and STOP outcome: " + (stop ? "stop" : "approve"));
            }
            finally { lifetime.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(3)); }
        }
    }

    private static Task Until(Func<bool> condition) => Until(() => Task.FromResult(condition()));
    private static async Task Until(Func<Task<bool>> condition)
    {
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < TimeSpan.FromSeconds(2))
        {
            if (await condition()) return;
            await Task.Delay(5);
        }
        throw new TimeoutException("Owned approval fixture condition did not become true.");
    }

    private sealed class Presenter : IConfirmationPresenter
    {
        internal readonly TaskCompletionSource Shown = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal readonly TaskCompletionSource<bool?> Decision = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal CoreRequestProtocol.ConfirmationView? View;
        internal int Count;
        internal volatile bool Cancelled;
        public async Task<bool?> ShowAsync(CoreRequestProtocol.ConfirmationView view, CancellationToken token)
        {
            View = view; Count++; Shown.TrySetResult();
            try { return await Decision.Task.WaitAsync(token); }
            catch (OperationCanceledException) { Cancelled = true; return null; }
        }
    }

    private sealed class Client : IConfirmationClient
    {
        internal volatile CoreRequestProtocol.ConfirmationView? Pending;
        internal volatile bool Unavailable, Uncertain;
        internal int Disconnections;
        internal readonly System.Collections.Concurrent.ConcurrentQueue<CoreRequestProtocol.ConfirmationDecisionRequest> Decisions = new();
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationList>> QueryAsync(string requestId, string clientId, CancellationToken token) =>
            Task.FromResult(Unavailable ? CoreRequestResult<CoreRequestProtocol.ConfirmationList>.Failed(CoreConnectionFailure.Unavailable)
                : new CoreRequestResult<CoreRequestProtocol.ConfirmationList>(new(1, "confirmation_list", requestId, clientId,
                    Pending is null ? [] : [Pending]), CoreConnectionFailure.None, false, null, null));
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationAck>> DecideAsync(CoreRequestProtocol.ConfirmationDecisionRequest request, CancellationToken token)
        {
            Decisions.Enqueue(request);
            return Task.FromResult(Uncertain ? CoreRequestResult<CoreRequestProtocol.ConfirmationAck>.Failed(CoreConnectionFailure.Timeout, true)
                : new CoreRequestResult<CoreRequestProtocol.ConfirmationAck>(new(1, "confirmation_ack", request.RequestId, request.ConfirmationId,
                    true, request.Approved, null), CoreConnectionFailure.None, false, null, null));
        }
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationDisconnected>> DisconnectAsync(string requestId, string clientId, CancellationToken token)
        {
            Disconnections++;
            return Task.FromResult(new CoreRequestResult<CoreRequestProtocol.ConfirmationDisconnected>(new(1, "confirmation_disconnected",
                requestId, clientId, 0), CoreConnectionFailure.None, false, null, null));
        }
    }
}
