using System;

namespace PLUMA.UI
{
    // Shared by the WinUI renderer and the dependency-free regression harness.
    public static class VoiceWaveformMotion
    {
        public static double Step(double current, double target, double elapsed)
        {
            current = double.IsFinite(current) ? Math.Clamp(current, 0, 1) : 0;
            target = double.IsFinite(target) ? Math.Clamp(target, 0, 1) : 0;
            double dt = double.IsFinite(elapsed) ? Math.Clamp(elapsed, 0, 0.05) : 0;
            double tau = target > current ? 0.10 : 0.24;
            double change = (target - current) * (1 - Math.Exp(-dt / tau));
            // At most 0.35 DIP outward growth per 60 Hz frame (7 DIP maximum).
            return current + Math.Clamp(change, -4 * dt, 3 * dt);
        }
    }
}
