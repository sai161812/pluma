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
        var blank = new ToolResultCard();
        check(((PopupStatusIndicator)blank.FindName("OutcomeState")).Label == "Unverified" &&
            ((PopupMessageText)blank.FindName("ResultText")).DisplayText.Contains("unavailable") &&
            ((TextBlock)new RouteBadgePopup().FindName("RouteText")).Text == "Unavailable",
            "native route/result controls start without fabricated route, verification or file-success defaults");
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("commands");
        await using var core = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var owner = new EventFeedController(new CoreEventFeedClient(core));
        int notices = 0; EventFeedEntry? latest = null;
        var surfaceFacts = new System.Collections.Generic.List<ActivitySurfaceFact>();
        var delivery = new System.Collections.Generic.List<(string Task, string Kind)>();
        owner.Surface += fact => { surfaceFacts.Add(fact); delivery.Add((fact.TaskId, "surface")); };
        owner.Notice += entry => { notices++; latest = entry; delivery.Add((entry.TaskId, "notice")); };
        await owner.PollOnceAsync(default);
        var page = new DashboardPage();
        page.AttachCoreClient(core); page.AttachEventController(owner);
        root.Children.Clear(); root.Children.Add(page);
        foreach (string command in new[] { "fixture:read", "fixture:verify", "fixture:fail", "fixture:denied" })
        {
            var submitted = await core.SubmitTextAsync(Guid.NewGuid().ToString("D"), command, default);
            if (submitted.Response is not { Accepted: true }) throw new InvalidOperationException("Owned event task not admitted.");
            var watch = Stopwatch.StartNew();
            while ((latest?.TaskId != submitted.Response.TaskId || command == "fixture:read" && latest?.Verified != true) && watch.Elapsed < TimeSpan.FromSeconds(5))
            { await owner.PollOnceAsync(default); await Task.Delay(10); }
            var observed = latest;
            if (observed is null || observed.TaskId != submitted.Response.TaskId) throw new TimeoutException("Owned terminal notice was not observed.");
            var list = (LiveMessageFeed)page.FindName("LiveFeed");
            check(delivery.FindLastIndex(item => item.Task == observed.TaskId && item.Kind == "surface") <
                delivery.FindLastIndex(item => item.Task == observed.TaskId && item.Kind == "notice"),
                "coalesced native action evidence precedes its terminal notice: " + command);
            check(list.Entries.Any(entry => entry.Message.Contains(submitted.Response.TaskId!)),
                "native live feed displays actual committed task identity and independent terminal readback: " + command);
            var history = await core.GetHistoryAsync(Guid.NewGuid().ToString("D"), submitted.Response.TaskId, 100, default);
            bool success = command is "fixture:read" or "fixture:verify";
            check(history.IsSuccess && history.Response!.Tasks.Single().FinalState == (success ? "SUCCEEDED" : "FAILED") &&
                observed.Verified == success && (!success || history.Response.Actions.Single().Verified),
                "native event projection agrees with actual policy/registry and independent WAL history: " + command);
            var notice = EventNoticePresentation.Create(observed);
            var routeFact = surfaceFacts.Last(f => f.TaskId == submitted.Response.TaskId && f.Surface == 6);
            var route = (RouteBadgePopup)ActivitySurfacePresentation.Create(routeFact);
            root.Children.Add(route);
            check(((TextBlock)route.FindName("RouteText")).Text == "Fast",
                "native route badge displays the actual saved route without a sample default: " + command);
            root.Children.Remove(route);
            var actionFact = surfaceFacts.Last(f => f.TaskId == submitted.Response.TaskId && f.Surface is 8 or 19);
            var actionView = ActivitySurfacePresentation.Create(actionFact); root.Children.Add(actionView);
            if (success)
            {
                var card = (ToolResultCard)actionView;
                check(((PopupStatusIndicator)card.FindName("OutcomeState")).Label == "Verified" &&
                    ((PopupMessageText)card.FindName("ResultText")).DisplayText == "Read owned fixture." &&
                    actionFact.Detail!.FactualMessage == "Read owned fixture.",
                    "native result card binds the actual saved executor message and independent verification flags");
                var original = actionFact.Action!;
                card.ApplyEvidence(original with { Verified = false, ErrorRecorded = true },
                    actionFact.Detail! with { ErrorCode = "MUTATION_OUTCOME_PENDING", FactualMessage = "Execution outcome has not been observed." });
                check(((PopupStatusIndicator)card.FindName("OutcomeState")).Label == "Pending" &&
                    ((PopupStatusIndicator)card.FindName("VerificationState")).Label == "Not verified",
                    "native pre-mutation intent remains pending without an execution or verification claim");
                card.ApplyEvidence(actionFact.Action! with { Tool = new string('m', 64) }, actionFact.Detail);
                card.UpdateLayout();
                var toolLabel = (TextBlock)card.FindName("ToolNameText");
                check(toolLabel.Text.Contains(new string('m', 64), StringComparison.OrdinalIgnoreCase) && toolLabel.ActualHeight > 20,
                    "native result card wraps the complete maximum-length unbroken tool name");
            }
            else if (command == "fixture:fail")
            {
                var card = (ToolResultCard)actionView;
                check(((PopupStatusIndicator)card.FindName("OutcomeState")).Label == "Issue recorded" &&
                    ((PopupMessageText)card.FindName("ResultText")).Text == "Failed: Owned fixture failure." &&
                    ((PopupMessageText)card.FindName("ErrorCodeText")).Text == "FIXTURE_FAILED" &&
                    ((PopupMessageText)card.FindName("ErrorCodeText")).Visibility == Microsoft.UI.Xaml.Visibility.Visible &&
                    actionFact.Detail!.ErrorCode == "FIXTURE_FAILED",
                    "native failed executor result and error code survive actual ledger/IPC readback without an exception body");
            }
            else
            {
                var policy = (PolicyBlockNotice)actionView;
                check(policy.IsNoticeOpen && policy.MatchedRule == actionFact.Detail!.PolicyReason &&
                    !string.IsNullOrWhiteSpace(policy.MatchedRule) && policy.ToolName == "fixture_denied",
                    "native policy notice binds the exact saved denial reason and tool identity");
                policy.HideNotice();
            }
            root.Children.Remove(actionView);
            if (command == "fixture:verify")
            {
                var proofFact = surfaceFacts.Last(f => f.TaskId == submitted.Response.TaskId && f.Surface == 17);
                var indicator = (PostClickVerifyIndicator)ActivitySurfacePresentation.Create(proofFact);
                root.Children.Add(indicator);
                check(indicator.IsOpen && indicator.Title == "Verified" && proofFact.Verification is
                    { Verified: true, Method: "owned_file_readback" },
                    "native verification feedback uses the actual registered owned-adapter proof read from the ledger");
                indicator.HideResult(); root.Children.Remove(indicator);
            }
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
        check(((LiveMessageFeed)returning.FindName("LiveFeed")).Entries.Count == owner.View.Messages!.Length && notices == count,
            "native navigation restores the shell-owned feed without resubmission or replay");
        root.Children.Clear();
        await CheckRuntimeAsync(root, core, check);
    }

    private static async Task CheckRuntimeAsync(StackPanel root, CoreIpcClient core, Action<bool, string> check)
    {
        var submitted = await core.SubmitTextAsync(Guid.NewGuid().ToString("D"), "fixture:hold", default);
        if (submitted.Response is not { Accepted: true } accepted) throw new InvalidOperationException("Owned live fixture not admitted.");
        var runtime = new RuntimeController(core.GetRuntimeAsync);
        var watch = Stopwatch.StartNew(); CoreRequestProtocol.RuntimeTask? live = null;
        while (watch.Elapsed < TimeSpan.FromSeconds(3))
        {
            await runtime.PollOnceAsync(default);
            live = runtime.View.Tasks.FirstOrDefault(task => task.TaskId == accepted.TaskId && task.Phase == "EXECUTING");
            if (live is not null) break;
            await Task.Delay(10);
        }
        if (live is null) throw new TimeoutException("Actual executor entry was not observed.");
        check(live.State == "RUNNING" && live.Step == 1 && live.Total == 1 && live.Tool == "fixture_command" && live.ToolElapsedMs >= 0,
            "actual runtime IPC reports owned executor entry and the selected validated FAST plan step");
        foreach (var key in RuntimePresentation.Keys(live))
        {
            var control = RuntimePresentation.Create(key.Surface, live); root.Children.Add(control);
            check(key.Surface switch
            {
                4 => ((PopupMessageText)control.FindName("TaskIdentity")).Text == accepted.TaskId,
                5 => ((TextBlock)control.FindName("StepText")).Text == "Step 1 of 1",
                7 => ((PopupStatusIndicator)control.FindName("CallStatus")).Label == "Executing",
                _ => false
            }, "native live surface binds actual task/step/tool readback: " + key.Surface);
            root.Children.Remove(control);
        }
        var rolling = live with { State = "ROLLING_BACK", RollbackStep = 1, RollbackTotal = 2, RollbackRecipe = "copy_file" };
        var rollback = RuntimePresentation.Create(9, rolling); root.Children.Add(rollback);
        check(((TextBlock)rollback.FindName("RollbackStep")).Text == "Inverse 1 of 2" &&
            ((ProgressBar)rollback.FindName("RollbackProgress")).IsIndeterminate && RuntimePresentation.Keys(rolling).All(k => k.Surface != 7),
            "native rollback projection fixture uses selected inverse evidence without invented completion percentages or executing tools");
        root.Children.Remove(rollback);
        var stop = await core.StopAsync(Guid.NewGuid().ToString("D"), accepted.TaskId, default);
        if (!stop.IsSuccess) throw new InvalidOperationException("Owned live fixture STOP was not acknowledged.");
        await runtime.PollOnceAsync(default);
        var terminal = await core.GetTerminalReadbackAsync(accepted.RequestId, accepted.TaskId!, default);
        check(runtime.View.Tasks.All(task => task.TaskId != accepted.TaskId) &&
            terminal.Response is { Terminal: true, TerminalPersisted: true, FinalState: "STOPPED" },
            "live disappearance is independently checked against actual STOP and saved terminal evidence");
        check(RuntimePresentation.Elapsed(90000000) == "25:00:00", "live elapsed hours do not wrap at one day");
    }
}
