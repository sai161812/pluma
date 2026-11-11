using System;
using System.Diagnostics;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal sealed record RuntimeView(CoreRequestProtocol.RuntimeTask[] Tasks, bool Connected, double? RoundTripMs,string? CoreInstanceId=null,bool? CoreReady=null);

/// <summary>One shell-owned observer. A missing snapshot never proves task completion.</summary>
internal sealed class RuntimeController(Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.RuntimeSnapshot>>> read,
    TimeSpan? interval = null,
    Func<string, CancellationToken, Task<CoreRequestResult<CoreRequestProtocol.PerceptionSnapshot>>>? perception = null,
    TimeProvider? clock = null)
{
    internal RuntimeView View { get; private set; } = new([], false, null);
    internal event Action<RuntimeView>? Changed;
    internal event Action<CoreRequestProtocol.PerceptionSnapshot?>? PerceptionChanged;
    internal event Action<CoreRequestProtocol.WorkerTermination>? WorkerTerminated;
    internal event Action<DateTimeOffset>? TextRequested;
    private string? _lastTextActivation;
    private readonly HashSet<string> _seen = new();
    private readonly Queue<string> _seenOrder = new();
    private bool _initialized;
    private int _running, _polling;
    private long _perceptionUntil;
    private readonly TimeProvider _clock=clock??TimeProvider.System;
    internal void NotePerceptionActivity()=>Interlocked.Exchange(ref _perceptionUntil,
        _clock.GetTimestamp()+checked(3*_clock.TimestampFrequency));
    internal async Task PollOnceAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _polling, 1) != 0) throw new InvalidOperationException("Runtime poll already owned.");
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(token);
        budget.CancelAfter(TimeSpan.FromSeconds(3));
        try
        {
            var timer = Stopwatch.StartNew();
            var response = await read(Guid.NewGuid().ToString("D"), budget.Token);
            budget.Token.ThrowIfCancellationRequested();
            if (response.IsSuccess)
            {
                foreach (var proof in response.Response!.Terminations)
                    if (_seen.Add(proof.Key))
                    {
                        _seenOrder.Enqueue(proof.Key);
                        if (_seenOrder.Count > 512) _seen.Remove(_seenOrder.Dequeue());
                        if (_initialized) WorkerTerminated?.Invoke(proof);
                    }
                var snapshot=response.Response!;
                if(snapshot.TextActivationId is not null && snapshot.TextActivationId!=_lastTextActivation)
                {
                    _lastTextActivation=snapshot.TextActivationId;
                    if(DateTimeOffset.TryParse(snapshot.TextActivationUtc,out var requested))
                    {
                        var age=DateTimeOffset.UtcNow-requested;
                        if(age>=TimeSpan.Zero && age<=TimeSpan.FromSeconds(3))TextRequested?.Invoke(requested);
                    }
                }
                _initialized = true;
            }
            View = response.IsSuccess ? new(response.Response!.Tasks, true, timer.Elapsed.TotalMilliseconds,response.Response.CoreInstanceId,response.Response.CoreReady) : new([], false, null);
            Changed?.Invoke(View);
            if (perception is not null)
            {
                if(Array.Exists(View.Tasks,task=>task.State=="RUNNING"))NotePerceptionActivity();
                if (View.Connected && View.CoreReady == true && _clock.GetTimestamp()<Interlocked.Read(ref _perceptionUntil))
                {
                    string id = Guid.NewGuid().ToString("D");
                    var frame = await perception(id, budget.Token);
                    budget.Token.ThrowIfCancellationRequested();
                    PerceptionChanged?.Invoke(frame.IsSuccess && frame.Response!.RequestId == id ? frame.Response : null);
                }
                else PerceptionChanged?.Invoke(null);
            }
        }
        finally { Interlocked.Exchange(ref _polling, 0); }
    }
    internal async Task RunAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _running, 1) != 0) throw new InvalidOperationException("Runtime observer already owned.");
        try
        {
            while (!token.IsCancellationRequested)
            {
                try { await PollOnceAsync(token); }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch { View = new([], false, null); Changed?.Invoke(View); PerceptionChanged?.Invoke(null); }
                await Task.Delay(interval ?? TimeSpan.FromMilliseconds(250), token);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        finally { PerceptionChanged?.Invoke(null); Interlocked.Exchange(ref _running, 0); }
    }
}
