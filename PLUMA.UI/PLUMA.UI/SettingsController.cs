using System;
using System.Linq;
using System.Text.Json;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal sealed record SettingsView(CoreRequestProtocol.SettingsEditSnapshot? Saved,
    CoreRequestProtocol.SettingsSnapshot? Runtime, double DraftLimit, bool Busy, bool Connected,
    bool CanEdit, bool CanSave, bool CanCancel, string Message, string CommandMessage, CoreRequestProtocol.SettingsEditValues? DraftValues, bool CanRecover);

/// <summary>Shell-owned draft/read lifecycle. Writes use the shared command/STOP owner.</summary>
internal sealed class SettingsController(
    Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.SettingsEditSnapshot>>> read,
    Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.SettingsSnapshot>>> runtime,
    CommandController commands) : IAsyncDisposable
{
    private static readonly JsonSerializerOptions SettingsJson=new(){PropertyNamingPolicy=JsonNamingPolicy.SnakeCaseLower};
    private readonly object _gate = new();
    private readonly CancellationTokenSource _lifetime = new();
    private Task _work = Task.CompletedTask;
    private Task? _disposal;
    private CoreRequestProtocol.SettingsEditSnapshot? _saved;
    private CoreRequestProtocol.SettingsSnapshot? _runtime;
    private bool _closed, _busy, _connected;
    private double _draft = double.NaN;
    private CoreRequestProtocol.SettingsEditValues? _advanced;
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
                bool available = !_closed && !_busy && _connected && !commands.View.Pending;
                bool edit = available && _saved?.PreviousRevision is null;
                bool dirty = _saved is not null && (_draft != _saved.Persisted.MaxPlanSteps || _advanced != _saved.Persisted);
                bool valid=Valid;
                if(valid && dirty) { try { BuildEdits().Fields(); } catch(Exception) { valid=false; } }
                return new(_saved, _runtime, _draft, _busy, _connected, edit,
                    edit && dirty && valid && commands.View.CanSubmit && _saved!.EditableFields.Contains("max_plan_steps"),
                    edit && dirty, _message, _commandMessage, _advanced, available && _saved?.PreviousRevision is not null && commands.View.CanSubmit);
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
    private CoreRequestProtocol.SettingsEdits BuildEdits()
    {
        var draft=JsonSerializer.SerializeToElement(_advanced! with { MaxPlanSteps=(int)_draft },SettingsJson);
        var persisted=JsonSerializer.SerializeToElement(_saved!.Persisted,SettingsJson);
        var fields=new Dictionary<string,JsonElement>();
        foreach(var key in _saved.EditableFields)
            if(draft.GetProperty(key).GetRawText()!=persisted.GetProperty(key).GetRawText()) fields[key]=draft.GetProperty(key).Clone();
        return JsonSerializer.Deserialize<CoreRequestProtocol.SettingsEdits>(JsonSerializer.Serialize(fields),SettingsJson)!;
    }
    internal void SetValues(CoreRequestProtocol.SettingsEditValues values)
    {
        lock(_gate) { if(!View.CanEdit)return; _advanced=values; _message="Unsaved settings. Core restart is required after saving."; }
        Publish();
    }
    internal void CancelEdits()
    {
        lock (_gate)
        {
            if (!View.CanCancel) return;
            _draft = _saved!.Persisted.MaxPlanSteps; _advanced=_saved.Persisted; _message = Summary(_saved);
        }
        Publish();
    }
    private static string Summary(CoreRequestProtocol.SettingsEditSnapshot saved) => saved.RestartFields.Length == 0
        ? "Saved settings match the active configuration. Locked safety settings remain enforced."
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
            lock (_gate) { _connected = false; _saved = null; _runtime = null; _advanced=null; _draft = double.NaN; _message = "Settings are unavailable. Reload to try again."; }
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
            _saved = saved.Response!; _runtime = active.Response!; _draft = _saved.Persisted.MaxPlanSteps; _advanced=_saved.Persisted;
            _connected = true; _message = Summary(_saved);
            if(_saved.PreviousRevision is not null)_message="Saved source is invalid. Restore previous valid settings only after confirmation. The rejected source will be preserved.";
            if (_saveRequest is not null && commands.View.RequestId == _saveRequest) _commandMessage = commands.View.Message;
        }
        commands.SetConnected(true);
    }
    internal Task RecoverAsync(CancellationToken owner)
    {
        lock(_gate) { if(!View.CanRecover)return Task.CompletedTask; return SubmitEdits(new(RecoverPrevious:true,RecoveryRevision:_saved!.PreviousRevision),owner); }
    }
    internal Task SaveAsync(CancellationToken owner)
    {
        lock(_gate) { if(!View.CanSave)return Task.CompletedTask; return SubmitEdits(BuildEdits(),owner); }
    }
    private Task SubmitEdits(CoreRequestProtocol.SettingsEdits edits, CancellationToken owner)
    {
        lock (_gate)
        {
            if (owner.IsCancellationRequested || _closed || _busy) return Task.CompletedTask;
            string revision = _saved!.Revision;
            _message = "Sending settings for confirmation. Saving is not yet verified.";
            _commandMessage = "";
            _busy = true;
            string? previous = commands.View.RequestId;
            // Claim the shared submission/fence synchronously. A STOP before
            // the first UI await must also fence this settings request.
            Task pending = commands.SubmitSettingsAsync(revision, edits);
            if (commands.View.RequestId == previous)
            {
                _busy = false; _message = "Another request owns command admission. Try again after it ends.";
                Publish(); return Task.CompletedTask;
            }
            _saveRequest = commands.View.RequestId;
            _work = RunAsync(() => SaveAndReadAsync(pending, edits, owner));
        }
        Publish(); return _work;
    }
    private async Task SaveAndReadAsync(Task pending, CoreRequestProtocol.SettingsEdits edits, CancellationToken owner)
    {
        owner.ThrowIfCancellationRequested(); _lifetime.Token.ThrowIfCancellationRequested();
        await pending.WaitAsync(_lifetime.Token);
        string outcome = commands.View.State;
        await ReadAsync(owner);
        lock (_gate)
        {
            _commandMessage = commands.View.Message;
            if (outcome != "Completed") _message = "Save was not verified as successful. Readback is shown; check Activity before repeating it.";
            else if (edits.RecoverPrevious!=true && edits.Fields().Any(field=>JsonSerializer.SerializeToElement(_saved!.Persisted,SettingsJson).GetProperty(field.Key).GetRawText()!=((JsonElement)field.Value).GetRawText())) _message = "Settings changed after the task. Readback shows the current saved value.";
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
