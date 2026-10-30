using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class ToolResultCard : UserControl
    {
        public ToolResultCard()
        {
            InitializeComponent();
        }
        internal void ApplyEvidence(CoreRequestProtocol.ActivityAction action)
        {
            ResultText.Text = ActivityProjection.ActionMessage(action);
            ToolNameText.Text = "Tool: " + PopupText.Label(action.Tool);
            bool issue = action.ErrorRecorded || action.PolicyDenied;
            OutcomeState.Label = issue ? "Issue recorded" : action.Verified ? "Verified" : "Unverified";
            OutcomeState.Kind = action.Verified && !issue ? PopupStatusKind.Success : PopupStatusKind.Dot;
            VerificationState.Label = action.Verified ? "Postcondition verified" : "Not verified";
            VerificationState.Kind = action.Verified ? PopupStatusKind.Success : PopupStatusKind.Dot;
        }
    }
}
