namespace PLUMA.UI
{
    /// <summary>
    /// Visual states of the unified voice overlay (Surfaces 11–14).
    /// Backend / preview hosts push this value; the control only renders it.
    /// </summary>
    public enum VoiceOverlayState
    {
        Hidden,
        ListeningSilence,
        ListeningSpeech,
        SilenceTimeout,
        Committed
    }
}
