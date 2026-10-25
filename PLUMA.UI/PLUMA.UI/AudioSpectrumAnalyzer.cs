using System;
using System.Numerics;

namespace PLUMA.UI
{
    // Pure DSP: no microphone, UI, files, network or speech recognition.
    public static class AudioSpectrumAnalyzer
    {
        public const int SampleRate = 16000;
        public const int WindowSize = 1024;
        public const int BandCount = 32;

        public static AudioSpectrumFrame Analyze(ReadOnlySpan<double> samples)
        {
            if (samples.Length != WindowSize)
                throw new ArgumentException("Expected 1024 mono samples.", nameof(samples));

            var bins = new Complex[WindowSize];
            double mean = 0;
            for (int i = 0; i < WindowSize; i++)
                mean += double.IsFinite(samples[i]) ? Math.Clamp(samples[i], -1, 1) : 0;
            mean /= WindowSize;
            double energy = 0;
            for (int i = 0; i < WindowSize; i++)
            {
                double sample = (double.IsFinite(samples[i]) ? Math.Clamp(samples[i], -1, 1) : 0) - mean;
                energy += sample * sample;
                bins[i] = new Complex(sample * (0.5 - 0.5 * Math.Cos(2 * Math.PI * i / (WindowSize - 1))), 0);
            }

            // In-place radix-2 FFT of a Hann-windowed, DC-removed frame.
            for (int i = 1, j = 0; i < WindowSize; i++)
            {
                int bit = WindowSize >> 1;
                for (; (j & bit) != 0; bit >>= 1) j ^= bit;
                j ^= bit;
                if (i < j) (bins[i], bins[j]) = (bins[j], bins[i]);
            }
            for (int length = 2; length <= WindowSize; length <<= 1)
            {
                Complex step = Complex.FromPolarCoordinates(1, -2 * Math.PI / length);
                for (int start = 0; start < WindowSize; start += length)
                {
                    Complex phase = Complex.One;
                    for (int j = 0; j < length / 2; j++)
                    {
                        Complex even = bins[start + j];
                        Complex odd = bins[start + j + length / 2] * phase;
                        bins[start + j] = even + odd;
                        bins[start + j + length / 2] = even - odd;
                        phase *= step;
                    }
                }
            }

            double loudness = Level(Math.Sqrt(energy / WindowSize), -55, -14);
            var bands = new double[BandCount];
            for (int band = 0; band < BandCount; band++)
            {
                double lowHz = 80 * Math.Pow(100, band / (double)BandCount);
                double highHz = 80 * Math.Pow(100, (band + 1) / (double)BandCount);
                int first = Math.Clamp((int)Math.Ceiling(lowHz * WindowSize / SampleRate), 1, WindowSize / 2 - 1);
                int end = Math.Clamp((int)Math.Ceiling(highHz * WindowSize / SampleRate), first + 1, WindowSize / 2);
                double power = 0;
                for (int bin = first; bin < end; bin++)
                    power += bins[bin].Real * bins[bin].Real + bins[bin].Imaginary * bins[bin].Imaginary;
                // Fixed calibration: do not normalize each frame to its own maximum.
                double magnitude = 2 * Math.Sqrt(power) / WindowSize;
                bands[band] = Level(magnitude, -65, -20) * loudness;
            }
            return new AudioSpectrumFrame(loudness, bands);
        }

        private static double Level(double magnitude, double floorDb, double ceilingDb)
        {
            double db = 20 * Math.Log10(Math.Max(magnitude, 1e-12));
            double x = Math.Clamp((db - floorDb) / (ceilingDb - floorDb), 0, 1);
            return x * x * (3 - 2 * x); // Soft knee, continuous at the noise floor.
        }
    }

    public sealed record AudioSpectrumFrame(double Amplitude, double[] Bands);
}
