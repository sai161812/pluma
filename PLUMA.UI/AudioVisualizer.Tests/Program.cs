using PLUMA.UI;

static void Check(bool condition, string name)
{
    if (!condition) throw new Exception("FAIL: " + name);
    Console.WriteLine("PASS: " + name);
}
static double[] Tone(double hz, double gain)
{
    return Enumerable.Range(0, AudioSpectrumAnalyzer.WindowSize)
        .Select(i => gain * Math.Sin(2 * Math.PI * hz * i / AudioSpectrumAnalyzer.SampleRate)).ToArray();
}
static int Peak(AudioSpectrumFrame frame) => Array.IndexOf(frame.Bands, frame.Bands.Max());

var silent = AudioSpectrumAnalyzer.Analyze(new double[1024]);
Check(silent.Amplitude == 0 && silent.Bands.All(x => x == 0), "silence has no movement");
var noise = AudioSpectrumAnalyzer.Analyze(Tone(1000, 0.0001));
Check(noise.Amplitude == 0, "sub-floor input stays quiet");
var low = AudioSpectrumAnalyzer.Analyze(Tone(500, 0.03));
var high = AudioSpectrumAnalyzer.Analyze(Tone(2000, 0.03));
Check(Peak(high) > Peak(low) + 5, "frequency changes move the dominant bands");
var soft = AudioSpectrumAnalyzer.Analyze(Tone(1000, 0.01));
var loud = AudioSpectrumAnalyzer.Analyze(Tone(1000, 0.10));
Check(loud.Amplitude > soft.Amplitude && loud.Bands.Max() > soft.Bands.Max(),
    "loudness scales height without per-frame auto-normalization");
var repeat = AudioSpectrumAnalyzer.Analyze(Tone(1000, 0.10));
Check(repeat.Bands.SequenceEqual(loud.Bands), "identical audio yields identical bands");
var invalid = AudioSpectrumAnalyzer.Analyze(Enumerable.Repeat(double.NaN, 1024).ToArray());
Check(double.IsFinite(invalid.Amplitude) && invalid.Bands.All(double.IsFinite), "non-finite samples are sanitized");
var clipping = AudioSpectrumAnalyzer.Analyze(Tone(500, 20));
Check(clipping.Bands.All(x => x >= 0 && x <= 1), "overload remains bounded");
Check(VoiceWaveformMotion.Step(0, 1, 0) == 0, "zero-time frame cannot jump");
Check(VoiceWaveformMotion.Step(0, 1, 1.0 / 60) <= 0.05 + 1e-12, "sudden onset has a bounded rise");
foreach (int fps in new[] { 30, 60, 120 })
{
    double level = 0;
    for (int i = 0; i < fps; i++) level = VoiceWaveformMotion.Step(level, 0.7, 1.0 / fps);
    Check(Math.Abs(level - 0.7) < 0.001, $"steady input converges at {fps} FPS");
    for (int i = 0; i < fps * 2; i++) level = VoiceWaveformMotion.Step(level, 0, 1.0 / fps);
    Check(level < 0.001, $"silence settles at {fps} FPS");
}
Console.WriteLine("All audio visualizer checks passed.");
