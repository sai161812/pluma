using System;
using System.Threading;
using NAudio.Wave;

namespace PLUMA.UI
{
    // Preview-only capture adapter. Production should feed the same spectrum API
    // from the existing voice worker rather than opening a second microphone.
    public sealed class MicrophoneSpectrumSource : IDisposable
    {
        private readonly WaveInEvent _capture;
        private readonly double[] _samples = new double[AudioSpectrumAnalyzer.WindowSize];
        private int _filled;
        private int _stopping;
        private bool _started;
        private AudioSpectrumFrame? _latest;
        private string? _error;

        public MicrophoneSpectrumSource()
        {
            _capture = new WaveInEvent
            {
                DeviceNumber = -1, // Windows default input (WAVE_MAPPER).
                WaveFormat = new WaveFormat(AudioSpectrumAnalyzer.SampleRate, 16, 1),
                BufferMilliseconds = 32,
                NumberOfBuffers = 3
            };
            _capture.DataAvailable += OnData;
            _capture.RecordingStopped += OnStopped;
        }

        public string? Error => Volatile.Read(ref _error);
        public AudioSpectrumFrame? TakeLatest() => Interlocked.Exchange(ref _latest, null);

        public void Start()
        {
            if (_started || Volatile.Read(ref _stopping) != 0)
                throw new InvalidOperationException("Capture has already started or stopped.");
            try
            {
                _capture.StartRecording();
                _started = true;
            }
            catch
            {
                Interlocked.Exchange(ref _stopping, 1);
                Release();
                throw;
            }
        }

        private void OnData(object? sender, WaveInEventArgs e)
        {
            if (Volatile.Read(ref _stopping) != 0) return;
            for (int i = 0; i + 1 < e.BytesRecorded; i += 2)
            {
                if (Volatile.Read(ref _stopping) != 0) return;
                short pcm = (short)(e.Buffer[i] | (e.Buffer[i + 1] << 8));
                _samples[_filled++] = pcm / 32768.0;
                if (_filled != _samples.Length) continue;
                Interlocked.Exchange(ref _latest, AudioSpectrumAnalyzer.Analyze(_samples));
                // 50% overlap: a 64 ms window, a new result every 32 ms.
                Array.Copy(_samples, _samples.Length / 2, _samples, 0, _samples.Length / 2);
                _filled = _samples.Length / 2;
            }
        }

        private void OnStopped(object? sender, StoppedEventArgs e)
        {
            bool unexpected = Interlocked.Exchange(ref _stopping, 1) == 0;
            if (unexpected)
                Volatile.Write(ref _error, e.Exception == null
                    ? "Microphone stopped. Reopen the preview to retry."
                    : "Microphone unavailable. Check Windows microphone access and the input device.");
            Release();
        }

        private void Release()
        {
            _capture.DataAvailable -= OnData;
            _capture.RecordingStopped -= OnStopped;
            _capture.Dispose();
            Array.Clear(_samples);
            Interlocked.Exchange(ref _latest, null);
        }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _stopping, 1) != 0) return;
            if (_started)
                _capture.StopRecording(); // Release only after its callback thread exits.
            else
                Release();
        }
    }
}
