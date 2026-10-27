using System;
using System.Diagnostics;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI.Tests;

internal static class NativeEventFeedChecks
{
    internal static async Task RunAsync(StackPanel root, Action<bool, string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("commands");
        await using var core = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var owner = new EventFeedController(new CoreEventFeedClient(core));
        int notices = 0; EventFeedEntry? latest = null;
        owner.Notice += entry => { notices++; latest = entry; };
        await owner.PollOnceAsync(default);
        var page = new DashboardPage();
        page.AttachCoreClient(core); page.AttachEventController(owner);
        root.Children.Clear(); root.Children.Add(page);
        foreach (string command in new[] { "fixture:read", "fixture:denied" })
        {
            var submitted = await core.SubmitTextAsync(Guid.NewGuid().ToString("D"), command, default);
            if (submitted.Response is not { Accepted: true }) throw new InvalidOperationException("Owned event task not admitted.");
            var watch = Stopwatch.StartNew();
            while ((latest?.TaskId != submitted.Response.TaskId || command == "fixture:read" && latest?.Verified != true) && watch.Elapsed < TimeSpan.FromSeconds(5))
            { await owner.PollOnceAsync(default); await Task.Delay(10); }
            var observed = latest;
            if (observed is null || observed.TaskId != submitted.Response.TaskId) throw new TimeoutException("Owned terminal notice was not observed.");
            var list = (ListView)page.FindName("LiveMessagesList");
            check(list.Items.Cast<EventFeedEntry>().Any(entry => entry.TaskId == submitted.Response.TaskId && entry.Terminal),
                "native live feed displays actual committed task identity and independent terminal readback: " + command);
            var history = await core.GetHistoryAsync(Guid.NewGuid().ToString("D"), submitted.Response.TaskId, 100, default);
            check(history.IsSuccess && history.Response!.Tasks.Single().FinalState == (command == "fixture:read" ? "SUCCEEDED" : "FAILED") &&
                observed.Verified == (command == "fixture:read") && (command != "fixture:read" || history.Response.Actions.Single().Verified),
                "native event projection agrees with actual policy/registry and independent WAL history: " + command);
            var notice = EventNoticePresentation.Create(observed);
            root.Children.Add(notice);
            check(notice.IsOpen && ((PopupMessageText)notice.FindName("NoticeText")).DisplayText.Contains(submitted.Response.TaskId!),
                "production native notice presentation retains actual task identity: " + command);
            notice.Hide(); root.Children.Remove(notice);
            var unchanged = await core.GetTerminalReadbackAsync(submitted.Response.RequestId, submitted.Response.TaskId!, default);
            check(unchanged.Response is { Terminal: true } && unchanged.Response.FinalState == history.Response!.Tasks.Single().FinalState,
                "dismissing native factual notice neither cancels nor changes the backend task: " + command);
        }
        int count = notices;
        await owner.PollOnceAsync(default);
        check(notices == count, "native event reconnect/readback does not repeat old notices");
        root.Children.Clear(); await Task.Delay(20);
        var returning = new DashboardPage(); returning.AttachCoreClient(core); returning.AttachEventController(owner);
        root.Children.Add(returning); await Task.Delay(30);
        check(((ListView)returning.FindName("LiveMessagesList")).Items.Count == owner.View.Entries.Length && notices == count,
            "native navigation restores the shell-owned feed without resubmission or replay");
        root.Children.Clear();
    }
}
