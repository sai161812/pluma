using System;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI;

internal sealed record VoiceObservation(CoreRequestProtocol.VoiceView? Voice, bool Connected, bool Reset);

/// <summary>One shell-owned, serialized transient observer. Never submits speech.</summary>
internal sealed class VoiceController(Func<string, string?, string?, CancellationToken,
    Task<CoreRequestResult<CoreRequestProtocol.VoiceSnapshot>>> read, TimeSpan? interval = null)
{
    internal VoiceObservation View { get; private set; } = new(null, false, true);
    internal event Action<VoiceObservation>? Changed;
    private string? _stream, _generation;
    private int _running, _polling;
    private void Clear()
    {
        _stream = _generation = null;
        View = new(null, false, true); Changed?.Invoke(View);
    }
    internal async Task PollOnceAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _polling, 1) != 0) throw new InvalidOperationException("Voice poll already owned.");
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(token);
        budget.CancelAfter(TimeSpan.FromSeconds(3));
        try
        {
            string id = Guid.NewGuid().ToString("D");
            var response = await read(id, _stream, _generation, budget.Token);
            budget.Token.ThrowIfCancellationRequested();
            if (!response.IsSuccess) { Clear(); return; }
            var value = response.Response!;
            bool reset = value.StreamId != _stream || value.Voice?.VoiceId != _generation;
            if (value.RequestId != id || value.ResetRequired != reset)
                throw new InvalidOperationException("Voice response scope changed.");
            if (!reset && View.Voice is { } old && value.Voice is { } next)
            {
                static int Order(string phase) => phase switch { "STARTING" => 0, "LISTENING" => 1, "DECODING" => 2, _ => 3 };
                if (old.TaskId != next.TaskId ||
                    Order(next.Phase) < Order(old.Phase) ||
                    old.Phase == "COMMITTED" && old.TaskRequestId != next.TaskRequestId ||
                    old.RecognitionId is not null && next.RecognitionId is not null && old.RecognitionId != next.RecognitionId ||
                    old.RecognitionId == next.RecognitionId && next.RecognitionSequence < old.RecognitionSequence ||
                    old.Phase is not ("STARTING" or "LISTENING" or "DECODING") && old.Phase != next.Phase)
                    throw new InvalidOperationException("Voice evidence regressed.");
            }
            _stream = value.StreamId; _generation = value.Voice?.VoiceId;
            View = new(value.Voice, true, reset); Changed?.Invoke(View);
        }
        catch { Clear(); throw; }
        finally { Interlocked.Exchange(ref _polling, 0); }
    }
    internal async Task RunAsync(CancellationToken token)
    {
        if (Interlocked.Exchange(ref _running, 1) != 0) throw new InvalidOperationException("Voice observer already owned.");
        try
        {
            while (!token.IsCancellationRequested)
            {
                try { await PollOnceAsync(token); }
                catch (OperationCanceledException) when (token.IsCancellationRequested) { break; }
                catch { /* PollOnce already cleared transient copy. */ }
                await Task.Delay(interval ?? TimeSpan.FromMilliseconds(150), token);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
        finally { Clear(); Interlocked.Exchange(ref _running, 0); }
    }
}
