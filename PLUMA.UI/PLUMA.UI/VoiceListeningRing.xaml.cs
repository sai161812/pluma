using System;
using Microsoft.UI;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace PLUMA.UI
{
    /// <summary>
    /// Compact listening ring. Perimeter deforms with amplitude; colour travels
    /// around the circumference. Does not capture audio.
    /// </summary>
    public sealed partial class VoiceListeningRing : UserControl
    {
        public static readonly DependencyProperty AmplitudeProperty =
            DependencyProperty.Register(
                nameof(Amplitude),
                typeof(double),
                typeof(VoiceListeningRing),
                new PropertyMetadata(0.0));

        public static readonly DependencyProperty IsAnimatingProperty =
            DependencyProperty.Register(
                nameof(IsAnimating),
                typeof(bool),
                typeof(VoiceListeningRing),
                new PropertyMetadata(true, OnIsAnimatingChanged));

        private const int SegmentCount = 80;
        private const double CanvasSize = 115.0;
        private const double BaseRadius = 46.0;
        private const double MaxDeformPx = 8.0;
        private const double StrokeThickness = 1.4;
        private const double EnergyStrokeThickness = 1.8;
        private const double AttackSeconds = 0.11;
        private const double ReleaseSeconds = 0.24;
        private const double ColorPeriodSeconds = 9.0;

        private static readonly Color[] Palette =
        {
            Color.FromArgb(255, 86, 132, 196),
            Color.FromArgb(255, 72, 168, 186),
            Color.FromArgb(255, 122, 102, 186),
            Color.FromArgb(255, 168, 96, 148),
            Color.FromArgb(255, 186, 148, 86),
            Color.FromArgb(255, 96, 156, 118)
        };

        private readonly Line[] _segments = new Line[SegmentCount];
        private readonly SolidColorBrush[] _brushes = new SolidColorBrush[SegmentCount];
        private readonly Line[] _energySegments = new Line[SegmentCount];
        private readonly SolidColorBrush[] _energyBrushes = new SolidColorBrush[SegmentCount];

        private bool _hooked;
        private bool _built;
        private double _smoothedAmplitude;
        private double _colorPhase;
        private double _wavePhaseA;
        private double _wavePhaseB;
        private double _wavePhaseC;
        private long _lastTicks;

        public VoiceListeningRing()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += OnUnloaded;
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

        private static void OnIsAnimatingChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceListeningRing ring)
            {
                ring.SyncRenderingHook();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            EnsureRing();
            _lastTicks = Environment.TickCount64;
            SyncRenderingHook();
            RenderFrame(0);
        }

        private void OnUnloaded(object sender, RoutedEventArgs e)
        {
            UnhookRendering();
        }

        private void SyncRenderingHook()
        {
            if (IsLoaded && IsAnimating)
            {
                HookRendering();
            }
            else
            {
                UnhookRendering();
            }
        }

        private void HookRendering()
        {
            if (_hooked)
            {
                return;
            }

            CompositionTarget.Rendering += OnRendering;
            _hooked = true;
            _lastTicks = Environment.TickCount64;
        }

        private void UnhookRendering()
        {
            if (!_hooked)
            {
                return;
            }

            CompositionTarget.Rendering -= OnRendering;
            _hooked = false;
        }

        private void EnsureRing()
        {
            if (_built)
            {
                return;
            }

            for (int i = 0; i < SegmentCount; i++)
            {
                var energyBrush = new SolidColorBrush(Palette[0])
                {
                    Opacity = 0.68
                };
                _energyBrushes[i] = energyBrush;

                var energyLine = new Line
                {
                    Stroke = energyBrush,
                    StrokeThickness = EnergyStrokeThickness,
                    StrokeStartLineCap = PenLineCap.Round,
                    StrokeEndLineCap = PenLineCap.Round
                };
                _energySegments[i] = energyLine;
                RingCanvas.Children.Add(energyLine);

                var brush = new SolidColorBrush(Palette[0]);
                _brushes[i] = brush;

                var line = new Line
                {
                    Stroke = brush,
                    StrokeThickness = StrokeThickness,
                    StrokeStartLineCap = PenLineCap.Round,
                    StrokeEndLineCap = PenLineCap.Round
                };

                _segments[i] = line;
                RingCanvas.Children.Add(line);
            }

            _built = true;
        }

        private void OnRendering(object? sender, object e)
        {
            long now = Environment.TickCount64;
            double dt = Math.Clamp((now - _lastTicks) / 1000.0, 0.0, 0.05);
            _lastTicks = now;
            RenderFrame(dt);
        }

        private void RenderFrame(double dt)
        {
            if (!_built)
            {
                return;
            }

            double target = Math.Clamp(Amplitude, 0.0, 1.0);
            if (target <= 0.02)
            {
                _smoothedAmplitude = 0.0;
            }
            else
            {
                double tau = target > _smoothedAmplitude ? AttackSeconds : ReleaseSeconds;
                double k = 1.0 - Math.Exp(-dt / Math.Max(tau, 0.001));
                _smoothedAmplitude += (target - _smoothedAmplitude) * k;
            }

            _colorPhase = (_colorPhase + dt / ColorPeriodSeconds) % 1.0;
            _wavePhaseA += dt * 1.15;
            _wavePhaseB += dt * 0.82;
            _wavePhaseC += dt * 0.54;

            double cx = CanvasSize / 2.0;
            double cy = CanvasSize / 2.0;
            double amp = _smoothedAmplitude;

            for (int i = 0; i < SegmentCount; i++)
            {
                int next = (i + 1) % SegmentCount;
                GetPoint(i, cx, cy, out double x1, out double y1);
                GetPoint(next, cx, cy, out double x2, out double y2);

                GetEnergyBasePoint(i, cx, cy, out double ex1, out double ey1);
                GetEnergyPoint(i, amp, cx, cy, out double ex2, out double ey2);

                _segments[i].X1 = x1;
                _segments[i].Y1 = y1;
                _segments[i].X2 = x2;
                _segments[i].Y2 = y2;
                _brushes[i].Color = SamplePalette((i / (double)SegmentCount) + _colorPhase);

                _energySegments[i].X1 = ex1;
                _energySegments[i].Y1 = ey1;
                _energySegments[i].X2 = ex2;
                _energySegments[i].Y2 = ey2;
                _energyBrushes[i].Color = SamplePalette((i / (double)SegmentCount) + _colorPhase + 0.04);

            }
        }

        private void GetPoint(int index, double cx, double cy, out double x, out double y)
        {
            double theta = (Math.PI * 2.0 * index) / SegmentCount;

            x = cx + Math.Cos(theta) * BaseRadius;
            y = cy + Math.Sin(theta) * BaseRadius;
        }

        private void GetEnergyPoint(int index, double amp, double cx, double cy, out double x, out double y)
        {
            double theta = (Math.PI * 2.0 * index) / SegmentCount;

            double wave =
                0.55 * Math.Sin(2.0 * theta + _wavePhaseA) +
                0.30 * Math.Sin(3.0 * theta + _wavePhaseB) +
                0.15 * Math.Sin(5.0 * theta + _wavePhaseC);

            double displacement = amp * MaxDeformPx * Math.Max(0.0, wave);
            double radius = BaseRadius + 2.4 + displacement;

            x = cx + Math.Cos(theta) * radius;
            y = cy + Math.Sin(theta) * radius;
        }

        private void GetEnergyBasePoint(int index, double cx, double cy, out double x, out double y)
        {
            double theta = (Math.PI * 2.0 * index) / SegmentCount;
            double radius = BaseRadius + 2.4;

            x = cx + Math.Cos(theta) * radius;
            y = cy + Math.Sin(theta) * radius;
        }

        private static Color SamplePalette(double t)
        {
            t = t - Math.Floor(t);
            double scaled = t * Palette.Length;
            int i0 = (int)Math.Floor(scaled) % Palette.Length;
            int i1 = (i0 + 1) % Palette.Length;
            double f = scaled - Math.Floor(scaled);

            Color a = Palette[i0];
            Color b = Palette[i1];
            return Color.FromArgb(
                255,
                Lerp(a.R, b.R, f),
                Lerp(a.G, b.G, f),
                Lerp(a.B, b.B, f));
        }

        private static byte Lerp(byte a, byte b, double t)
        {
            return (byte)Math.Round(a + (b - a) * t);
        }
    }
}
