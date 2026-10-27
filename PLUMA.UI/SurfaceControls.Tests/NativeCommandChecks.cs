using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml;

namespace PLUMA.UI.Tests;

internal static class NativeCommandChecks
{
    internal static async Task RunAsync(StackPanel root, Action<bool, string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("commands");
        await using var core = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        foreach (string scenario in new[] { "read", "fail", "denied", "hold", "planning", "residual", "lost-ack", "disconnect", "close" })
        {
            var bridge = new Bridge(core) { LoseAck = scenario == "lost-ack", LoseRead = scenario == "disconnect" };
            await using var controller = new CommandController(bridge, TimeSpan.FromMilliseconds(20));
            var page = new DashboardPage();
            page.AttachCommandController(controller);
            page.AttachCoreClient(core);
            root.Children.Clear(); root.Children.Add(page);
            var input = (AutoSuggestBox)page.FindName("CommandInput");
            var run = (Button)page.FindName("CommandRunButton");
            var stop = (Button)page.FindName("CommandStopButton");
            await Until(() => run.IsEnabled && input.IsEnabled && page.IsLoaded);
            input.Text = "fixture:" + (scenario is "lost-ack" or "disconnect" ? "read" : scenario == "close" ? "hold" : scenario);
            Invoke(run);
            check(!run.IsEnabled && !input.IsEnabled && stop.IsEnabled,
                "actual native Run reserves admission once while independent Stop remains available: " + scenario);
            if (scenario is "hold" or "residual" or "planning" or "close")
            {
                await fixture.WaitForEventAsync(scenario == "planning" ? "PLANNING_ENTERED" : "COMMAND_ENTERED");
                check(controller.View.Pending && controller.View.TaskId != null &&
                    ((TextBlock)page.FindName("CommandIdentityText")).Text.Contains(controller.View.TaskId),
                    "native pending view retains actual request/task identity: " + scenario);
                if (scenario == "close")
                {
                    root.Children.Remove(page);
                    var closing = new Window { Title = "PLUMA owned command close check", Content = page };
                    var drained = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                    closing.Closed += async (_, _) => { await controller.DisposeAsync(); drained.TrySetResult(); };
                    closing.Activate(); closing.Close();
                    await drained.Task.WaitAsync(TimeSpan.FromSeconds(3));
                    var active = await core.GetTerminalReadbackAsync(controller.View.RequestId!, controller.View.TaskId!, default);
                    check(active.Response is { Terminal: false } && bridge.Stops == 0,
                        "actual native window close drains its UI observation without pretending backend cancellation");
                    await core.StopAsync(Guid.NewGuid().ToString("D"), controller.View.TaskId, default);
                    await Until(async () => (await core.GetTerminalReadbackAsync(controller.View.RequestId!, controller.View.TaskId!, default)).Response is { Terminal: true });
                    continue;
                }
                Invoke(stop);
            }
            if (scenario == "disconnect")
            {
                await Until(() => controller.View.State == "Unconfirmed");
                check(!run.IsEnabled && controller.View.Pending, "native disconnected task cannot be duplicated");
                Invoke((Button)page.FindName("CoreRefreshButton"));
            }
            await Until(() => !controller.View.Pending &&
                ((TextBlock)page.FindName("CommandMessageText")).Text.Contains(controller.View.Message));
            string expected = scenario is "hold" or "planning" ? "Stopped" : scenario == "residual" ? "Remaining effects"
                : scenario is "fail" or "denied" ? "Failed" : "Completed";
            check(controller.View.State == expected && bridge.Submissions == 1 &&
                ((TextBlock)page.FindName("CommandMessageText")).Text.Contains(controller.View.Message),
                "native results come from actual registered execution/terminal readback, with no replay: " + scenario);
            var history = await core.GetHistoryAsync(Guid.NewGuid().ToString("D"), controller.View.TaskId, 100, default);
            check(history.IsSuccess && history.Response!.Tasks.Single().RequestId == controller.View.RequestId &&
                (expected == "Completed" ? history.Response.Actions.Single().Verified && history.Response.Tasks.Single().FinalState == "SUCCEEDED"
                    : history.Response.Tasks.Single().FinalState == (scenario == "residual" ? "STOPPED_WITH_RESIDUAL" : expected == "Stopped" ? "STOPPED" : "FAILED")),
                "native dashboard agrees with saved SQLite action verification and terminal/residual state: " + scenario);
            if (scenario == "planning") check(history.Response!.Actions.Length == 0 && history.Response.Tasks.Single().Route == "SMART",
                "native STOP interrupts the actual SMART orchestration planner wait before any executor entry");
        }
        root.Children.Clear();
    }

    private static void Invoke(Button button) => ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button)
        .GetPattern(PatternInterface.Invoke)).Invoke();
    private static Task Until(Func<bool> condition) => Until(() => Task.FromResult(condition()));
    private static async Task Until(Func<Task<bool>> condition)
    {
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < TimeSpan.FromSeconds(5))
        {
            if (await condition()) return;
            await Task.Delay(10);
        }
        throw new TimeoutException("Native command fixture did not reach its required readback.");
    }

    private sealed class Bridge(CoreIpcClient core) : ICommandClient
    {
        private readonly CoreCommandClient _inner = new(core);
        internal int Submissions, Stops;
        internal bool LoseAck, LoseRead;
        public async Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitAsync(string request, string text, CancellationToken token)
        {
            Submissions++;
            var actual = await _inner.SubmitAsync(request, text, token);
            return LoseAck && actual.IsSuccess
                ? CoreRequestResult<CoreRequestProtocol.SubmissionAck>.Failed(CoreConnectionFailure.Timeout, true) : actual;
        }
        public Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> ReadAsync(string request, string task, CancellationToken token)
        {
            if (LoseRead) { LoseRead = false; return Task.FromResult(CoreRequestResult<CoreRequestProtocol.TerminalReadback>.Failed(CoreConnectionFailure.Unavailable)); }
            return _inner.ReadAsync(request, task, token);
        }
        public Task<CoreRequestResult<CoreRequestProtocol.HistoryReply>> HistoryAsync(string request, CancellationToken token) => _inner.HistoryAsync(request, token);
        public Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(string request, string? submissionRequest, CancellationToken token)
        { Stops++; return _inner.StopAsync(request, submissionRequest, token); }
    }
}
