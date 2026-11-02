using System;
using System.Globalization;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI
{
    internal enum CoreConnectionFailure { None, Unavailable, CredentialsUnavailable, AccessDenied, Authentication, Timeout, Protocol, Busy }

    internal sealed record CoreStatus(bool Running, int ActiveTasks, bool VoiceEnabled, double RoundTripMilliseconds);

    internal sealed record CoreStatusResult(CoreStatus? Status, CoreConnectionFailure Failure)
    {
        internal static CoreStatusResult Failed(CoreConnectionFailure failure) => new(null, failure);
        internal string HealthLabel => Status is { Running: true } ? "Connected" : Status != null ? "Core stopped" : "Disconnected";
        internal string TaskLabel => Status == null ? "Unavailable" : Status.ActiveTasks == 0 ? "Idle" :
            Status.ActiveTasks.ToString(CultureInfo.CurrentCulture) + (Status.ActiveTasks == 1 ? " active task" : " active tasks");
        internal string Message => Status != null ? (Status.Running ? "Core status verified." : "The core is not running.") : Failure switch
        {
            CoreConnectionFailure.CredentialsUnavailable => "Start PLUMA, then refresh the connection.",
            CoreConnectionFailure.AccessDenied => "Connection denied. Check the core connection permissions.",
            CoreConnectionFailure.Authentication => "The core connection could not be authenticated.",
            CoreConnectionFailure.Timeout => "The core did not respond in time. Refresh to try again.",
            CoreConnectionFailure.Protocol => "The core returned an unsupported status response.",
            CoreConnectionFailure.Busy => "A connection check is already in progress.",
            _ => "The core is unavailable. Start PLUMA, then refresh the connection."
        };
    }

    internal sealed record CoreRequestResult<T>(T? Response, CoreConnectionFailure Failure,
        bool OutcomeUnknown, string? ErrorCode, string? Message) where T : class
    {
        internal bool IsSuccess => Response is not null && Failure == CoreConnectionFailure.None;
        internal static CoreRequestResult<T> Failed(CoreConnectionFailure failure,
            bool outcomeUnknown = false, string? errorCode = null, string? message = null) =>
            new(null, failure, outcomeUnknown, errorCode, message);
    }

    internal interface ICoreStatusClient : IAsyncDisposable
    {
        Task<CoreStatusResult> GetStatusAsync(CancellationToken cancellationToken);
    }
}
