using System;

namespace PLUMA.UI
{
    /// <summary>Transfers visual dismissal to the shared host without changing execution state.</summary>
    public interface IHostedPopup
    {
        bool IsHosted { get; set; }
        event EventHandler? DismissRequested;
    }
}
