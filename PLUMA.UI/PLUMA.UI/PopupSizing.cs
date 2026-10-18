using System;

namespace PLUMA.UI
{
    public readonly record struct PopupClassSize(double WidthDips, double HeightDips);

    /// <summary>Stable class footprints; message length never changes the native card size.</summary>
    public static class PopupSizing
    {
        public static PopupClassSize ForSurface(int surface) => surface switch
        {
            4 or 5 or 20 or 21 => new(360, 152),
            6 => new(260, 112),
            7 or 8 => new(420, 176),
            9 => new(380, 276),
            >= 11 and <= 14 => new(460, 276),
            17 or 19 or 24 => new(400, 112),
            _ => throw new ArgumentOutOfRangeException(nameof(surface))
        };
    }
}
