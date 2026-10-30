using System;

namespace PLUMA.UI;

internal sealed record ActivitySurfaceFact(string Key, int Surface, string TaskId,
    string Fingerprint, string? Route = null, CoreRequestProtocol.ActivityAction? Action = null,
    CoreRequestProtocol.ActionDetail? Detail = null)
{
    internal static ActivitySurfaceFact ForRoute(string task, string route) =>
        route is "FAST" or "SMART" or "SCREEN" or "DEEP"
            ? new("ledger-route-" + task, 6, task, route, Route: route)
            : throw new ArgumentException("Unknown execution route.");

    internal static ActivitySurfaceFact ForAction(string task, CoreRequestProtocol.ActivityAction action, CoreRequestProtocol.ActionDetail? detail = null) =>
        new("ledger-action-" + task + "/" + action.ActionId, action.PolicyDenied ? 19 : 8, task,
            string.Join("/", action.Tool, action.StepIndex, action.Risk, action.Verified, action.ErrorRecorded, action.PolicyDenied,
                System.Text.Json.JsonSerializer.Serialize(new[] { detail?.FactualMessage, detail?.ErrorCode, detail?.PolicyReason })),
            Action: action, Detail: detail);
}
