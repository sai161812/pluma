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
            ResultText.Text = action.Detail?.FactualMessage ?? ActivityProjection.ActionMessage(action);
            ErrorCodeText.Text = action.Detail?.ErrorCode ?? string.Empty;
            ErrorCodeText.Visibility = action.Detail?.ErrorCode is null
                ? Microsoft.UI.Xaml.Visibility.Collapsed : Microsoft.UI.Xaml.Visibility.Visible;
            ToolNameText.Text = "Tool: " + PopupText.Label(action.Tool);
            bool issue = action.ErrorRecorded || action.PolicyDenied;
            bool pending = action.Detail?.ErrorCode == "MUTATION_OUTCOME_PENDING";
            OutcomeState.Label = pending ? "Pending" : issue ? "Issue recorded" : action.Verified ? "Verified" : "Unverified";
            OutcomeState.Kind = action.Verified && !issue ? PopupStatusKind.Success : PopupStatusKind.Dot;
            VerificationState.Label = action.Verified ? "Postcondition verified" : "Not verified";
            VerificationState.Kind = action.Verified ? PopupStatusKind.Success : PopupStatusKind.Dot;
        }
    }
}
