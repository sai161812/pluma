using System;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI.Tests;

internal static class NativeP19VoiceChecks
{
    private static async Task Until(Func<bool> condition)
    {
        var timer = Stopwatch.StartNew();
        while (!condition() && timer.Elapsed.TotalSeconds < 5) await Task.Delay(20);
        if (!condition()) throw new TimeoutException("Owned P19 voice condition was not observed.");
    }
    internal static async Task RunAsync(Action<bool, string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("voice");
        await using var client = new CoreIpcClient(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        var shell = new MainWindow(new(fixture.Pipe, fixture.Key, TimeSpan.FromSeconds(3)));
        shell.Activate();
        VoiceOverlay? Overlay() => shell.Popups.Windows.Select(w => w.HostedContent).OfType<VoiceOverlay>().SingleOrDefault();
        VoiceOverlay overlay;
        try
        {
            await Until(() => shell.Dashboard is { IsLoaded: true });
            check(Overlay() is null, "production shell stays voice-cold before activation");
            await fixture.ControlVoiceAsync("voice_begin");
            await Until(() => Overlay() is { VoiceState: VoiceOverlayState.ListeningSpeech });
            overlay = Overlay()!;
            check(overlay.Amplitude > 0 && overlay.IsAnimating && overlay.PartialTranscript == "",
                "single native overlay receives measured capture activity without fake transcript");
            await fixture.ControlVoiceAsync("voice_silence");
            await Until(() => overlay.VoiceState == VoiceOverlayState.SilenceTimeout);
            check(overlay.SilenceProgress is > 0 and < 1, "native silence progress comes from actual fixture VAD frames");
            await fixture.ControlVoiceAsync("voice_decode");
            await Until(() => overlay.VoiceState == VoiceOverlayState.Recognizing && overlay.PartialTranscript.Length > 1000);
            check(!overlay.IsAnimating && overlay.FinalTranscript == "" && overlay.PartialTranscript.Contains("file_name.md"),
                "native decoding shows literal recognized fixture segments without commitment or microphone animation");
            var transcript = (LiveTranscriptionOverlay)overlay.FindName("LiveTranscriptHost");
            var text = (PopupMessageText)transcript.FindName("LiveTranscript");
            await Until(() => text.MessageScroll.ScrollableHeight > 10);
            check(text.DisplayText.Contains("file_name.md") && text.MessageScroll.ActualHeight <= 64.5,
                "literal transcript wraps inside the existing fixed voice viewport");
            await Until(() => text.MessageScroll.ScrollableHeight - text.MessageScroll.VerticalOffset < 2);
            int queuedLength = overlay.PartialTranscript.Length;
            // Order a real viewport move immediately after the next genuine
            // fixture update, before native layout consumes pending follow.
            long scrollHook = overlay.RegisterPropertyChangedCallback(VoiceOverlay.PartialTranscriptProperty,
                (_, _) => text.MessageScroll.ChangeView(null, 0, null, true));
            try
            {
                await fixture.ControlVoiceAsync("voice_more");
                await Until(() => overlay.PartialTranscript.Length > queuedLength && text.MessageScroll.VerticalOffset < 1);
                await Task.Delay(80);
                check(text.MessageScroll.VerticalOffset < 1, "manual reading cancels a queued native tail follow");
            }
            finally { overlay.UnregisterPropertyChangedCallback(VoiceOverlay.PartialTranscriptProperty, scrollHook); }
            text.MessageScroll.ChangeView(null, 0, null, true);
            await Until(() => text.MessageScroll.VerticalOffset < 1);
            double offset = text.MessageScroll.VerticalOffset;
            int earlierLength = overlay.PartialTranscript.Length;
            await fixture.ControlVoiceAsync("voice_more");
            await Until(() => overlay.PartialTranscript.Length > earlierLength);
            await Task.Delay(80);
            Console.WriteLine($"Owned voice reader: same={ReferenceEquals(Overlay(), overlay)}, before={offset}, after={text.MessageScroll.VerticalOffset}, extent={text.MessageScroll.ScrollableHeight}");
            check(ReferenceEquals(Overlay(), overlay) && Math.Abs(text.MessageScroll.VerticalOffset - offset) < 1,
                "new speech preserves the same overlay and earlier-text reading position");
            text.MessageScroll.ChangeView(null, text.MessageScroll.ScrollableHeight, null, true); await Task.Delay(80);
            int priorLength = overlay.PartialTranscript.Length;
            await fixture.ControlVoiceAsync("voice_more");
            await Until(() => overlay.PartialTranscript.Length > priorLength);
            await Until(() => text.MessageScroll.ScrollableHeight - text.MessageScroll.VerticalOffset < 2);
            check(true, "new speech follows only when the reader is at the tail");
            await fixture.ControlVoiceAsync("voice_commit");
            await Until(() => overlay.VoiceState == VoiceOverlayState.Committed);
            check(overlay.FinalTranscript == "fixture:read" && overlay.PartialTranscript == "" && !overlay.IsAnimating,
                "native committed state follows actual same-capsule orchestrator admission and final transcript");
            shell.NavigateForAcceptance(false); await Task.Delay(80); shell.NavigateForAcceptance(true);
            check(ReferenceEquals(Overlay(), overlay), "voice observer and native overlay survive page navigation once");
            await fixture.ControlVoiceAsync("voice_pause");
            await Until(() => Overlay() is null);
            check(overlay.FinalTranscript == "" && overlay.PartialTranscript == "", "disconnect clears text before native dismissal");
            await fixture.ControlVoiceAsync("voice_resume");
            await fixture.ControlVoiceAsync("voice_clarify");
            await Until(() => Overlay() is { VoiceState: VoiceOverlayState.Outcome } current &&
                ((PopupStatusIndicator)current.FindName("StatusHost")).Label == "Please repeat the command");
            check(Overlay()!.FinalTranscript == "" && Overlay()!.PartialTranscript == "", "low-confidence clarification never replays uncertain targets");
            await fixture.ControlVoiceAsync("voice_empty");
            await Until(() => ((PopupStatusIndicator)Overlay()!.FindName("StatusHost")).Label == "No speech detected");
            await fixture.ControlVoiceAsync("voice_deny");
            await Until(() => ((PopupStatusIndicator)Overlay()!.FindName("StatusHost")).Label == "Microphone access denied");
            check(!Overlay()!.IsAnimating, "native denial is truthful and does not animate capture");
            await fixture.ControlVoiceAsync("voice_timeout");
            await Until(() => ((PopupStatusIndicator)Overlay()!.FindName("StatusHost")).Label == "Voice timed out");
            check(Overlay()!.FinalTranscript == "" && !Overlay()!.IsAnimating, "native owned deadline never fabricates voice commitment");
            await fixture.ControlVoiceAsync("voice_begin");
            await Until(() => Overlay()!.IsAnimating);
            await client.StopAsync(Guid.NewGuid().ToString("D"), null, default);
            await Until(() => ((PopupStatusIndicator)Overlay()!.FindName("StatusHost")).Label == "Voice cancelled");
            check(Overlay()!.PartialTranscript == "" && !Overlay()!.IsAnimating, "priority STOP during capture clears and stops the single voice overlay");
            await fixture.ControlVoiceAsync("voice_begin");
            await fixture.ControlVoiceAsync("voice_decode");
            await Until(() => Overlay()!.VoiceState == VoiceOverlayState.Recognizing);
            await client.StopAsync(Guid.NewGuid().ToString("D"), null, default);
            await Until(() => ((PopupStatusIndicator)Overlay()!.FindName("StatusHost")).Label == "Voice cancelled");
            check(Overlay()!.PartialTranscript == "", "priority STOP during recognition prevents final text revival");
        }
        catch (Exception error) { Console.Error.WriteLine("P19 voice failure before fixture teardown: " + error); throw; }
        finally { shell.Close(); await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(5)); }
        check(shell.ObservationLifetime.IsCompleted, "shell shutdown joins its voice observer and native popup lifetime");
    }
}
