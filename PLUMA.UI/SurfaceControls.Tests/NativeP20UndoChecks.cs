using System;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests;

internal static class NativeP20UndoChecks
{
    private static async Task Until(Func<bool> ready)
    {
        var timer = Stopwatch.StartNew();
        while (!ready() && timer.Elapsed.TotalSeconds < 6) await Task.Delay(15);
        if (!ready()) throw new TimeoutException("Owned saved-undo UI condition was not observed.");
    }
    private static void Invoke(Button button) => ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button)
        .GetPattern(PatternInterface.Invoke)).Invoke();
    private static Button Find(DependencyObject root, string label)
    {
        if (root is Button button && button.Content?.ToString() == label) return button;
        for (int i=0; i<VisualTreeHelper.GetChildrenCount(root); i++)
        { try { return Find(VisualTreeHelper.GetChild(root,i), label); } catch (InvalidOperationException) { } }
        throw new InvalidOperationException("Owned dialog button not ready.");
    }
    internal static async Task RunAsync(Action<bool,string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("history_undo");
        await using var client = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var shell = new MainWindow(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        shell.Activate(); NativeActivityTray? tray = null;
        try
        {
            await fixture.WaitForEventAsync("INITIAL_STATUS_PENDING");
            await fixture.ControlHistoryAsync("history_assert_pending");
            await fixture.ControlHistoryAsync("history_release_startup");
            await Until(() => shell.Dashboard is { IsLoaded:true } page && ((Button)page.FindName("CommandRunButton")).IsEnabled);
            await fixture.ControlHistoryAsync("history_assert_startup");
            check(true, "initial admission health drains before all four ordinary observers start");
            tray = shell.ActivityTrayForAcceptance;
            check(tray is not null && !tray.IsDisposed, "production shell owns one native Activity tray contract");
            tray!.Select(1);
            await Until(() => shell.History is { IsLoaded:true });
            check(shell.History is not null, "native Activity tray menu command reaches the actual History page");
            foreach (string scenario in new[] { "approve", "deny", "stop", "conflict" })
            {
                await fixture.ControlHistoryAsync("history_move");
                var page = shell.History!;
                Invoke((Button)page.FindName("HistoryRefresh"));
                var records = (ListView)page.FindName("HistoryRecords");
                await Until(() => records.Items.Cast<HistoryRow>().Any(r => r.CommandText == "Owned P20 file move"));
                records.SelectedItem = records.Items.Cast<HistoryRow>().First(r => r.CommandText == "Owned P20 file move");
                var selectedTask = ((HistoryRow)records.SelectedItem).TaskId;
                var actions = (ListView)page.FindName("DetailActions");
                await Until(() => actions.Items.Count == 1);
                actions.SelectedIndex = 0;
                var action = ((SavedActionRow)actions.SelectedItem).Original;
                check(action.Tool == "move_file" && action.Verified && action.VerificationMethod is not null && action.Selection is not null,
                    "native saved detail reads actual owned-file policy, verifier and selected inverse: " + scenario);
                if (scenario == "conflict") await fixture.ControlHistoryAsync("history_conflict");
                await Until(() => ((Button)page.FindName("DetailUndo")).IsEnabled);
                Invoke((Button)page.FindName("DetailUndo"));
                await Until(() => shell.ApprovalForAcceptance is { IsLoaded:true });
                var approval = shell.ApprovalForAcceptance!;
                check(((PopupMessageText)approval.FindName("MaterialEffectText")).DisplayText.Contains("Restore captured move file"),
                    "selected inverse requires material confirmation from the recorded effect: " + scenario);
                if (scenario == "stop")
                    await client.StopAsync(Guid.NewGuid().ToString("D"), null, default);
                else
                    Invoke(Find(approval, scenario == "deny" ? "Deny" : "Approve"));
                await Until(() => shell.ApprovalForAcceptance is null);
                await Until(() => actions.Items.Count == 1 && ((SavedActionRow)actions.Items[0]).Original.ActionId == action.ActionId &&
                    (((SavedActionRow)actions.Items[0]).Original.ClaimState is not null || scenario is "stop" or "deny" && !shell.CurrentCommandForAcceptance.Pending));
                var read = await client.GetTaskDetailAsync(Guid.NewGuid().ToString("D"), selectedTask, 0, default);
                check(read.IsSuccess, "native selected inverse has independently queried saved scope: " + scenario);
                var saved = read.Response!.Actions.Single();
                if (scenario == "stop")
                {
                    var command = shell.CurrentCommandForAcceptance;
                    var stopped = await client.GetTerminalReadbackAsync(command.RequestId!, command.TaskId!, default);
                    check(stopped.Response is { Terminal:true, TerminalPersisted:true } terminal &&
                        terminal.FinalState is "STOPPED" or "STOPPED_WITH_RESIDUAL",
                        "selected undo STOP agrees with independently saved stopped/residual terminal facts");
                }
                if (scenario == "approve")
                {
                    await fixture.ControlHistoryAsync("history_assert_restored");
                    check(saved.ClaimState == "verified" && saved.RollbackOk is true && !saved.UndoAvailable && saved.Selection is null,
                        "native selected undo restores the owned file and atomically consumes its captured inverse");
                    var duplicate = await client.SubmitUndoAsync(Guid.NewGuid().ToString("D"), action.Selection!, default);
                    check(duplicate.IsSuccess, "a stale duplicate receives admission facts rather than a fabricated inverse result");
                }
                else if (scenario == "conflict")
                {
                    await fixture.ControlHistoryAsync("history_assert_conflict");
                    check(saved.ClaimState == "unverified" && saved.RollbackOk is false && saved.RollbackCode == "ROLLBACK_CONFLICT" && saved.Selection is null && saved.ConflictCurrent is not null,
                        "native conflict retains both owned file contents, exact paths and nonrepeatable evidence");
                    actions.SelectedIndex = 0; Invoke((Button)page.FindName("DetailConflict"));
                    await Until(() => page.ActiveConflict is { IsLoaded:true });
                    var dialog = page.ActiveConflict!;
                    check(((PopupMessageText)dialog.FindName("CurrentPathText")).Text == saved.ConflictCurrent &&
                        ((PopupMessageText)dialog.FindName("ConflictPathText")).Text == saved.ConflictTarget,
                        "actual conflict surface binds recorded paths without sample data or overwrite actions");
                    if (Environment.GetEnvironmentVariable("GITHUB_ACTIONS") == "true")
                    {
                        // The disposable Windows acceptance host may open a
                        // newly owned folder. Personal desktop runs do not.
                        await fixture.ControlHistoryAsync("history_prepare_folder");
                        string? prior = shell.CurrentCommandForAcceptance.RequestId;
                        Console.WriteLine("Owned folder command before invocation: " + JsonSerializer.Serialize(shell.CurrentCommandForAcceptance));
                        Console.WriteLine("Owned folder dialog admission enabled: " + dialog.IsSecondaryButtonEnabled);
                        Invoke(Find(dialog, "Open folder"));
                        await Until(() => shell.CurrentCommandForAcceptance.RequestId != prior && !shell.CurrentCommandForAcceptance.Pending);
                        var command = shell.CurrentCommandForAcceptance;
                        var folder = await client.GetTaskDetailAsync(Guid.NewGuid().ToString("D"), command.TaskId!, 0, default);
                        Console.WriteLine("Owned folder saved timing and verifier: " + JsonSerializer.Serialize(folder.Response));
                        check(folder.IsSuccess && folder.Response!.Actions.Single().Tool == "open_folder" && folder.Response.Actions.Single().Verified,
                            "actual conflict folder command has native Shell visibility and saved verifier readback");
                        await fixture.ControlHistoryAsync("history_assert_folder");
                        check(true,"disposable native acceptance closes only its newly owned folder window");
                    }
                    else
                    {
                        Invoke(Find(dialog, "View conflict"));
                        Console.WriteLine("UNEXECUTED physical folder opening: reserved for disposable Windows acceptance host.");
                    }
                    await Until(() => page.ActiveConflict is null);
                }
                else
                {
                    await fixture.ControlHistoryAsync("history_assert_unchanged");
                    check(saved.ClaimState is null && saved.UndoAvailable && !saved.RollbackAttempted,
                        "denial or priority STOP preserves captured pre-state and both owned file postconditions: " + scenario);
                }
            }
            shell.NavigateForAcceptance(true);
            await Until(() => shell.Dashboard is { IsLoaded:true } page && ((Button)page.FindName("CommandRunButton")).IsEnabled);
            var dashboard = shell.Dashboard!;
            ((AutoSuggestBox)dashboard.FindName("CommandInput")).Text = "show activity";
            Invoke((Button)dashboard.FindName("CommandRunButton"));
            await Until(() => shell.History is { IsLoaded:true });
            check(shell.History is not null, "verified registered show activity command opens the shared native History page");
        }
        catch (Exception error)
        {
            fixture.WriteFolderDiagnostics();
            Console.Error.WriteLine("P20 selected undo failure before teardown: " + error);
            var command = shell.CurrentCommandForAcceptance;
            Console.Error.WriteLine("Owned command outcome: " + JsonSerializer.Serialize(command));
            if (command.RequestId is not null && command.TaskId is not null)
            {
                try
                {
                    var terminal = await client.GetTerminalReadbackAsync(command.RequestId, command.TaskId, default);
                    var detail = await client.GetTaskDetailAsync(Guid.NewGuid().ToString("D"), command.TaskId, 0, default);
                    Console.Error.WriteLine("Owned terminal readback: " + JsonSerializer.Serialize(terminal));
                    Console.Error.WriteLine("Owned saved detail: " + JsonSerializer.Serialize(detail));
                }
                catch (Exception diagnostic) { Console.Error.WriteLine("Owned failure readback unavailable: " + diagnostic.GetType().Name); }
            }
            throw;
        }
        finally { shell.Close(); await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(5)); }
        check(tray is { IsDisposed:true, IsAvailable:false } && shell.ObservationLifetime.IsCompleted,
            "shell shutdown removes only its own tray entry and joins saved-detail/command observers");
    }
}
