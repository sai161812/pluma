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
            string method = PopupText.Label(verificationMethod);
            NoticeText.Text = string.IsNullOrWhiteSpace(sanitizedDetail) ? method : $"{method}. {PopupText.Message(sanitizedDetail)}";
            IsOpen = true;
        }

        public void HideResult()
        {
            IsOpen = false;
            Title = string.Empty;
            NoticeText.Text = string.Empty;
            Severity = InfoBarSeverity.Error;
        }

        private void OnCloseButtonClick(InfoBar sender, object args) => HideResult();
    }
}
