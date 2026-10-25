using System;
using Microsoft.UI.Dispatching;

namespace PLUMA.UI
{
    /// <summary>
    /// Temporary mock driver for VoiceOverlay. Keep this outside the reusable control.
    /// Later PLUMA backend events replace this generator.
    /// </summary>
    public sealed class VoiceOverlayPreviewGenerator
    {
        private static readonly string[] TranscriptSteps =
        {
            "Open",
            "Open Visual",
            "Open Visual Studio",
            "Open Visual Studio and",
            "Open Visual Studio and run",
            "Open Visual Studio and run the PLUMA project, then locate the latest activity report inside the Downloads folder, open the report, compare it with yesterday's version, and summarize the differences clearly"
        };

        private const double SilenceHoldSeconds = 1.7;
        private const double SpeechSeconds = 4.0;
        private const double TimeoutSeconds = 1.5;
        private const double CommittedHoldSeconds = 2.2;
        private const double HiddenHoldSeconds = 0.7;

        private readonly DispatcherQueueTimer _timer;
        private double _elapsed;
        private bool _started;

        public VoiceOverlayPreviewGenerator(DispatcherQueue dispatcher)
        {
            _timer = dispatcher.CreateTimer();
            _timer.Interval = TimeSpan.FromMilliseconds(16);
            _timer.Tick += OnTick;
        }

        public event EventHandler<VoiceOverlayPreviewFrame>? FrameReady;

        public void Start()
        {
            if (_started)
            {
                return;
            }

            _started = true;
            _elapsed = 0;
            _timer.Start();
        }

        public void Stop()
        {
            _timer.Stop();
            _started = false;
        }

        private void OnTick(DispatcherQueueTimer sender, object args)
        {
            _elapsed += _timer.Interval.TotalSeconds;
            FrameReady?.Invoke(this, BuildFrame(_elapsed));
        }

        private static VoiceOverlayPreviewFrame BuildFrame(double t)
        {
            double speechStart = SilenceHoldSeconds;
            double timeoutStart = speechStart + SpeechSeconds;
            double committedStart = timeoutStart + TimeoutSeconds;
            double hiddenStart = committedStart + CommittedHoldSeconds;
            double cycle = hiddenStart + HiddenHoldSeconds;
            double local = t % cycle;

            if (local < speechStart)
            {
                return new VoiceOverlayPreviewFrame(
                    VoiceOverlayState.ListeningSilence,
                    Amplitude: 0.0,
                    FinalTranscript: string.Empty,
                    PartialTranscript: string.Empty,
                    SilenceProgress: 0);
            }

            if (local < timeoutStart)
            {
                double speechT = local - speechStart;
                ApplyTranscriptStep(speechT, out string finalText, out string partialText);
                return new VoiceOverlayPreviewFrame(
                    VoiceOverlayState.ListeningSpeech,
                    Amplitude: SpeechAmplitude(speechT),
                    FinalTranscript: finalText,
                    PartialTranscript: partialText,
                    SilenceProgress: 0);
            }

            if (local < committedStart)
            {
                double timeoutT = local - timeoutStart;
                ApplyTranscriptStep(SpeechSeconds, out string finalText, out string partialText);
                return new VoiceOverlayPreviewFrame(
                    VoiceOverlayState.SilenceTimeout,
                    Amplitude: 0.04,
                    FinalTranscript: finalText,
                    PartialTranscript: partialText,
                    SilenceProgress: Math.Clamp(timeoutT / TimeoutSeconds, 0, 1));
            }

            if (local < hiddenStart)
            {
                return new VoiceOverlayPreviewFrame(
                    VoiceOverlayState.Committed,
                    Amplitude: 0,
                    FinalTranscript: TranscriptSteps[^1],
                    PartialTranscript: string.Empty,
                    SilenceProgress: 0);
            }

            return new VoiceOverlayPreviewFrame(
                VoiceOverlayState.Hidden,
                Amplitude: 0,
                FinalTranscript: string.Empty,
                PartialTranscript: string.Empty,
                SilenceProgress: 0);
        }

        private static void ApplyTranscriptStep(double speechT, out string finalText, out string partialText)
        {
            int stepCount = TranscriptSteps.Length;
            double stepDuration = SpeechSeconds / stepCount;
            int index = Math.Clamp((int)(speechT / stepDuration), 0, stepCount - 1);

            string current = TranscriptSteps[index];
            string previous = index == 0 ? string.Empty : TranscriptSteps[index - 1];

            if (string.IsNullOrEmpty(previous))
            {
                finalText = string.Empty;
                partialText = current;
                return;
            }

            finalText = previous;
            partialText = current.Length > previous.Length
                ? current[previous.Length..].TrimStart()
                : current;
        }

        private static double SpeechAmplitude(double speechT)
        {
            double env = 0.40 + 0.18 * Math.Sin(speechT * 1.65);
            double pulse = 0.16 * (0.5 + 0.5 * Math.Sin(speechT * 6.8 + 0.35));
            double swell = 0.18 * Math.Max(0.0, Math.Sin(speechT * 2.05 + 0.6));
            double breath = 0.10 * Math.Sin(speechT * 10.4 + 1.1);
            return Math.Clamp(env + pulse + swell + breath, 0.10, 0.85);
        }
    }

    public readonly record struct VoiceOverlayPreviewFrame(
        VoiceOverlayState VoiceState,
        double Amplitude,
        string FinalTranscript,
        string PartialTranscript,
        double SilenceProgress);
}
