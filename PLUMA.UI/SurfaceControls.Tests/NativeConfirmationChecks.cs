using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests;

internal static class NativeConfirmationChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    internal static async Task RunAsync(FrameworkElement root, Action<bool, string> check)
    {
        await using var fixture = await Fixture.StartAsync();
        await using var client = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        foreach (string scenario in new[] { "approve", "deny", "stop", "expiry", "close" })
        {
            var presenter = new NativeConfirmationPresenter(() => root.XamlRoot);
            var bridge = new CountingClient(client);
            var controller = new ConfirmationController(bridge, presenter, TimeSpan.FromMilliseconds(25));
            using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(7));
            Task run = controller.RunAsync(lifetime.Token);
            try
            {
                if (!(await client.GetConfirmationsAsync(Id(), controller.ClientId, default)).IsSuccess)
                    throw new InvalidOperationException("Owned approval lease failed.");
                var submitted = await client.SubmitTextAsync(Id(), "fixture:approval", default);
                if (submitted.Response is not { Accepted: true }) throw new InvalidOperationException("Owned task was not admitted.");
                await Until(() => presenter.ActiveDialog is { IsLoaded: true });
                var dialog = presenter.ActiveDialog!;
                var view = presenter.ActiveView!;
                string path = view.Arguments.GetProperty("path").GetString()!;
                check(path.Contains("p16_budget_预算_") &&
                    ((PopupMessageText)dialog.FindName("SanitizedArgumentsText")).DisplayText.Contains(path) &&
                    ((PopupMessageText)dialog.FindName("MaterialEffectText")).DisplayText.Contains(view.Prompt) &&
                    dialog.DefaultButton == ContentDialogButton.Secondary,
                    "native approval shows exact redacted material and literal filename with Deny default: " + scenario);
                if (scenario is "approve" or "deny")
                {
                    await Until(() =>
                    {
                        try { return FindButton(dialog, scenario == "approve" ? "Approve" : "Deny").IsLoaded; }
                        catch (InvalidOperationException) { return false; }
                    });
                    Button button = FindButton(dialog, scenario == "approve" ? "Approve" : "Deny");
                    ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button).GetPattern(PatternInterface.Invoke)).Invoke();
                }
                else if (scenario == "stop")
                    check((await client.StopAsync(Id(), submitted.Response.TaskId, default)).IsSuccess,
                        "native dialog cannot block independent backend STOP");
                else if (scenario == "close") lifetime.Cancel();
                await Until(() => presenter.ActiveDialog is null, 5);
                CoreRequestProtocol.TerminalReadback? terminal = null;
                await Until(async () =>
                {
                    terminal = (await client.GetTerminalReadbackAsync(submitted.Response.RequestId, submitted.Response.TaskId!, default)).Response;
                    return terminal?.Terminal == true;
                }, 5);
                var history = await client.GetHistoryAsync(Id(), submitted.Response.TaskId, 100, default);
                check(terminal!.TerminalPersisted == true && history.IsSuccess &&
                    (scenario == "approve" ? terminal.CompletionVerified && history.Response!.Actions.Single().Verified
                        : !terminal.CompletionVerified && history.Response!.Actions.All(a => !a.Verified)),
                    "native dialog decision agrees with actual registry verification and WAL ledger: " + scenario);
                check(bridge.Decisions == (scenario is "approve" or "deny" ? 1 : 0),
                    "native dialog produces at most one exact decision and no late approval: " + scenario);
            }
            finally { lifetime.Cancel(); await run.WaitAsync(TimeSpan.FromSeconds(4)); }
            check(presenter.ActiveDialog is null && bridge.Disconnections > 0,
                "native approval dialog and logical client are drained on owner close: " + scenario);
        }
    }

    private static Task Until(Func<bool> ready, int seconds = 3) => Until(() => Task.FromResult(ready()), seconds);
    private static async Task Until(Func<Task<bool>> ready, int seconds)
    {
        var watch = Stopwatch.StartNew();
        while (watch.Elapsed < TimeSpan.FromSeconds(seconds))
        {
            if (await ready()) return;
            await Task.Delay(10);
        }
        throw new TimeoutException("Native owned confirmation did not reach its readback condition.");
    }

    private static Button FindButton(DependencyObject root, string text)
    {
        if (root is Button button && button.Content?.ToString() == text) return button;
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(root); i++)
        {
            try { return FindButton(VisualTreeHelper.GetChild(root, i), text); }
            catch (InvalidOperationException) { }
        }
        throw new InvalidOperationException("Owned dialog button is not ready.");
    }

    private sealed class CountingClient(CoreIpcClient client) : IConfirmationClient
    {
        private readonly CoreConfirmationClient _inner = new(client);
        internal int Decisions, Disconnections;
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationList>> QueryAsync(string request, string owner, CancellationToken token) =>
            _inner.QueryAsync(request, owner, token);
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationAck>> DecideAsync(CoreRequestProtocol.ConfirmationDecisionRequest request, CancellationToken token)
        { Decisions++; return _inner.DecideAsync(request, token); }
        public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationDisconnected>> DisconnectAsync(string request, string owner, CancellationToken token)
        { Disconnections++; return _inner.DisconnectAsync(request, owner, token); }
    }

    private sealed class Fixture : IAsyncDisposable
    {
        internal string Pipe = "pluma_p16_native_" + Guid.NewGuid().ToString("N");
        private readonly string _root = Path.Combine(Path.GetTempPath(), "PLUMA-P16-" + Guid.NewGuid().ToString("N"));
        internal string Key => Path.Combine(_root, "Pluma", "ipc_secret.key");
        private Process _process = null!;
        private DateTime _created;
        private Task<string> _errors = null!, _output = null!;
        internal static async Task<Fixture> StartAsync()
        {
            var value = new Fixture();
            Directory.CreateDirectory(value._root);
            var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("PLUMA_TEST_PYTHON") ?? "python")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (string arg in new[] { "-u", Path.Combine(Directory.GetCurrentDirectory(), "PLUMA.UI", "CoreIpc.Tests", "fixture_server.py"),
                value.Pipe, value._root, "versioned", "normal" }) start.ArgumentList.Add(arg);
            value._process = Process.Start(start) ?? throw new InvalidOperationException("Owned fixture did not start.");
            value._created = value._process.StartTime.ToUniversalTime();
            value._errors = value._process.StandardError.ReadToEndAsync();
            value._output = Task.FromResult(string.Empty);
            try
            {
                using var budget = new CancellationTokenSource(TimeSpan.FromSeconds(7));
                string? ready = await value._process.StandardOutput.ReadLineAsync(budget.Token);
                value._output = value._process.StandardOutput.ReadToEndAsync();
                if (ready != "READY") throw new InvalidOperationException("Owned fixture was not ready.");
                return value;
            }
            catch { await value.DisposeAsync(); throw; }
        }
        public async ValueTask DisposeAsync()
        {
            try
            {
                if (!_process.HasExited)
                {
                    await _process.StandardInput.WriteLineAsync("stop"); await _process.StandardInput.FlushAsync();
                    try { await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(6)); }
                    catch (TimeoutException)
                    {
                        using var current = Process.GetProcessById(_process.Id);
                        if (current.StartTime.ToUniversalTime() != _created ||
                            !string.Equals(Path.GetFileNameWithoutExtension(current.MainModule?.FileName),
                                Path.GetFileNameWithoutExtension(_process.StartInfo.FileName), StringComparison.OrdinalIgnoreCase))
                            throw new InvalidOperationException("Owned fixture identity cannot be verified.");
                        _process.Kill(true); await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(3));
                    }
                }
                string errors = await _errors; await _output;
                if (_process.ExitCode != 0) throw new InvalidOperationException("Owned fixture cleanup failed: " + errors);
            }
            finally
            {
                _process.Dispose();
                if (File.Exists(Key)) File.Delete(Key);
                string keyDir = Path.GetDirectoryName(Key)!;
                if (Directory.Exists(keyDir) && !Directory.EnumerateFileSystemEntries(keyDir).Any()) Directory.Delete(keyDir);
                if (Directory.Exists(_root) && !Directory.EnumerateFileSystemEntries(_root).Any()) Directory.Delete(_root);
            }
        }
    }
}
