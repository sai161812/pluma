using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI;

internal sealed class NativeConfirmationPresenter(Func<XamlRoot?> root) : IConfirmationPresenter
{
    internal RiskApprovalDialog? ActiveDialog { get; private set; }
    internal CoreRequestProtocol.ConfirmationView? ActiveView { get; private set; }
    public async Task<bool?> ShowAsync(CoreRequestProtocol.ConfirmationView view, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        if (ActiveDialog is not null) throw new InvalidOperationException("An approval dialog is already owned.");
        var dialog = new RiskApprovalDialog
        {
            XamlRoot = root() ?? throw new InvalidOperationException("Approval host is unavailable."),
            ToolName = view.Tool, RiskClass = view.Risk,
            MaterialEffect = view.Prompt + (string.IsNullOrEmpty(view.TargetSummary) ? "" : Environment.NewLine + view.TargetSummary),
            SanitizedArguments = view.Arguments.GetRawText()
        };
        ActiveDialog = dialog; ActiveView = view;
        try
        {
            using var registration = token.Register(() => dialog.DispatcherQueue.TryEnqueue(dialog.Hide));
            var result = await dialog.ShowAsync();
            if (token.IsCancellationRequested) return null;
            return result == ContentDialogResult.Primary;
        }
        finally { ActiveDialog = null; ActiveView = null; }
    }
}
