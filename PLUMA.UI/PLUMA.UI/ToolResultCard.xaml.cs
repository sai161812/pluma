using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class ToolResultCard : UserControl
    {
        public ToolResultCard()
        {
            InitializeComponent();
        }
        internal void ApplyEvidence(CoreRequestProtocol.ActivityAction action, CoreRequestProtocol.ActionDetail? detail = null)
        {
            ResultText.Text = detail?.FactualMessage ?? ActivityProjection.ActionMessage(action);
            ErrorCodeText.Text = detail?.ErrorCode ?? string.Empty;
            ErrorCodeText.Visibility = detail?.ErrorCode is null
                ? Microsoft.UI.Xaml.Visibility.Collapsed : Microsoft.UI.Xaml.Visibility.Visible;
            ToolNameText.Text = "Tool: " + PopupText.Label(action.Tool);
            bool issue = action.ErrorRecorded || action.PolicyDenied;
            bool pending = detail?.ErrorCode == "MUTATION_OUTCOME_PENDING";
            OutcomeState.Label = pending ? "Pending" : issue ? "Issue recorded" : action.Verified ? "Verified" : "Unverified";
            OutcomeState.Kind = action.Verified && !issue ? PopupStatusKind.Success : PopupStatusKind.Dot;
            VerificationState.Label = action.Verified ? "Postcondition verified" : "Not verified";
            VerificationState.Kind = action.Verified ? PopupStatusKind.Success : PopupStatusKind.Dot;
        }
    }
}
