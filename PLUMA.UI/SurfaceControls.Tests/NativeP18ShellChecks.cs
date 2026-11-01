using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI.Tests;

internal static class NativeP18ShellChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static async Task Until(Func<bool> predicate, double seconds = 4)
    {
        var timer = Stopwatch.StartNew();
        while (!predicate() && timer.Elapsed.TotalSeconds < seconds) await Task.Delay(15);
        if (!predicate()) throw new TimeoutException("Owned P18 shell acceptance condition was not observed.");
    }
    private static void Invoke(Button button) => ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button)
        .GetPattern(PatternInterface.Invoke)).Invoke();

    internal static async Task RunAsync(Action<bool, string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("commands");
        await using var client = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var shell = new MainWindow(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var notifications = new List<(string Key, int Surface, bool Accepted)>();
        shell.NotificationPresented += (key, surface, accepted) => notifications.Add((key, surface, accepted));
        var host = shell.Popups;
        var frames = new List<PopupWindowSnapshot[]>();
        host.FramePresented += frame => { if (frames.Count == 1000) frames.RemoveAt(0); frames.Add(frame.ToArray()); };
        shell.Activate();
        CoreRequestProtocol.SubmissionAck? closeTask = null;
        try
        {
            await Until(() => shell.Dashboard is { IsLoaded: true } page && ((Button)page.FindName("CommandRunButton")).IsEnabled);
            var dashboard = shell.Dashboard!;
            ((AutoSuggestBox)dashboard.FindName("CommandInput")).Text = "fixture:hold";
            Invoke((Button)dashboard.FindName("CommandRunButton"));
            await Until(() => host.Windows.Any(window => window.HostedContent is ToolCallCard card &&
                ((PopupStatusIndicator)card.FindName("CallStatus")).Label == "Executing"));
            var live = await client.GetRuntimeAsync(Id(), default);
            var task = live.Response!.Tasks.Single();
            check(host.Windows.Any(window => window.HostedContent is TaskRunningPopup card &&
                ((PopupMessageText)card.FindName("TaskIdentity")).Text == task.TaskId) &&
                host.Windows.Any(window => window.HostedContent is StepProgressPopup card &&
                ((TextBlock)card.FindName("StepText")).Text == "Step 1 of 1"),
                "actual MainWindow, typed core and shared native host display the same live task/step/tool identity");
            await Until(() => frames.Any(frame => frame.Any(card => card.Key == "runtime-tool-" + task.TaskId && card.Opacity > .95)));
            check(frames.SelectMany(frame => frame).Where(card => card.Opacity > .95).All(card => card.Bounds.Width > 0 && card.Bounds.Height > 0),
                "event-driven shell popups reached native visible layout rather than merely returning from a factory");
            nint originalToolWindow = host.HandleFor("runtime-tool-" + task.TaskId);
            await Task.Delay(300);
            check(originalToolWindow != 0 && host.HandleFor("runtime-tool-" + task.TaskId) == originalToolWindow,
                "actual live replacements update the existing owned popup window instead of duplicating it");
            shell.NavigateForAcceptance(false); await Task.Delay(30); shell.NavigateForAcceptance(true);
            await Until(() => shell.Dashboard is { IsLoaded: true } page &&
                ((Button)page.FindName("CommandStopButton")).IsEnabled &&
                ((CoreHealthIndicator)page.FindName("CoreHealthReadback")).IsConnected &&
                ((ListView)page.FindName("CurrentActivityList")).Items.Cast<string>().Any(line => line.Contains(task.TaskId)));
            dashboard = shell.Dashboard!;
            check(((ListView)dashboard.FindName("CurrentActivityList")).Items.Cast<string>().Any(line => line.Contains(task.TaskId)) &&
                ((CoreHealthIndicator)dashboard.FindName("CoreHealthReadback")).IsConnected,
                "actual navigation restores shell-owned live state and measured connection health without resubmitting");
            var capacityKeys = new List<string>();
            for (int index = 0; host.Count < PopupStackState.Capacity - 1 && index < PopupStackState.Capacity; index++)
            {
                string key = "owned-capacity-" + index; capacityKeys.Add(key);
                if (!host.Present(key, 6, new RouteBadgePopup(), persistent: true))
                    throw new InvalidOperationException("Owned capacity fixture was not admitted.");
            }
            check(host.Count == PopupStackState.Capacity - 1, "actual shared host is saturated except the reserved priority STOP slot");
            var stopTimer = Stopwatch.StartNew(); Invoke((Button)dashboard.FindName("CommandStopButton"));
            await Until(() => frames.Any(frame => frame.Any(card => card.Key == "command-stop" && card.Opacity > .9)));
            await Until(() => notifications.Any(item => item.Key == "ledger-notice-" + task.TaskId));
            var stopped = await client.GetTerminalReadbackAsync(task.TaskRequestId, task.TaskId, default);
            check(stopTimer.Elapsed < TimeSpan.FromSeconds(3) && stopped.Response is
                { Terminal: true, TerminalPersisted: true, FinalState: "STOPPED" },
                "actual shell priority STOP survives concurrent popup work and agrees with saved cleanup/terminal evidence");
            foreach (string key in capacityKeys) host.Dismiss(key);
            await Until(() => !host.Windows.Any(window => window.HostedContent is ToolCallCard or TaskRunningPopup or StepProgressPopup));

            await Until(() => ((Button)dashboard.FindName("CommandRunButton")).IsEnabled);
            ((AutoSuggestBox)dashboard.FindName("CommandInput")).Text = "fixture:process";
            Invoke((Button)dashboard.FindName("CommandRunButton"));
            await Until(() => host.Windows.Any(window => window.HostedContent is ToolCallCard card &&
                ((PopupMessageText)card.FindName("CallTool")).Text == "Fixture process" &&
                ((PopupStatusIndicator)card.FindName("CallStatus")).Label == "Executing"));
            Invoke((Button)dashboard.FindName("CommandStopButton"));
            await Until(() => notifications.Any(item => item.Surface == 21 && item.Accepted));
            var absent = await client.GetRuntimeAsync(Id(), default);
            var worker = absent.Response!.Terminations.Single();
            await Until(() => host.Windows.Any(window => window.HostedContent is WorkerTerminationFlash flash &&
                flash.WorkerPid == worker.Pid.ToString(System.Globalization.CultureInfo.InvariantCulture)));
            check(host.Windows.Any(window => window.HostedContent is WorkerTerminationFlash flash &&
                flash.WorkerPid == worker.Pid.ToString(System.Globalization.CultureInfo.InvariantCulture)) && worker.CreationTime > 0,
                "actual owned process STOP produces native worker feedback only after identity-bound absence readback");

            var inverse = (await client.SubmitTextAsync(Id(), "fixture:rollback", default)).Response!;
            await Until(() => host.Windows.Any(window => window.HostedContent is ToolCallCard card &&
                ((PopupMessageText)card.FindName("CallTool")).Text == "Fixture rollback"));
            await client.StopAsync(Id(), inverse.TaskId, default);
            await Until(() => host.Windows.Any(window => window.HostedContent is RollbackPopup card &&
                ((TextBlock)card.FindName("RollbackStep")).Text == "Inverse 1 of 1" &&
                ((ProgressBar)card.FindName("RollbackProgress")).IsIndeterminate));
            await fixture.WaitForEventAsync("ROLLBACK_READBACK_OK");
            await Until(() => notifications.Any(item => item.Key == "ledger-notice-" + inverse.TaskId));
            var undone = await client.GetTerminalReadbackAsync(inverse.RequestId, inverse.TaskId!, default);
            check(undone.Response is { Terminal: true, TerminalPersisted: true, FinalState: "STOPPED", HasResidual: false },
                "actual shell rollback projects a selected real inverse and agrees with independent owned-file and saved cleanup readback");

            await fixture.ControlEventsAsync(true);
            await Until(() => ((TextBlock)dashboard.FindName("LiveConnectionText")).Text.Contains("unavailable"));
            var burst = new List<(CoreRequestProtocol.SubmissionAck Ack, bool Success)>();
            foreach (string command in new[] { "read", "verify", "fail", "denied", "read", "verify", "fail", "read" })
            {
                var reply = await client.SubmitTextAsync(Id(), "fixture:" + command, default);
                if (reply.Response is not { Accepted: true } accepted) throw new InvalidOperationException("Owned burst refused.");
                burst.Add((accepted, command is "read" or "verify"));
            }
            await fixture.ControlEventsAsync(false);
            await Until(() => burst.All(item => notifications.Any(note => note.Key == "ledger-notice-" + item.Ack.TaskId) &&
                ((LiveMessageFeed)dashboard.FindName("LiveFeed")).Entries.Any(row => row.Message.Contains(item.Ack.TaskId!) &&
                    row.Message.Contains(item.Success ? "Task completed and verified." : "Task did not complete successfully."))), 6);
            check(host.Count <= PopupStackState.Capacity && notifications.Any(item => item.Surface == 17 && item.Accepted) &&
                notifications.Any(item => item.Surface == 19 && item.Accepted) && notifications.Any(item => item.Surface == 8 && item.Accepted),
                "multi-surface burst recovers factual results, verification and denial through the actual shared bounded host");
            check(((LiveMessageFeed)dashboard.FindName("LiveFeed")).Entries.Any(row => row.Message.Contains("Read owned fixture.") && row.Message.Contains("Postcondition verified.")),
                "actual live-message widget projects saved executor detail and its independent verification flag");
            foreach (var item in burst)
            {
                var saved = await client.GetHistoryAsync(Id(), item.Ack.TaskId, 100, default);
                check(saved.IsSuccess && saved.Response!.Tasks.Single().FinalState is "SUCCEEDED" or "FAILED",
                    "reconnected shell burst agrees with independent WAL task readback");
            }
            int count = notifications.Count;
            await Task.Delay(700);
            check(notifications.Count == count, "actual authenticated replay polls do not duplicate old multi-surface notifications");
            check(host.Windows.Select(window => window.Handle).Distinct().Count() == host.Windows.Count(),
                "shared shell popup replacements keep one owned native window per entry");
            host.Clear();
            await Until(() => host.Count == 0);
            closeTask = (await client.SubmitTextAsync(Id(), "fixture:hold", default)).Response!;
            await Until(() => host.Windows.Any(window => window.HostedContent is TaskRunningPopup card &&
                ((PopupMessageText)card.FindName("TaskIdentity")).Text == closeTask.TaskId));
        }
        finally
        {
            shell.Close(); await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(4));
        }
        check(host.IsDisposed && host.Count == 0 && !host.TimerRunning,
            "actual shell shutdown drains observers and owned popup windows/timers without an implicit backend cancellation");
        var stillOwned = await client.GetTerminalReadbackAsync(closeTask!.RequestId, closeTask.TaskId!, default);
        check(stillOwned.Response is { Terminal: false }, "closing the actual whole shell leaves an admitted backend task owned and active");
        await client.StopAsync(Id(), closeTask.TaskId, default);
    }
}
