using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.UI;

namespace PLUMA.UI
{
    /// <summary>
    /// Monochrome circular waveform driven by a normalized amplitude value.
    /// It renders feedback only and never captures audio.
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

        private const int SegmentCount = 88;
        private const double CanvasSize = 126.0;
        private const double BaseRadius = 49.0;
        private const double StrokeThickness = 1.25;
        private const double QuietHalfLength = 0.55;
        private const double MaximumAddedHalfLength = 8.5;
        private const double AttackSeconds = 0.07;
        private const double ReleaseSeconds = 0.18;
        private const double BarAttackSeconds = 0.055;
        private const double BarReleaseSeconds = 0.15;
        private const double TargetRefreshSeconds = 0.085;
        private const double FrameIntervalSeconds = 1.0 / 30.0;

        private readonly Line[] _bars = new Line[SegmentCount];
        private readonly double[] _rawTargets = new double[SegmentCount];
        private readonly double[] _targetLevels = new double[SegmentCount];
        private readonly double[] _currentLevels = new double[SegmentCount];
        private readonly double[] _barBias = new double[SegmentCount];
        private readonly Random _random = new(0x504C554D);
        private readonly SolidColorBrush _waveBrush =
            new(Color.FromArgb(255, 230, 230, 230));

        private bool _hooked;
        private bool _built;
        private double _smoothedAmplitude;
        private double _targetRefreshElapsed = TargetRefreshSeconds;
        private double _renderElapsed;
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

        private static void OnIsAnimatingChanged(
            DependencyObject d,
            DependencyPropertyChangedEventArgs e)
        {
            if (d is VoiceListeningRing ring)
            {
                ring.SyncRenderingHook();
            }
        }

        private void OnLoaded(object sender, RoutedEventArgs e)
        {
            EnsureWaveform();
            _lastTicks = Environment.TickCount64;
            _targetRefreshElapsed = TargetRefreshSeconds;
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

        private void EnsureWaveform()
        {
            if (_built)
            {
                return;
            }

            for (int i = 0; i < SegmentCount; i++)
            {
                _barBias[i] = 0.72 + (_random.NextDouble() * 0.56);

                var bar = new Line
                {
                    Stroke = _waveBrush,
                    StrokeThickness = StrokeThickness,
                    StrokeStartLineCap = PenLineCap.Round,
                    StrokeEndLineCap = PenLineCap.Round,
                    IsHitTestVisible = false
                };

                _bars[i] = bar;
                RingCanvas.Children.Add(bar);
            }

            _built = true;
        }

        private void OnRendering(object? sender, object e)
        {
            long now = Environment.TickCount64;
            double dt = Math.Clamp((now - _lastTicks) / 1000.0, 0.0, 0.05);
            _lastTicks = now;

            _renderElapsed += dt;
            if (_renderElapsed < FrameIntervalSeconds)
            {
                return;
            }

            double frameDt = _renderElapsed;
            _renderElapsed = 0;
            RenderFrame(frameDt);
        }

        private void RenderFrame(double dt)
        {
            if (!_built)
            {
                return;
            }

            double targetAmplitude = Math.Clamp(Amplitude, 0.0, 1.0);
            if (targetAmplitude <= 0.025)
            {
                targetAmplitude = 0;
            }

            double amplitudeTau =
                targetAmplitude > _smoothedAmplitude
                    ? AttackSeconds
                    : ReleaseSeconds;
            _smoothedAmplitude = Smooth(
                _smoothedAmplitude,
                targetAmplitude,
                dt,
                amplitudeTau);

            _targetRefreshElapsed += dt;
            if (_targetRefreshElapsed >= TargetRefreshSeconds)
            {
                _targetRefreshElapsed %= TargetRefreshSeconds;
                RefreshTargets(_smoothedAmplitude);
            }

            double cx = CanvasSize / 2.0;
            double cy = CanvasSize / 2.0;

            for (int i = 0; i < SegmentCount; i++)
            {
                double levelTau =
                    _targetLevels[i] > _currentLevels[i]
                        ? BarAttackSeconds
                        : BarReleaseSeconds;
                _currentLevels[i] = Smooth(
                    _currentLevels[i],
                    _targetLevels[i],
                    dt,
                    levelTau);

                double halfLength =
                    QuietHalfLength +
                    (_smoothedAmplitude * MaximumAddedHalfLength * _currentLevels[i]);

                double theta = (Math.PI * 2.0 * i) / SegmentCount;
                double cos = Math.Cos(theta);
                double sin = Math.Sin(theta);
                double innerRadius = BaseRadius - halfLength;
                double outerRadius = BaseRadius + halfLength;

                _bars[i].X1 = cx + (cos * innerRadius);
                _bars[i].Y1 = cy + (sin * innerRadius);
                _bars[i].X2 = cx + (cos * outerRadius);
                _bars[i].Y2 = cy + (sin * outerRadius);
            }

            _waveBrush.Opacity =
                0.18 + (0.74 * Math.Min(1.0, _smoothedAmplitude * 2.4));
        }

        private void RefreshTargets(double amplitude)
        {
            if (amplitude <= 0.015)
            {
                Array.Clear(_targetLevels);
                return;
            }

            for (int i = 0; i < SegmentCount; i++)
            {
                double randomValue = Math.Pow(_random.NextDouble(), 2.15);
                _rawTargets[i] = randomValue * _barBias[i];
            }

            for (int i = 0; i < SegmentCount; i++)
            {
                int previous = (i + SegmentCount - 1) % SegmentCount;
                int next = (i + 1) % SegmentCount;

                double localContinuity =
                    (_rawTargets[previous] +
                     (2.0 * _rawTargets[i]) +
                     _rawTargets[next]) / 4.0;

                double isolatedPeak =
                    _random.NextDouble() < 0.055
                        ? 0.28 + (_random.NextDouble() * 0.42)
                        : 0.0;

                _targetLevels[i] = Math.Clamp(
                    (0.72 * localContinuity) +
                    (0.28 * _rawTargets[i]) +
                    isolatedPeak,
                    0.0,
                    1.0);
            }
        }

        private static double Smooth(
            double current,
            double target,
            double dt,
            double timeConstant)
        {
            if (dt <= 0)
            {
                return target;
            }

            double factor =
                1.0 - Math.Exp(-dt / Math.Max(timeConstant, 0.001));
            return current + ((target - current) * factor);
        }
    }
}
