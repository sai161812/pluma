using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace PLUMA.UI
{
    internal sealed record CoreIpcOptions(string PipeName, string SecretPath, TimeSpan Timeout)
    {
        internal static CoreIpcOptions ForCurrentUser()
        {
            string? user = Environment.GetEnvironmentVariable("USERNAME");
            if (string.IsNullOrEmpty(user)) user = Environment.GetEnvironmentVariable("USER");
            if (string.IsNullOrEmpty(user)) user = "default";
            var clean = new StringBuilder();
            foreach (Rune rune in user.EnumerateRunes())
            {
                UnicodeCategory category = Rune.GetUnicodeCategory(rune);
                if (Rune.IsLetterOrDigit(rune) || category is UnicodeCategory.LetterNumber or UnicodeCategory.OtherNumber || rune.Value is '-' or '_')
                    clean.Append(rune.ToString());
            }
            string? local = Environment.GetEnvironmentVariable("LOCALAPPDATA");
            if (string.IsNullOrEmpty(local)) local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            return new("pluma_ipc_" + clean, Path.Combine(local, "Pluma", "ipc_secret.key"), TimeSpan.FromSeconds(3));
        }
    }

    /// <summary>Authenticated per-user adapter to the Python Windows message pipe. Never starts the core or retries uncertain requests.</summary>
    internal sealed class CoreIpcClient : ICoreStatusClient
    {
        internal const int MaximumMessageBytes = 1024 * 1024;
        private readonly CoreIpcOptions _options;
        private readonly CancellationTokenSource _lifetime = new();
        private readonly object _gate = new();
        private TaskCompletionSource _idle = CompletedSource();
        private readonly TaskCompletionSource _shutdown = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _active;
        private int _normalActive;
        private int _stopActive;
        private bool _disposed;

        internal CoreIpcClient(CoreIpcOptions? options = null)
        {
            _options = options ?? CoreIpcOptions.ForCurrentUser();
            if (string.IsNullOrWhiteSpace(_options.PipeName) || _options.PipeName.IndexOfAny(new[] { '\\', '/' }) >= 0 ||
                _options.PipeName.Length > 240 || _options.Timeout <= TimeSpan.Zero || _options.Timeout > TimeSpan.FromSeconds(10) ||
                !Path.IsPathFullyQualified(_options.SecretPath) || Path.GetFullPath(_options.SecretPath).StartsWith(@"\\", StringComparison.Ordinal))
                throw new ArgumentException("A bounded local core connection is required.");
        }

        private static TaskCompletionSource CompletedSource()
        {
            var source = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            source.SetResult(); return source;
        }

        public async Task<CoreStatusResult> GetStatusAsync(CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!TryEnterCall(priority: false, out CancellationToken lifetime))
                return CoreStatusResult.Failed(CoreConnectionFailure.Busy);
            try { return await QueryAsync(cancellationToken, lifetime).ConfigureAwait(false); }
            finally { ExitCall(priority: false); }
        }

        private async Task<CoreStatusResult> QueryAsync(CancellationToken caller, CancellationToken lifetime)
        {
            PipeExchangeResult exchange = await ExchangeAsync("{\"command\":\"status\"}"u8.ToArray(), caller, lifetime,
                returnUncertainOnCallerCancellation: false).ConfigureAwait(false);
            if (exchange.Failure != CoreConnectionFailure.None) return CoreStatusResult.Failed(exchange.Failure);
            try { return ParseStatus(exchange.Response!, exchange.ElapsedMilliseconds); }
            catch (Exception error) when (error is JsonException or InvalidDataException)
            { return CoreStatusResult.Failed(CoreConnectionFailure.Protocol); }
        }

        private sealed record PipeExchangeResult(byte[]? Response, CoreConnectionFailure Failure,
            bool OutcomeUnknown, double ElapsedMilliseconds);

        private async Task<PipeExchangeResult> ExchangeAsync(byte[] request, CancellationToken caller,
            CancellationToken lifetime, bool returnUncertainOnCallerCancellation)
        {
            if (request.Length == 0 || request.Length > MaximumMessageBytes)
                return new(null, CoreConnectionFailure.Protocol, false, 0);
            using var bounded = CancellationTokenSource.CreateLinkedTokenSource(caller, lifetime);
            bounded.CancelAfter(_options.Timeout);
            CancellationToken token = bounded.Token;
            byte[]? secret = null, proof = null;
            bool authenticating = false, credentialsLoaded = false;
            bool requestSent = false;
            var elapsed = Stopwatch.StartNew();
            try
            {
                secret = await ReadSecretAsync(_options.SecretPath, token).ConfigureAwait(false);
                credentialsLoaded = true;
                using var pipe = new NamedPipeClientStream(".", _options.PipeName, PipeDirection.InOut,
                    PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                using var abort = token.Register(() => pipe.Dispose());
                await pipe.ConnectAsync(token).ConfigureAwait(false);
                pipe.ReadMode = PipeTransmissionMode.Message;
                authenticating = true;
                byte[] challenge = await ReadMessageAsync(pipe, 32, token).ConfigureAwait(false);
                if (challenge.Length != 32) throw new AuthenticationException();
                proof = HMACSHA256.HashData(secret, challenge);
                CryptographicOperations.ZeroMemory(secret); secret = null;
                await pipe.WriteAsync(proof, token).ConfigureAwait(false);
                CryptographicOperations.ZeroMemory(proof); proof = null;
                byte[] ack = await ReadMessageAsync(pipe, 7, token).ConfigureAwait(false);
                if (!ack.AsSpan().SequenceEqual("AUTH_OK"u8)) throw new AuthenticationException();
                authenticating = false;
                // Python PipeConnection on Windows uses native message boundaries, not a TCP length prefix.
                requestSent = true; // From this point a lost reply may leave a committed request.
                await pipe.WriteAsync(request, token).ConfigureAwait(false);
                byte[] response = await ReadMessageAsync(pipe, MaximumMessageBytes, token).ConfigureAwait(false);
                token.ThrowIfCancellationRequested();
                return new(response, CoreConnectionFailure.None, false, elapsed.Elapsed.TotalMilliseconds);
            }
            catch (Exception error) when (error is OperationCanceledException or ObjectDisposedException or IOException && token.IsCancellationRequested)
            {
                if (caller.IsCancellationRequested && requestSent && returnUncertainOnCallerCancellation)
                    return new(null, CoreConnectionFailure.Timeout, true, elapsed.Elapsed.TotalMilliseconds);
                if (caller.IsCancellationRequested || lifetime.IsCancellationRequested)
                    throw new OperationCanceledException(caller.IsCancellationRequested ? caller : lifetime);
                return new(null, CoreConnectionFailure.Timeout, requestSent, elapsed.Elapsed.TotalMilliseconds);
            }
            catch (FileNotFoundException) { return new(null, CoreConnectionFailure.CredentialsUnavailable, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (DirectoryNotFoundException) { return new(null, CoreConnectionFailure.CredentialsUnavailable, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (UnauthorizedAccessException) { return new(null, CoreConnectionFailure.AccessDenied, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (System.Security.SecurityException) { return new(null, CoreConnectionFailure.AccessDenied, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (AuthenticationException) { return new(null, CoreConnectionFailure.Authentication, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (Exception error) when (error is JsonException or InvalidDataException)
            { return new(null, !credentialsLoaded ? CoreConnectionFailure.CredentialsUnavailable : authenticating ? CoreConnectionFailure.Authentication : CoreConnectionFailure.Protocol, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            catch (IOException) { return new(null, authenticating ? CoreConnectionFailure.Authentication : CoreConnectionFailure.Unavailable, requestSent, elapsed.Elapsed.TotalMilliseconds); }
            finally
            {
                if (secret != null) CryptographicOperations.ZeroMemory(secret);
                if (proof != null) CryptographicOperations.ZeroMemory(proof);
            }
        }

        private bool TryEnterCall(bool priority, out CancellationToken lifetime)
        {
            lock (_gate)
            {
                ObjectDisposedException.ThrowIf(_disposed, this);
                // Four ordinary calls are bounded independently from one reserved
                // STOP call, so a slow status/history response cannot consume STOP's client slot.
                if (priority ? _stopActive >= 1 : _normalActive >= 4)
                { lifetime = default; return false; }
                if (priority) _stopActive++; else _normalActive++;
                if (_active++ == 0) _idle = new(TaskCreationOptions.RunContinuationsAsynchronously);
                lifetime = _lifetime.Token;
                return true;
            }
        }

        private void ExitCall(bool priority)
        {
            lock (_gate)
            {
                if (priority) _stopActive--; else _normalActive--;
                if (--_active == 0) _idle.TrySetResult();
            }
        }

        internal Task<CoreRequestResult<CoreRequestProtocol.SubmissionAck>> SubmitTextAsync(
            string requestId, string text, CancellationToken cancellationToken) =>
            VersionedCallAsync(new CoreRequestProtocol.SubmitText(requestId, text).ToMessage(), requestId,
                false, true, bytes => CoreRequestProtocol.SubmissionAck.Parse(bytes), value => value.RequestId, cancellationToken);

        internal Task<CoreRequestResult<CoreRequestProtocol.TerminalReadback>> GetTerminalReadbackAsync(
            string requestId, string taskId, CancellationToken cancellationToken) =>
            VersionedCallAsync(new CoreRequestProtocol.TerminalReadbackRequest(requestId, taskId).ToMessage(), requestId,
                false, false, bytes => CoreRequestProtocol.TerminalReadback.Parse(bytes), value => value.RequestId, cancellationToken,
                value => value.TaskId == taskId);

        internal Task<CoreRequestResult<CoreRequestProtocol.StopAck>> StopAsync(
            string requestId, string? taskId, CancellationToken cancellationToken) =>
            VersionedCallAsync(new CoreRequestProtocol.StopRequest(requestId, taskId).ToMessage(), requestId,
                true, true, bytes => CoreRequestProtocol.StopAck.Parse(bytes), value => value.RequestId, cancellationToken);

        private async Task<CoreRequestResult<T>> VersionedCallAsync<T>(byte[] request, string requestId,
            bool priority, bool mutation, Func<byte[], T> parse, Func<T, string> correlation,
            CancellationToken caller, Func<T, bool>? additionalCorrelation = null) where T : class
        {
            caller.ThrowIfCancellationRequested();
            if (!TryEnterCall(priority, out CancellationToken lifetime))
                return CoreRequestResult<T>.Failed(CoreConnectionFailure.Busy);
            try
            {
                PipeExchangeResult exchange = await ExchangeAsync(request, caller, lifetime,
                    returnUncertainOnCallerCancellation: mutation).ConfigureAwait(false);
                if (exchange.Failure != CoreConnectionFailure.None)
                    return CoreRequestResult<T>.Failed(exchange.Failure, exchange.OutcomeUnknown);
                try
                {
                    using JsonDocument document = JsonDocument.Parse(exchange.Response!, new JsonDocumentOptions { MaxDepth = 16 });
                    if (document.RootElement.ValueKind == JsonValueKind.Object &&
                        document.RootElement.TryGetProperty("message_type", out JsonElement type) &&
                        type.ValueKind == JsonValueKind.String && type.GetString() == "protocol_error")
                    {
                        var protocolError = CoreRequestProtocol.ProtocolError.Parse(exchange.Response!);
                        CoreConnectionFailure failure = protocolError.ErrorCode == "BUSY"
                            ? CoreConnectionFailure.Busy : CoreConnectionFailure.Protocol;
                        return CoreRequestResult<T>.Failed(failure, false, protocolError.ErrorCode, protocolError.Message);
                    }
                    T response = parse(exchange.Response!);
                    if (correlation(response) != requestId || (additionalCorrelation is not null && !additionalCorrelation(response)))
                        throw new JsonException("The response correlation did not match the request.");
                    return new(response, CoreConnectionFailure.None, false, null, null);
                }
                catch (Exception error) when (error is JsonException or InvalidDataException)
                { return CoreRequestResult<T>.Failed(CoreConnectionFailure.Protocol, true); }
            }
            finally { ExitCall(priority); }
        }

        private static async Task<byte[]> ReadSecretAsync(string path, CancellationToken token)
        {
            await using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 32, FileOptions.Asynchronous);
            // Inspect the opened handle, rather than trusting a path check before opening it.
            FileSecurity security = file.GetAccessControl();
            using WindowsIdentity identity = WindowsIdentity.GetCurrent();
            SecurityIdentifier user = identity.User ?? throw new UnauthorizedAccessException();
            if (!user.Equals(security.GetOwner(typeof(SecurityIdentifier)))) throw new UnauthorizedAccessException();
            foreach (FileSystemAccessRule rule in security.GetAccessRules(true, true, typeof(SecurityIdentifier)))
            {
                if (rule.AccessControlType != AccessControlType.Allow) continue;
                var sid = (SecurityIdentifier)rule.IdentityReference;
                if (!sid.Equals(user) && !sid.IsWellKnown(WellKnownSidType.LocalSystemSid) && !sid.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid))
                    throw new UnauthorizedAccessException();
            }
            if (file.Length != 32) throw new InvalidDataException("Core credentials are unavailable.");
            byte[] secret = new byte[32];
            try { await file.ReadExactlyAsync(secret, token).ConfigureAwait(false); return secret; }
            catch { CryptographicOperations.ZeroMemory(secret); throw; }
        }

        private static async Task<byte[]> ReadMessageAsync(PipeStream pipe, int maximum, CancellationToken token)
        {
            byte[] buffer = new byte[Math.Min(maximum, 8192)];
            using var message = new MemoryStream();
            while (true)
            {
                int count = await pipe.ReadAsync(buffer, token).ConfigureAwait(false);
                if (count == 0) throw new IOException("Core connection closed.");
                if (message.Length + count > maximum) throw new InvalidDataException("Core response exceeds its bound.");
                message.Write(buffer, 0, count);
                if (pipe.IsMessageComplete) return message.ToArray();
                if (message.Length == maximum) throw new InvalidDataException("Core response exceeds its bound.");
            }
        }

        internal static CoreStatusResult ParseStatus(byte[] response, double milliseconds)
        {
            using JsonDocument document = JsonDocument.Parse(response, new JsonDocumentOptions { MaxDepth = 16 });
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException();
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in root.EnumerateObject())
                if (!names.Add(property.Name)) throw new InvalidDataException();
            if (!root.TryGetProperty("status", out var status) || status.ValueKind != JsonValueKind.String || status.GetString() != "ok" ||
                !root.TryGetProperty("running", out var running) || running.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                !root.TryGetProperty("active_tasks", out var active) || active.ValueKind != JsonValueKind.Number || !active.TryGetInt32(out int count) || count < 0 ||
                !root.TryGetProperty("voice_enabled", out var voice) || voice.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw new InvalidDataException();
            return new(new(running.GetBoolean(), count, voice.GetBoolean(), milliseconds), CoreConnectionFailure.None);
        }

        public async ValueTask DisposeAsync()
        {
            Task idle; bool first;
            lock (_gate) { first = !_disposed; _disposed = true; idle = _idle.Task; }
            if (!first) { await _shutdown.Task.ConfigureAwait(false); return; }
            try { _lifetime.Cancel(); await idle.ConfigureAwait(false); }
            finally { _lifetime.Dispose(); _shutdown.TrySetResult(); }
        }
    }
}
