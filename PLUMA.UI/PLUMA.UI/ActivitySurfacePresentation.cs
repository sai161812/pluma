using System;
using Microsoft.UI.Xaml;

namespace PLUMA.UI;

internal static class ActivitySurfacePresentation
{
    internal static FrameworkElement Create(ActivitySurfaceFact fact)
    {
        if (fact.Surface == 6 && fact.Route is not null) return new RouteBadgePopup { Route = fact.Route };
        if (fact.Surface == 8 && fact.Action is { } action)
        {
            var result = new ToolResultCard(); result.ApplyEvidence(action, fact.Detail); return result;
        }
        if (fact.Surface == 19 && fact.Action is { PolicyDenied: true } denied)
            return new PolicyBlockNotice { ToolName = denied.Tool,
                MatchedRule = fact.Detail?.PolicyReason ?? "The recorded denial reason is unavailable.", IsNoticeOpen = true };
        throw new ArgumentException("No supported surface matches this activity evidence.");
    }
}
