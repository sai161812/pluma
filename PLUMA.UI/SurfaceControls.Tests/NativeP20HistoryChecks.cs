using System;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests;

internal static class NativeP20HistoryChecks
{
    private static async Task Until(Func<bool> test)
    {
        var timer = Stopwatch.StartNew();
        while (!test() && timer.Elapsed.TotalSeconds < 5) await Task.Delay(20);
        if (!test()) throw new TimeoutException("Owned P20 history condition was not observed.");
    }
    private static void Invoke(Button button) => ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button)
        .GetPattern(PatternInterface.Invoke)).Invoke();
    private static string[] Texts(DependencyObject root)
    {
        var values = new System.Collections.Generic.List<string>();
        if (root is TextBlock text) values.Add(text.Text);
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++) values.AddRange(Texts(VisualTreeHelper.GetChild(root,i)));
        return values.ToArray();
    }
    internal static async Task RunAsync(Action<bool, string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("history");
        var shell = new MainWindow(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        shell.Activate();
        try
        {
            await Until(() => shell.Dashboard is { IsLoaded: true });
            shell.NavigateHistoryForAcceptance();
            await Until(() => shell.History is { IsLoaded: true } loaded && ((TextBlock)loaded.FindName("HistoryStatus")).Text == "No saved tasks.");
            var page = shell.History!;
            var list = (ListView)page.FindName("HistoryRecords");
            check(list.Items.Count == 0 && !((Button)page.FindName("HistoryOlder")).IsEnabled,
                "native history starts with factual empty storage and no production sample rows");
            await fixture.ControlHistoryAsync("history_seed");
            Invoke((Button)page.FindName("HistoryRefresh"));
            await Until(() => list.Items.Count == 20 && list.ContainerFromIndex(0) is ListViewItem);
            var first = list.Items.Cast<HistoryRow>().ToArray();
            check(first.All(row => !row.CommandText.Contains("HISTORY_PRIVATE_NATIVE_PAYLOAD")) &&
                first.Any(row => row.CommandText.Contains("file_预算_")) && first.All(row => row.StateText.StartsWith("Saved:")),
                "actual history page reads bounded redacted SQLite facts with literal filenames");
            check(Texts((ListViewItem)list.ContainerFromIndex(0)).Contains(first[0].TaskId) &&
                Texts((ListViewItem)list.ContainerFromIndex(0)).Contains(first[0].CommandText),
                "actual native history template renders the same identities and command values as the validated DTO");
            await VisualReview.CaptureAsync(page, System.IO.Path.Combine(AppContext.BaseDirectory, "history-page-saved-dark.png"));
            var scroll = (ScrollViewer)page.Content;
            scroll.ChangeView(null, scroll.ScrollableHeight, null, true); await Task.Delay(80);
            Invoke((Button)page.FindName("HistoryOlder"));
            await Until(() => list.Items.Count == 20 && ((HistoryRow)list.Items[0]).TaskId != first[0].TaskId);
            check(!list.Items.Cast<HistoryRow>().Select(row => row.TaskId).Intersect(first.Select(row => row.TaskId)).Any(),
                "native older-page control advances the saved cursor without duplicates or unbounded accumulation");
            ((AutoSuggestBox)page.FindName("HistorySearch")).Text = "HISTORY_PRIVATE_NATIVE_PAYLOAD";
            Invoke((Button)page.FindName("HistoryRefresh"));
            await Until(() => ((TextBlock)page.FindName("HistoryStatus")).Text == "No matching saved tasks.");
            check(list.Items.Count == 0, "native history search cannot reveal a legacy private clipboard payload");
            ((AutoSuggestBox)page.FindName("HistorySearch")).Text = "FILE_预算_";
            Invoke((Button)page.FindName("HistoryRefresh"));
            await Until(() => list.Items.Count == 20);
            check(list.Items.Cast<HistoryRow>().All(row => row.CommandText.Contains("file_预算_")),
                "native Unicode case-insensitive search uses redacted saved values");
            var ids = list.Items.Cast<HistoryRow>().Select(row => row.TaskId).ToArray();
            shell.NavigateForAcceptance(true); shell.NavigateHistoryForAcceptance();
            await Until(() => shell.History is { IsLoaded: true });
            page = shell.History!; list = (ListView)page.FindName("HistoryRecords");
            check(list.Items.Cast<HistoryRow>().Select(row => row.TaskId).SequenceEqual(ids),
                "navigation reuses the single shell history readback without creating another operation");
            await fixture.ControlHistoryAsync("history_close");
            Invoke((Button)page.FindName("HistoryRefresh"));
            await Until(() => ((TextBlock)page.FindName("HistoryStatus")).Text.Contains("unavailable"));
            check(list.Items.Count == 0 && !((Button)page.FindName("HistoryOlder")).IsEnabled,
                "closed storage clears stale native rows and never reports a fake empty-history pass");
            await fixture.ControlHistoryAsync("history_reopen");
            Invoke((Button)page.FindName("HistoryRefresh"));
            await Until(() => list.Items.Count == 20);
            check(list.Items.Cast<HistoryRow>().Select(row => row.TaskId).SequenceEqual(ids),
                "reopened durable history agrees with the same independently checked saved records");
        }
        finally { shell.Close(); await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(5)); }
        check(shell.ObservationLifetime.IsCompleted, "shell close joins history work and all existing observers");
    }
}
