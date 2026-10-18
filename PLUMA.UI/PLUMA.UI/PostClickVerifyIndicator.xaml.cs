using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    /// <summary>Displays supplied verifier evidence; never infers success from a click.</summary>
    public sealed partial class PostClickVerifyIndicator : InfoBar
    {
        public PostClickVerifyIndicator() => InitializeComponent();

        public void ShowResult(bool verified, string verificationMethod, string sanitizedDetail)
        {
            HideResult();
            if (string.IsNullOrWhiteSpace(verificationMethod)) return;
            Title = verified ? "Verified" : "Unverified";
            Severity = verified ? InfoBarSeverity.Success : InfoBarSeverity.Error;
            Message = string.IsNullOrWhiteSpace(sanitizedDetail) ? verificationMethod : $"{verificationMethod} — {sanitizedDetail}";
            IsOpen = true;
        }

        public void HideResult()
        {
            IsOpen = false;
            Title = string.Empty;
            Message = string.Empty;
            Severity = InfoBarSeverity.Error;
        }

        private void OnCloseButtonClick(InfoBar sender, object args) => HideResult();
    }
}
