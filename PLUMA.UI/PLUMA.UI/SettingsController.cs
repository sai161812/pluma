using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal sealed record SettingsView(CoreRequestProtocol.SettingsEditSnapshot? Saved,
    CoreRequestProtocol.SettingsSnapshot? Runtime, double DraftLimit, bool Busy, bool Connected,
    bool CanEdit, bool CanSave, bool CanCancel, string Message, string CommandMessage);

/// <summary>Shell-owned draft/read lifecycle. Writes use the shared command/STOP owner.</summary>
internal sealed class SettingsController(
    Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.SettingsEditSnapshot>>> read,
    Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.SettingsSnapshot>>> runtime,
    CommandController commands) : IAsyncDisposable
{
    private readonly object _gate = new();
    private readonly CancellationTokenSource _lifetime = new();
    private Task _work = Task.CompletedTask;
    private Task? _disposal;
    private CoreRequestProtocol.SettingsEditSnapshot? _saved;
    private CoreRequestProtocol.SettingsSnapshot? _runtime;
    private bool _closed, _busy, _connected;
    private double _draft = double.NaN;
    private string _message = "Reload to read settings.", _commandMessage = "";
    private string? _saveRequest;
    internal event Action<SettingsView>? Changed;
    private static string Id() => Guid.NewGuid().ToString("D");
    private bool Valid => double.IsFinite(_draft) && _draft == Math.Truncate(_draft) && _draft is >= 1 and <= 20;
    internal SettingsView View
    {
        get
        {
            lock (_gate)
            {
                bool edit = !_closed && !_busy && _connected && !commands.View.Pending;
                bool dirty = _saved is not null && _draft != _saved.Persisted.MaxPlanSteps;
                return new(_saved, _runtime, _draft, _busy, _connected, edit,
                    edit && dirty && Valid && commands.View.CanSubmit && _saved!.EditableFields.Contains("max_plan_steps"),
                    edit && dirty, _message, _commandMessage);
            }
        }
    }
    private void Publish() { if (!_closed) Changed?.Invoke(View); }
    internal void SetDraft(double value)
    {
        lock (_gate)
        {
            if (!View.CanEdit) return;
            _draft = value;
            _message = Valid ? "Unsaved changes. Core restart is required after saving." : "Enter a whole number from 1 to 20.";
        }
        Publish();
    }
    internal void CancelEdits()
    {
        lock (_gate)
        {
            if (!View.CanCancel) return;
            _draft = _saved!.Persisted.MaxPlanSteps; _message = Summary(_saved);
        }
        Publish();
    }
    private static string Summary(CoreRequestProtocol.SettingsEditSnapshot saved) => saved.RestartFields.Length == 0
        ? "Saved settings match the active configuration. Other controls are read-only."
        : "Saved changes require a Core restart. Active plan limit: " + saved.Effective.MaxPlanSteps + ".";

    internal Task RefreshAsync(CancellationToken owner) => Start(() => RefreshAndReconcileAsync(owner));
    private Task Start(Func<Task> operation)
    {
        lock (_gate)
        {
            if (_closed || _busy || !_work.IsCompleted) return _work;
            _busy = true; _work = RunAsync(operation);
        }
        Publish(); return _work;
    }
    private async Task RunAsync(Func<Task> operation)
    {
        await Task.Yield();
        try { await operation(); }
        catch (Exception)
        {
            lock (_gate) { _connected = false; _saved = null; _runtime = null; _draft = double.NaN; _message = "Settings are unavailable. Reload to try again."; }
        }
        finally { lock (_gate) _busy = false; Publish(); }
    }
    private async Task RefreshAndReconcileAsync(CancellationToken owner)
    {
        if (_saveRequest is not null && commands.View.RequestId == _saveRequest && commands.View.Pending)
            await commands.ReconcileAsync().WaitAsync(_lifetime.Token);
        await ReadAsync(owner);
    }
    private async Task ReadAsync(CancellationToken owner)
    {
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(owner, _lifetime.Token);
        budget.CancelAfter(TimeSpan.FromSeconds(3));
        var saved = await read(Id(), budget.Token);
        for (int retry=0; saved.Failure == CoreConnectionFailure.Busy && retry<3; retry++)
        { await Task.Delay(50, budget.Token); saved = await read(Id(), budget.Token); }
        var active = await runtime(Id(), budget.Token);
        for (int retry=0; active.Failure == CoreConnectionFailure.Busy && retry<3; retry++)
        { await Task.Delay(50, budget.Token); active = await runtime(Id(), budget.Token); }
        budget.Token.ThrowIfCancellationRequested();
        if (!saved.IsSuccess || !active.IsSuccess) throw new InvalidOperationException("Settings readback unavailable.");
        lock (_gate)
        {
            if (_closed) return;
            _saved = saved.Response!; _runtime = active.Response!; _draft = _saved.Persisted.MaxPlanSteps;
            _connected = true; _message = Summary(_saved);
            if (_saveRequest is not null && commands.View.RequestId == _saveRequest) _commandMessage = commands.View.Message;
        }
        commands.SetConnected(true);
    }
    internal Task SaveAsync(CancellationToken owner)
    {
        lock (_gate)
        {
            if (owner.IsCancellationRequested || !View.CanSave) return Task.CompletedTask;
            int limit = (int)_draft; string revision = _saved!.Revision;
            _message = "Sending settings for confirmation. Saving is not yet verified.";
            _commandMessage = "";
            _busy = true;
            string? previous = commands.View.RequestId;
            // Claim the shared submission/fence synchronously. A STOP before
            // the first UI await must also fence this settings request.
            Task pending = commands.SubmitSettingsAsync(revision, limit);
            if (commands.View.RequestId == previous)
            {
                _busy = false; _message = "Another request owns command admission. Try again after it ends.";
                Publish(); return Task.CompletedTask;
            }
            _saveRequest = commands.View.RequestId;
            _work = RunAsync(() => SaveAndReadAsync(pending, limit, owner));
        }
        Publish(); return _work;
    }
    private async Task SaveAndReadAsync(Task pending, int limit, CancellationToken owner)
    {
        owner.ThrowIfCancellationRequested(); _lifetime.Token.ThrowIfCancellationRequested();
        await pending.WaitAsync(_lifetime.Token);
        string outcome = commands.View.State;
        await ReadAsync(owner);
        lock (_gate)
        {
            _commandMessage = commands.View.Message;
            if (outcome != "Completed") _message = "Save was not verified as successful. Readback is shown; check Activity before repeating it.";
            else if (_saved!.Persisted.MaxPlanSteps != limit) _message = "Settings changed after the task. Readback shows the current saved value.";
        }
    }
    internal void OnCommandChanged(CommandView view)
    {
        lock (_gate)
        {
            if (_closed) return;
            if (_saveRequest == view.RequestId) _commandMessage = view.Message;
        }
        Publish();
    }
    public ValueTask DisposeAsync()
    {
        lock (_gate)
        {
            if (_disposal is null) { _closed = true; _lifetime.Cancel(); _disposal = DrainAsync(_work); }
            return new(_disposal);
        }
    }
    private async Task DrainAsync(Task pending)
    {
        await Task.Yield();
        try { await pending; }
        finally { Changed = null; _lifetime.Dispose(); }
    }
}
