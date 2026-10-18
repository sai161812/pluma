using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace PLUMA.UI
{
    public sealed partial class VoiceListeningRing : UserControl
    {
        public static readonly DependencyProperty AmplitudeProperty =
            DependencyProperty.Register(nameof(Amplitude), typeof(double),
                typeof(VoiceListeningRing), new PropertyMetadata(0.0));
        public static readonly DependencyProperty IsAnimatingProperty =
            DependencyProperty.Register(nameof(IsAnimating), typeof(bool),
                typeof(VoiceListeningRing), new PropertyMetadata(true, OnAnimationChanged));

        private const int Count = 88;
        private readonly Line[] _bars = new Line[Count];
        private readonly double[] _levels = new double[Count];
        private readonly double[] _bands = new double[AudioSpectrumAnalyzer.BandCount];
        private readonly SolidColorBrush _brush = new(Color.FromArgb(255, 230, 230, 230));
        private bool _built;
        private bool _hooked;
        private bool _hasSpectrum;
        private long _lastFrame;
        private long _lastSpectrum;

        public VoiceListeningRing()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += (_, _) => StopRendering();
        }

        public double Amplitude
        {
            get => (double)GetValue(AmplitudeProperty);
            set => SetValue(AmplitudeProperty, value);
        }
        public bool IsAnimating
        {
            get => (bool)GetValue(IsAnimatingProperty);
            set => SetValue(IsAnimatingProperty, value);
        }

        // Call on the UI thread. Copy data so the producer may reuse its buffer.
        public void SetSpectrum(ReadOnlySpan<double> bands)
        {
            if (bands.Length != _bands.Length)
                throw new ArgumentException("Expected 32 spectrum bands.", nameof(bands));
            for (int i = 0; i < bands.Length; i++)
                _bands[i] = double.IsFinite(bands[i]) ? Math.Clamp(bands[i], 0, 1) : 0;
            _lastSpectrum = Environment.TickCount64;
            _hasSpectrum = true;
        }

        private static void OnAnimationChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            var ring = (VoiceListeningRing)d;
            if (ring.IsLoaded && ring.IsAnimating) ring.StartRendering();
            else ring.StopRendering();
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            if (!_built)
            {
                for (int i = 0; i < Count; i++)
                {
                    _bars[i] = new Line
                    {
                        Stroke = _brush, StrokeThickness = 1.25,
                        StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round,
                        IsHitTestVisible = false
                    };
                    RingCanvas.Children.Add(_bars[i]);
                }
                _built = true;
            }
            Draw();
            if (IsAnimating) StartRendering();
        }

        private void StartRendering()
        {
            if (_hooked) return;
            _lastFrame = Environment.TickCount64;
            CompositionTarget.Rendering += OnRendering;
            _hooked = true;
        }

        private void StopRendering()
        {
            if (_hooked) CompositionTarget.Rendering -= OnRendering;
            _hooked = false;
            Array.Clear(_levels);
            Array.Clear(_bands);
            _hasSpectrum = false;
            if (_built) Draw();
        }

        private void OnRendering(object? sender, object e)
        {
            long now = Environment.TickCount64;
            double dt = Math.Clamp((now - _lastFrame) / 1000.0, 0, 0.05);
            _lastFrame = now;
            bool fresh = now - _lastSpectrum < 250;
            for (int i = 0; i < Count; i++)
            {
                // Wrap ordered frequency bands around the circumference.
                // Cyclic interpolation makes the join continuous without mirroring.
                double position = i * _bands.Length / (double)Count;
                int left = (int)position;
                double fraction = position - left;
                double target = _hasSpectrum
                    ? (fresh ? _bands[left] * (1 - fraction) + _bands[(left + 1) % _bands.Length] * fraction : 0)
                    : (double.IsFinite(Amplitude) ? Math.Clamp(Amplitude, 0, 1) * 0.35 : 0);
                _levels[i] = VoiceWaveformMotion.Step(_levels[i], target, dt);
            }
            Draw();
        }

        private void Draw()
        {
            for (int i = 0; i < Count; i++)
            {
                double theta = 2 * Math.PI * i / Count;
                double extent = 0.55 + 7 * _levels[i];
                double inner = 49 - extent * 0.45;
                double outer = 49 + extent;
                _bars[i].X1 = 63 + Math.Cos(theta) * inner;
                _bars[i].Y1 = 63 + Math.Sin(theta) * inner;
                _bars[i].X2 = 63 + Math.Cos(theta) * outer;
                _bars[i].Y2 = 63 + Math.Sin(theta) * outer;
                _bars[i].Opacity = 0.18 + 0.68 * _levels[i];
            }
        }
    }
}
