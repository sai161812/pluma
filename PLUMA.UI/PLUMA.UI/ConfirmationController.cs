using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal interface IConfirmationClient
{
    Task<CoreRequestResult<CoreRequestProtocol.ConfirmationList>> QueryAsync(string requestId, string clientId, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.ConfirmationAck>> DecideAsync(CoreRequestProtocol.ConfirmationDecisionRequest request, CancellationToken token);
    Task<CoreRequestResult<CoreRequestProtocol.ConfirmationDisconnected>> DisconnectAsync(string requestId, string clientId, CancellationToken token);
}

internal sealed class CoreConfirmationClient(CoreIpcClient client) : IConfirmationClient
{
    public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationList>> QueryAsync(string requestId, string clientId, CancellationToken token) =>
        client.GetConfirmationsAsync(requestId, clientId, token);
    public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationAck>> DecideAsync(CoreRequestProtocol.ConfirmationDecisionRequest request, CancellationToken token) =>
        client.DecideConfirmationAsync(request, token);
    public Task<CoreRequestResult<CoreRequestProtocol.ConfirmationDisconnected>> DisconnectAsync(string requestId, string clientId, CancellationToken token) =>
        client.DisconnectConfirmationsAsync(requestId, clientId, token);
}

internal interface IConfirmationPresenter
{
    Task<bool?> ShowAsync(CoreRequestProtocol.ConfirmationView view, CancellationToken token);
}

/// <summary>One window-owned loop/dialog, with fresh backend readback before each decision.</summary>
internal sealed class ConfirmationController(IConfirmationClient client, IConfirmationPresenter presenter,
    TimeSpan? pollInterval = null)
{
    private readonly TimeSpan _poll = pollInterval ?? TimeSpan.FromMilliseconds(250);
    private readonly Dictionary<string, DateTimeOffset> _seen = new();
    private CancellationTokenSource? _dialogLifetime;
    private Task<bool?>? _dialog;
    private CoreRequestProtocol.ConfirmationView? _view;
    private int _running;
    internal string ClientId { get; private set; } = Guid.NewGuid().ToString("D");
    internal string? LastFailure { get; private set; }
    private static string Id() => Guid.NewGuid().ToString("D");

    internal async Task RunAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _running, 1) != 0) throw new InvalidOperationException("Confirmation owner already running.");
        try
        {
            while (!token.IsCancellationRequested)
            {
                var response = await client.QueryAsync(Id(), ClientId, token);
                if (!response.IsSuccess)
                {
                    LastFailure = "Approval connection unavailable.";
                    await EndDialogAsync();
                    await DisconnectAsync();
                    ClientId = Id(); _seen.Clear();
                    await Task.Delay(TimeSpan.FromSeconds(1), token);
                    continue;
                }
                var pending = response.Response!.Confirmations;
                var now = DateTimeOffset.UtcNow;
                foreach (string key in _seen.Where(pair => pair.Value <= now).Select(pair => pair.Key).ToArray()) _seen.Remove(key);
                if (_view is not null && !pending.Any(item => SameMaterial(item, _view) && IsLive(item, now)))
                    await EndDialogAsync();
                if (_dialog is { IsCompleted: true } && _view is not null)
                {
                    var view = _view;
                    bool? approved;
                    try { approved = await _dialog; }
                    catch { approved = null; LastFailure = "Approval dialog unavailable."; }
                    _dialogLifetime?.Dispose(); _dialogLifetime = null; _dialog = null; _view = null;
                    if (approved.HasValue && !token.IsCancellationRequested && IsLive(view, DateTimeOffset.UtcNow))
                    {
                        // This fresh query still contains the exact displayed call. The
                        // broker and registry independently recheck STOP and the binding.
                        var result = await client.DecideAsync(new(Id(), ClientId, view.TaskId,
                            view.ConfirmationId, view.Binding, approved.Value), token);
                        if (!result.IsSuccess || !result.Response!.Accepted)
                            LastFailure = "Approval could not be recorded. Check task history.";
                    }
                }
                if (_dialog is null)
                {
                    var next = pending.FirstOrDefault(item => !_seen.ContainsKey(item.ConfirmationId) && IsLive(item, DateTimeOffset.UtcNow));
                    if (next is not null)
                    {
                        if (_seen.Count >= 256) throw new InvalidOperationException("Confirmation display capacity reached.");
                        _seen[next.ConfirmationId] = DateTimeOffset.Parse(next.ExpiresAt);
                        _view = next;
                        _dialogLifetime = CancellationTokenSource.CreateLinkedTokenSource(token);
                        _dialogLifetime.CancelAfter(DateTimeOffset.Parse(next.ExpiresAt) - DateTimeOffset.UtcNow);
                        _dialog = presenter.ShowAsync(next, _dialogLifetime.Token);
                    }
                }
                await Task.Delay(_poll, token);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        catch { LastFailure = "Approval connection closed safely."; }
        finally
        {
            await EndDialogAsync();
            await DisconnectAsync();
            _seen.Clear(); Interlocked.Exchange(ref _running, 0);
        }
    }

    private async Task EndDialogAsync()
    {
        _dialogLifetime?.Cancel();
        if (_dialog is not null) try { await _dialog; } catch { }
        _dialogLifetime?.Dispose(); _dialogLifetime = null; _dialog = null; _view = null;
    }

    private async Task DisconnectAsync()
    {
        using var budget = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        try { await client.DisconnectAsync(Id(), ClientId, budget.Token); } catch { }
    }

    private static bool IsLive(CoreRequestProtocol.ConfirmationView view, DateTimeOffset now) =>
        DateTimeOffset.TryParse(view.ExpiresAt, out var expires) && expires > now;

    private static bool SameMaterial(CoreRequestProtocol.ConfirmationView a, CoreRequestProtocol.ConfirmationView b) =>
        a.ConfirmationId == b.ConfirmationId && a.TaskId == b.TaskId && a.Binding == b.Binding && a.Tool == b.Tool &&
        a.Risk == b.Risk && a.Prompt == b.Prompt && a.TargetSummary == b.TargetSummary && a.ExpiresAt == b.ExpiresAt &&
        a.Arguments.GetRawText() == b.Arguments.GetRawText();
}

internal static class ConfirmationPresentation
{
    internal static string Arguments(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            return Render(doc.RootElement);
        }
        catch (JsonException) { return json; } // existing gallery-only plain text
    }
    private static string Render(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.Object => string.Join(Environment.NewLine, value.EnumerateObject().Select(p =>
            p.Name.Replace('_', ' ') + ": " + Render(p.Value))),
        JsonValueKind.Array => string.Join(Environment.NewLine, value.EnumerateArray().Select(Render)),
        JsonValueKind.String => value.GetString() ?? string.Empty,
        JsonValueKind.Null => "Not set", JsonValueKind.True => "Yes", JsonValueKind.False => "No",
        _ => value.GetRawText()
    };
}
