using System.Diagnostics;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using System.Text.Json;
using PLUMA.UI;

internal static class Program
{
    private static int _checks;
    private static readonly string Root = Path.Combine(Path.GetTempPath(), "PLUMA-Ipc-tests-" + Guid.NewGuid().ToString("N"));
    private static string Secret => Path.Combine(Root, "secret.key");
    private const string Healthy = "{\"status\":\"ok\",\"running\":true,\"active_tasks\":2,\"voice_enabled\":true}";
    private static void Check(bool condition, string label)
    {
        if (!condition) throw new InvalidOperationException(label);
        _checks++; Console.WriteLine("PASS " + label);
    }
    private static CoreIpcOptions Options(string pipe, string? key = null, int milliseconds = 1800) =>
        new(pipe, key ?? Secret, TimeSpan.FromMilliseconds(milliseconds));
    private static string PipeName() => "pluma_status_test_" + Guid.NewGuid().ToString("N");

    private static async Task<int> Main()
    {
        try
        {
            CreatePrivateDirectory(Root);
            WritePrivateKey(Secret);
            await RunAsync();
            Console.WriteLine($"{_checks} IPC checks passed. No production resident, microphone or personal desktop actions were started.");
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
        finally
        {
            // Exact test-owned files only; never recursively delete or touch the production credential.
            foreach (string relative in new[] { "secret.key", "wrong.key", "broad.key", "null.key", "Pluma/ipc_secret.key" })
            {
                string path = Path.GetFullPath(Path.Combine(Root, relative));
                if (path.StartsWith(Root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase) && File.Exists(path)) File.Delete(path);
            }
            string child = Path.Combine(Root, "Pluma");
            if (Directory.Exists(child) && !Directory.EnumerateFileSystemEntries(child).Any()) Directory.Delete(child);
            if (Directory.Exists(Root) && !Directory.EnumerateFileSystemEntries(Root).Any()) Directory.Delete(Root);
        }
    }

    private static async Task RunAsync()
    {
        await ConfirmationControllerChecks.RunAsync(Check);
        string absent = Path.Combine(Root, "not-created", "ipc_secret.key");
        await using (var client = new CoreIpcClient(Options(PipeName(), absent)))
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.CredentialsUnavailable && !File.Exists(absent),
                "missing credentials stay disconnected without creating credentials or starting the core");

        foreach (string malformed in new[] { "{}", "[]", "{\"status\":\"ok\",\"running\":\"true\",\"active_tasks\":0,\"voice_enabled\":false}",
            Healthy.Replace("\"active_tasks\":2", "\"active_tasks\":-1"), Healthy.Replace("\"active_tasks\":2", "\"active_tasks\":\"2\""),
            Healthy.Replace("\"status\":\"ok\"", "\"status\":\"ok\",\"status\":\"error\"") })
        {
            try { CoreIpcClient.ParseStatus(Encoding.UTF8.GetBytes(malformed), 0); throw new Exception("Malformed status accepted."); }
            catch (InvalidDataException) { Check(true, "incomplete, mistyped, negative or duplicate status fields cannot imply connection"); }
        }
        Check(CoreIpcClient.ParseStatus(Encoding.UTF8.GetBytes(Healthy), 1).TaskLabel == "2 active tasks", "status projection uses supplied task count");
        Check(CoreStatusResult.Failed(CoreConnectionFailure.Timeout).HealthLabel == "Disconnected", "failure projection clears a previous connected state");
        await using (var server = new LocalServer(PipeName(), "", "stall-response"))
        await using (var client = new CoreIpcClient(Options(server.Name, milliseconds: 180)))
        {
            CoreRequestResult<CoreRequestProtocol.SubmissionAck> uncertain =
                await client.SubmitTextAsync("9fb62f64-4eb4-42b3-b268-8c586a90da12", "safe fixture request", default);
            Check(uncertain.Response is null && uncertain.Failure == CoreConnectionFailure.Timeout && uncertain.OutcomeUnknown,
                "a reply timeout after request write is surfaced as uncertain without retry");
        }
        await using (var server = new LocalServer(PipeName(), "", "stall-response"))
        await using (var client = new CoreIpcClient(Options(server.Name)))
        using (var cancel = new CancellationTokenSource(120))
        {
            CoreRequestResult<CoreRequestProtocol.SubmissionAck> uncertain =
                await client.SubmitTextAsync("c583f0b4-6ed0-420c-bdb1-9c87e46264ef", "safe fixture request", cancel.Token);
            Check(uncertain.Response is null && uncertain.Failure == CoreConnectionFailure.Timeout && uncertain.OutcomeUnknown,
                "caller cancellation after request write preserves uncertain submission state");
        }

        string requestId = "9fb62f64-4eb4-42b3-b268-8c586a90da12";
        string taskId = "a30d93be-1110-4d54-9fd2-4bf03f9d595c";
        await using (var server = new LocalServer(PipeName(), "", "stall-response"))
        await using (var client = new CoreIpcClient(Options(server.Name, milliseconds: 180)))
        {
            var decision = new CoreRequestProtocol.ConfirmationDecisionRequest(requestId,
                Guid.NewGuid().ToString("D"), taskId, Guid.NewGuid().ToString("D"), new string('a', 64), true);
            var uncertain = await client.DecideConfirmationAsync(decision, default);
            Check(uncertain.Response is null && uncertain.Failure == CoreConnectionFailure.Timeout && uncertain.OutcomeUnknown,
                "material-decision timeout after write is uncertain and never silently retried");
        }
        var submit = new CoreRequestProtocol.SubmitText(requestId, "get system status").ToMessage();
        using (var submitJson = JsonDocument.Parse(submit))
            Check(submitJson.RootElement.GetProperty("protocol_version").GetInt32() == 1 &&
                submitJson.RootElement.GetProperty("message_type").GetString() == "submit_text" &&
                submitJson.RootElement.GetProperty("request_id").GetString() == requestId,
                "C# encodes the versioned text request with stable correlation");
        using (var stopJson = JsonDocument.Parse(new CoreRequestProtocol.StopRequest(requestId, taskId).ToMessage()))
            Check(stopJson.RootElement.GetProperty("message_type").GetString() == "stop" &&
                stopJson.RootElement.GetProperty("task_id").GetString() == taskId,
                "C# encodes STOP as an independent correlated request");
        using (var settingsJson = JsonDocument.Parse(new CoreRequestProtocol.SettingsQueryRequest(requestId).ToMessage()))
            Check(settingsJson.RootElement.GetProperty("message_type").GetString() == "settings_query" &&
                settingsJson.RootElement.GetProperty("request_id").GetString() == requestId,
                "C# encodes a versioned read-only settings query");
        using (var historyJson = JsonDocument.Parse(new CoreRequestProtocol.HistoryQueryRequest(requestId, taskId, 100).ToMessage()))
            Check(historyJson.RootElement.GetProperty("message_type").GetString() == "history_query" &&
                historyJson.RootElement.GetProperty("task_id").GetString() == taskId &&
                historyJson.RootElement.GetProperty("limit").GetInt32() == 100,
                "C# encodes a correlated, bounded task-history query");
        try { _ = new CoreRequestProtocol.HistoryQueryRequest(requestId, taskId, 101).ToMessage(); throw new Exception("Oversized history query accepted."); }
        catch (ArgumentOutOfRangeException) { Check(true, "C# refuses history queries beyond the shared result bound"); }
        try { _ = new CoreRequestProtocol.SubmitText(requestId, new string('x', 4097)).ToMessage(); throw new Exception("Oversized submit accepted."); }
        catch (ArgumentException) { Check(true, "C# refuses text beyond the shared protocol bound"); }
        try { CoreRequestProtocol.SubmissionAck.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"submission_ack\",\"request_id\":\"{requestId}\",\"accepted\":true,\"task_id\":null,\"error_code\":null,\"message\":\"bad\"}}")); throw new Exception("Inconsistent ack accepted."); }
        catch (JsonException) { Check(true, "C# refuses acknowledgements that claim acceptance without a task"); }
        var validAck = CoreRequestProtocol.SubmissionAck.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"submission_ack\",\"request_id\":\"{requestId}\",\"accepted\":true,\"task_id\":\"{taskId}\",\"error_code\":null,\"message\":\"accepted\"}}"));
        Check(validAck.Accepted && validAck.TaskId == taskId, "C# parses correlated accepted acknowledgement");
        try { CoreRequestProtocol.SubmissionAck.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"submission_ack\",\"request_id\":\"{requestId}\",\"request_id\":\"{requestId}\",\"accepted\":true,\"task_id\":\"{taskId}\",\"error_code\":null,\"message\":\"accepted\"}}")); throw new Exception("Duplicate ack field accepted."); }
        catch (JsonException) { Check(true, "C# rejects duplicate protocol fields"); }
        try { CoreRequestProtocol.SubmissionAck.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":2,\"message_type\":\"submission_ack\",\"request_id\":\"{requestId}\",\"accepted\":true,\"task_id\":\"{taskId}\",\"error_code\":null,\"message\":\"accepted\"}}")); throw new Exception("Wrong version accepted."); }
        catch (JsonException) { Check(true, "C# rejects unsupported protocol versions"); }
        var pending = CoreRequestProtocol.TerminalReadback.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"terminal_readback\",\"request_id\":\"{requestId}\",\"task_id\":\"{taskId}\",\"terminal\":false,\"final_state\":\"RUNNING\",\"completion_verified\":false,\"terminal_persisted\":null,\"has_residual\":false,\"route\":null,\"message\":\"Execution is in progress.\",\"duration_ms\":null}}"));
        Check(!pending.Terminal && !pending.CompletionVerified, "C# preserves pending state without claiming success");
        var stopAck = CoreRequestProtocol.StopAck.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"stop_ack\",\"request_id\":\"{requestId}\",\"status\":\"ok\",\"stop_contract\":\"pluma.stop.v1\",\"message\":\"STOP request processed.\",\"error_code\":null,\"tasks\":[],\"stopped_tasks\":[],\"stopped_count\":0,\"latch_acknowledged_count\":0}}"));
        Check(stopAck.RequestId == requestId && stopAck.StoppedCount == 0, "C# parses STOP receipt without inferring task completion");
        try { CoreRequestProtocol.TerminalReadback.Parse(Encoding.UTF8.GetBytes($"{{\"protocol_version\":1,\"message_type\":\"terminal_readback\",\"request_id\":\"{requestId}\",\"task_id\":\"{taskId}\",\"terminal\":false,\"final_state\":\"RUNNING\",\"completion_verified\":true,\"terminal_persisted\":null,\"has_residual\":false,\"route\":null,\"message\":\"bad\",\"duration_ms\":null}}")); throw new Exception("Pending success accepted."); }
        catch (JsonException) { Check(true, "C# rejects completion claims on pending work"); }

        await Exchange(Healthy, CoreConnectionFailure.None, result => result.Status is { Running: true, ActiveTasks: 2, VoiceEnabled: true }, "native message-mode status round trip");
        await Exchange(Healthy[..^1] + ",\"padding\":\"" + new string('x', 30000) + "\"}", CoreConnectionFailure.None,
            result => result.Status?.ActiveTasks == 2, "a native message larger than the read buffer is fully reassembled");
        await Exchange("{\"status\":\"ok\",\"running\":false,\"active_tasks\":0,\"voice_enabled\":false}", CoreConnectionFailure.None,
            result => result.HealthLabel == "Core stopped" && result.TaskLabel == "Idle", "reachable stopped core does not display running");
        await Exchange("{\"status\":\"error\",\"message\":\"private detail\"}", CoreConnectionFailure.Protocol, null, "server error cannot become successful health");
        await Exchange("not JSON", CoreConnectionFailure.Protocol, null, "malformed JSON is rejected");
        await Exchange("\0\0\0\u0004" + Healthy, CoreConnectionFailure.Protocol, null, "TCP length prefixes are not accepted on the Windows message pipe");
        await Exchange(new string(' ', CoreIpcClient.MaximumMessageBytes + 1), CoreConnectionFailure.Protocol, null, "oversized response is rejected at the byte bound");
        await Exchange(Healthy, CoreConnectionFailure.Authentication, null, "short authentication challenge is rejected", mode: "short-challenge");
        await Exchange(Healthy, CoreConnectionFailure.Authentication, null, "invalid authentication acknowledgement is rejected", mode: "bad-ack");

        string wrong = Path.Combine(Root, "wrong.key"); WritePrivateKey(wrong);
        await Exchange(Healthy, CoreConnectionFailure.Authentication, null, "wrong secret cannot authenticate", key: wrong);
        string broad = Path.Combine(Root, "broad.key"); WritePrivateKey(broad);
        FileSecurity broadSecurity = new FileInfo(broad).GetAccessControl();
        broadSecurity.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.WorldSid, null), FileSystemRights.Read, AccessControlType.Allow));
        new FileInfo(broad).SetAccessControl(broadSecurity);
        await using (var client = new CoreIpcClient(Options(PipeName(), broad)))
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.AccessDenied, "a broadly readable key is rejected before connecting");

        string nullDacl = Path.Combine(Root, "null.key"); WritePrivateKey(nullDacl);
        FileSecurity nullSecurity = new FileInfo(nullDacl).GetAccessControl();
        nullSecurity.SetSecurityDescriptorSddlForm("D:NO_ACCESS_CONTROL", AccessControlSections.Access);
        new FileInfo(nullDacl).SetAccessControl(nullSecurity);
        await using (var client = new CoreIpcClient(Options(PipeName(), nullDacl)))
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.AccessDenied,
                "a null credential DACL is rejected before connecting");

        await using (var client = new CoreIpcClient(Options(PipeName(), milliseconds: 180)))
        {
            var watch = Stopwatch.StartNew();
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.Timeout && watch.Elapsed < TimeSpan.FromSeconds(2), "missing server has a bounded connection deadline");
        }
        await using (var server = new LocalServer(PipeName(), Healthy, "stall"))
        await using (var client = new CoreIpcClient(Options(server.Name, milliseconds: 180)))
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.Timeout, "silent peer cannot hold authentication open indefinitely");

        await using (var server = new LocalServer(PipeName(), Healthy, "stall"))
        await using (var client = new CoreIpcClient(Options(server.Name)))
        using (var stop = new CancellationTokenSource(100))
        {
            var watch = Stopwatch.StartNew();
            try { await client.GetStatusAsync(stop.Token); throw new Exception("Cancellation ignored."); }
            catch (OperationCanceledException) { Check(watch.Elapsed < TimeSpan.FromSeconds(1), "caller cancellation interrupts an outstanding native read"); }
        }
        await using (var server = new LocalServer(PipeName(), Healthy, "stall"))
        {
            var client = new CoreIpcClient(Options(server.Name));
            Task<CoreStatusResult>[] pendingQueries = Enumerable.Range(0, 4).Select(_ => client.GetStatusAsync(default)).ToArray();
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.Busy, "concurrent status checks are bounded");
            await client.DisposeAsync();
            foreach (var query in pendingQueries)
            {
                try { await query; throw new Exception("Disposed query completed as health."); }
                catch (OperationCanceledException) { Check(true, "disposal cancels and awaits each owned query"); }
            }
            await client.DisposeAsync();
            try { await client.GetStatusAsync(default); throw new Exception("Disposed client reused."); }
            catch (ObjectDisposedException) { Check(true, "disposed client rejects new work and repeated disposal is safe"); }
        }

        string reconnect = PipeName();
        await using (var client = new CoreIpcClient(Options(reconnect, milliseconds: 250)))
        {
            await using (var server = new LocalServer(reconnect, Healthy))
                Check((await client.GetStatusAsync(default)).Status != null, "first authenticated connection succeeds");
            Check((await client.GetStatusAsync(default)).Status == null, "disconnect does not reuse cached connected status");
            await using (var server = new LocalServer(reconnect, Healthy))
                Check((await client.GetStatusAsync(default)).Status != null, "explicit refresh reconnects after server restart");
        }

        // P09: the production Python factory must create the fixture key.
        // The unchanged C# opened-handle reader then verifies its owner/DACL.
        string pythonDirectory = Path.Combine(Root, "Pluma");
        CreatePrivateDirectory(pythonDirectory);
        DirectorySecurity inherited = new DirectoryInfo(pythonDirectory).GetAccessControl();
        inherited.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null),
            FileSystemRights.Read, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(pythonDirectory).SetAccessControl(inherited);
        Check(!File.Exists(Path.Combine(Root, "Pluma", "ipc_secret.key")),
            "Python interoperability starts without a preseeded credential");
        await using (var python = await PythonServer.StartAsync(PipeName()))
        await using (var client = new CoreIpcClient(Options(python.Name, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            for (int index = 0; index < 2; index++)
            {
                CoreStatusResult result = await client.GetStatusAsync(default);
                Check(result.Status is { Running: true, ActiveTasks: 2, VoiceEnabled: true } && result.Status.RoundTripMilliseconds >= 0,
                    "production Python IPC server authenticates the C# client and returns a multi-buffer status message");
            }
        }

        string requestsPipe = PipeName();
        await using (var python = await PythonServer.StartAsync(requestsPipe, "versioned"))
        await using (var client = new CoreIpcClient(Options(requestsPipe, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            string wireRequestId = Guid.NewGuid().ToString("D");
            CoreRequestResult<CoreRequestProtocol.SubmissionAck> submitted =
                await client.SubmitTextAsync(wireRequestId, "fixture:success", default);
            Check(submitted.IsSuccess && submitted.Response is { Accepted: true, RequestId: var acceptedId } && acceptedId == wireRequestId,
                "authenticated C# submit reaches the Python resident and returns the same request identity");
            CoreRequestResult<CoreRequestProtocol.TerminalReadback>? readback = null;
            var deadline = Stopwatch.StartNew();
            while (deadline.Elapsed < TimeSpan.FromSeconds(3))
            {
                readback = await client.GetTerminalReadbackAsync(wireRequestId, submitted.Response!.TaskId!, default);
                if (readback.Response?.Terminal == true) break;
                await Task.Delay(20);
            }
            Check(readback is { IsSuccess: true, Response.Terminal: true, Response.CompletionVerified: true,
                Response.TerminalPersisted: true, Response.FinalState: "SUCCEEDED" },
                "authenticated C# readback observes Python task terminal and ledger verification");
            CoreRequestResult<CoreRequestProtocol.SettingsSnapshot> settings =
                await client.GetSettingsAsync(Guid.NewGuid().ToString("D"), default);
            Check(settings.IsSuccess && settings.Response is { MaxPlanSteps: > 0, VoiceRequired: true,
                PlannerModelPath: @"C:\fixture\planner.gguf", SttModelPath: @"C:\fixture\whisper.ggml" },
                "authenticated C# settings query returns the allowlisted Python configuration snapshot");
            CoreRequestResult<CoreRequestProtocol.HistoryReply> history =
                await client.GetHistoryAsync(Guid.NewGuid().ToString("D"), null, 10, default);
            Check(history.IsSuccess && history.Response!.Tasks.Any(task => task.TaskId == submitted.Response!.TaskId),
                "authenticated C# recent-history query reads the submitted task from the Activity Ledger");
            CoreRequestResult<CoreRequestProtocol.HistoryReply> taskHistory =
                await client.GetHistoryAsync(Guid.NewGuid().ToString("D"), submitted.Response!.TaskId, 100, default);
            Check(taskHistory.IsSuccess && taskHistory.Response!.TaskId == submitted.Response.TaskId,
                "authenticated C# task-history query preserves task correlation");

            await RemainingContractsAsync(client, requestsPipe);

            string holdRequestId = Guid.NewGuid().ToString("D");
            CoreRequestResult<CoreRequestProtocol.SubmissionAck> held =
                await client.SubmitTextAsync(holdRequestId, "fixture:hold", default);
            Check(held.IsSuccess && held.Response is { Accepted: true }, "blocking fixture task is accepted asynchronously");
            await python.WaitForLineAsync("TASK_ENTERED");
            string stopRequestId = Guid.NewGuid().ToString("D");
            CoreRequestResult<CoreRequestProtocol.StopAck> stop =
                await client.StopAsync(stopRequestId, held.Response!.TaskId, default);
            Check(stop.IsSuccess && stop.Response is { RequestId: var stoppedRequestId } && stoppedRequestId == stopRequestId,
                "priority authenticated STOP remains responsive during a blocked execution response");
            CoreRequestResult<CoreRequestProtocol.TerminalReadback>? stopped = null;
            deadline.Restart();
            while (deadline.Elapsed < TimeSpan.FromSeconds(3))
            {
                stopped = await client.GetTerminalReadbackAsync(holdRequestId, held.Response.TaskId!, default);
                if (stopped.Response?.Terminal == true) break;
                await Task.Delay(20);
            }
            Check(stopped is { IsSuccess: true, Response.Terminal: true, Response.CompletionVerified: false,
                Response.FinalState: "STOPPED" or "STOPPED_WITH_RESIDUAL" },
                "STOP terminal readback preserves stopped state without claiming completed execution");
        }

        string saturatedPipe = PipeName();
        await using (var python = await PythonServer.StartAsync(saturatedPipe, "versioned", saturate: true))
        await using (var client = new CoreIpcClient(Options(saturatedPipe, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            Task<CoreStatusResult>[] statusCalls = Enumerable.Range(0, 4)
                .Select(_ => client.GetStatusAsync(default)).ToArray();
            for (int index = 0; index < 4; index++) await python.WaitForLineAsync("STATUS_ENTERED");
            string stopId = Guid.NewGuid().ToString("D");
            CoreRequestResult<CoreRequestProtocol.StopAck> priorityStop = await client.StopAsync(stopId, null, default);
            Check(priorityStop.IsSuccess && priorityStop.Response?.RequestId == stopId,
                "reserved C# STOP call slot and Python priority handler remain available under four stalled calls");
            CoreStatusResult[] statuses = await Task.WhenAll(statusCalls);
            Check(statuses.All(result => result.Status is { Running: true }),
                "priority STOP releases the owned stalled status fixtures cleanly");
        }
    }

    private static async Task RemainingContractsAsync(CoreIpcClient client, string pipe)
    {
        string Id() => Guid.NewGuid().ToString("D");
        string clientId = Id();
        var opened = await client.GetConfirmationsAsync(Id(), clientId, default);
        Check(opened.IsSuccess && opened.Response!.Confirmations.Length == 0,
            "authenticated confirmation query opens a bounded logical client lease");
        var initial = await client.GetEventsAsync(new(Id()), default);
        Check(initial.IsSuccess && initial.Response!.ResetRequired, "event handshake requires factual snapshot readback");
        var cursor = new CoreEventCursor();
        cursor.Apply(initial.Response!);
        Check((await client.GetHistoryAsync(Id(), null, 100, default)).IsSuccess, "event resynchronization reads actual history");
        cursor.SnapshotRead();
        long? verifiedAction = null;
        foreach (string scenario in new[] { "approve", "deny", "stop", "disconnect" })
        {
            var submission = await client.SubmitTextAsync(Id(), "fixture:approval", default);
            Check(submission.IsSuccess && submission.Response!.Accepted, "owned confirmation fixture admitted: " + scenario);
            string taskId = submission.Response!.TaskId!;
            CoreRequestProtocol.ConfirmationView? item = null;
            var deadline = Stopwatch.StartNew();
            while (deadline.Elapsed < TimeSpan.FromSeconds(3))
            {
                var pending = await client.GetConfirmationsAsync(Id(), clientId, default);
                item = pending.Response?.Confirmations.SingleOrDefault(value => value.TaskId == taskId);
                if (item is not null) break;
                await Task.Delay(10);
            }
            Check(item is { Tool: "fixture_read", Risk: "HIGH" }, "material call is published with task and binding: " + scenario);
            var decision = new CoreRequestProtocol.ConfirmationDecisionRequest(Id(), clientId, taskId,
                item!.ConfirmationId, item.Binding, scenario == "approve");
            if (scenario == "approve")
            {
                var mismatch = await client.DecideConfirmationAsync(decision with { Binding = new string('0', 64) }, default);
                Check(mismatch.Response is { Accepted: false, ErrorCode: "CONFIRMATION_MISMATCH" }, "changed exact-call binding cannot approve");
                Check((await client.DecideConfirmationAsync(decision, default)).Response is { Accepted: true, Approved: true },
                    "exact material approval is recorded once");
                Check((await client.DecideConfirmationAsync(decision, default)).Response is { Accepted: false, ErrorCode: "CONFIRMATION_NOT_PENDING" },
                    "duplicate decision cannot approve a second call");
            }
            else if (scenario == "deny")
                Check((await client.DecideConfirmationAsync(decision, default)).Response is { Accepted: true, Approved: false },
                    "explicit denial is recorded without authorizing execution");
            else if (scenario == "stop")
            {
                Check((await client.StopAsync(Id(), taskId, default)).IsSuccess, "STOP remains responsive during material approval");
                Check((await client.DecideConfirmationAsync(decision with { Approved = true }, default)).Response is { Accepted: false },
                    "late approval cannot revive a stopped task");
            }
            else
                Check((await client.DisconnectConfirmationsAsync(Id(), clientId, default)).Response is { DeniedCount: 1 },
                    "logical UI disconnect denies its pending material operation");

            CoreRequestProtocol.TerminalReadback? terminal = null;
            deadline.Restart();
            while (deadline.Elapsed < TimeSpan.FromSeconds(3))
            {
                terminal = (await client.GetTerminalReadbackAsync(submission.Response.RequestId, taskId, default)).Response;
                if (terminal?.Terminal == true) break;
                await Task.Delay(10);
            }
            Check(terminal is { Terminal: true, TerminalPersisted: true } &&
                (scenario == "approve" ? terminal is { FinalState: "SUCCEEDED", CompletionVerified: true }
                    : !terminal.CompletionVerified && terminal.FinalState is "FAILED" or "STOPPED" or "STOPPED_WITH_RESIDUAL"),
                "terminal and ledger preserve the exact decision outcome: " + scenario);
            var history = await client.GetHistoryAsync(Id(), taskId, 100, default);
            if (scenario == "approve")
            {
                var action = history.Response!.Actions.Single();
                verifiedAction = action.ActionId;
                Check(action is { Tool: "fixture_read", Verified: true, ApprovalState: "ALLOW" },
                    "registered owned-file action has independent postcondition and policy ledger readback");
            }
            else
                Check(history.IsSuccess && history.Response!.Actions.All(action => !action.Verified),
                    "unapproved task contains no verified fixture execution: " + scenario);
        }
        var request = new CoreRequestProtocol.EventsQueryRequest(Id(), cursor.StreamId, cursor.Sequence);
        var batch = await client.GetEventsAsync(request, default);
        Check(batch.IsSuccess && batch.Response!.Events.Any(item => item.Kind == "action_recorded" && item.RecordId == verifiedAction),
            "authenticated event feed names the actual committed verified action identity");
        Check(cursor.Apply(batch.Response!).Length > 0, "C# event cursor applies committed facts in sequence");
        var replay = await client.GetEventsAsync(request with { RequestId = Id() }, default);
        Check(replay.IsSuccess && cursor.Apply(replay.Response!).Length == 0, "replayed event batch is deduplicated without cursor regression");
        await using (var reconnect = new CoreIpcClient(Options(pipe, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            var resumed = await reconnect.GetEventsAsync(new(Id(), cursor.StreamId, cursor.Sequence), default);
            Check(resumed.IsSuccess && !resumed.Response!.ResetRequired && resumed.Response.Events.Length == 0,
                "a new authenticated connection resumes the same durable event cursor");
        }
        var wrongStream = await client.GetEventsAsync(new(Id(), Id(), 0), default);
        Check(wrongStream.IsSuccess && wrongStream.Response!.ResetRequired && wrongStream.Response.Events.Length == 0,
            "replaced database identity requires snapshot resynchronization instead of invented continuity");
        try { CoreRequestProtocol.EventBatch.Parse("{}"u8); throw new Exception("Missing event fields accepted."); }
        catch (JsonException) { Check(true, "required event fields cannot default into a successful cursor"); }
        try { CoreRequestProtocol.ConfirmationAck.Parse("{}"u8); throw new Exception("Missing decision fields accepted."); }
        catch (JsonException) { Check(true, "required decision fields cannot default into approval"); }
        long before = cursor.Sequence;
        var gap = batch.Response! with { Events = [batch.Response.Events[0] with { Sequence = before + 2 }], NextSequence = before + 2 };
        try { cursor.Apply(gap); throw new Exception("Event gap accepted."); }
        catch (JsonException) { Check(cursor.Sequence == before, "event gaps refuse without partially changing the consumer cursor"); }
        var ahead = await client.GetEventsAsync(new(Id(), cursor.StreamId, cursor.Sequence + 1000), default);
        Check(ahead.IsSuccess && ahead.Response!.ResetRequired, "an impossible future cursor requires explicit resynchronization");
        cursor.Apply(ahead.Response!);
        Check(cursor.RequiresSnapshot && cursor.Sequence == ahead.Response!.LastSequence,
            "the consumer honors reset readback even when saved cursor was ahead of the journal");
        await ConfirmationControllerChecks.RunNativeAsync(client, Check);
    }

    private static async Task Exchange(string reply, CoreConnectionFailure expected, Func<CoreStatusResult, bool>? additional, string label, string mode = "normal", string? key = null)
    {
        await using var server = new LocalServer(PipeName(), reply, mode);
        await using var client = new CoreIpcClient(Options(server.Name, key));
        CoreStatusResult result = await client.GetStatusAsync(default);
        Check(result.Failure == expected && (additional?.Invoke(result) ?? result.Status == null), label + " (" + result.Failure + ")");
        if (expected == CoreConnectionFailure.None) Check(server.StatusOnly, "client sends only the registered read-only status request");
    }

    private static void CreatePrivateDirectory(string path)
    {
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        var security = new DirectorySecurity(); security.SetOwner(identity.User!); security.SetAccessRuleProtection(true, false);
        security.AddAccessRule(new FileSystemAccessRule(identity.User!, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
        new DirectoryInfo(path).Create(security);
    }
    private static void WritePrivateKey(string path)
    {
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        var security = new FileSecurity(); security.SetOwner(identity.User!); security.SetAccessRuleProtection(true, false);
        security.AddAccessRule(new FileSystemAccessRule(identity.User!, FileSystemRights.FullControl, AccessControlType.Allow));
        using FileStream file = new FileInfo(path).Create(FileMode.CreateNew, FileSystemRights.FullControl, FileShare.None, 32, FileOptions.None, security);
        byte[] key = RandomNumberGenerator.GetBytes(32); file.Write(key); CryptographicOperations.ZeroMemory(key);
    }

    private sealed class LocalServer : IAsyncDisposable
    {
        internal string Name { get; }
        internal bool StatusOnly { get; private set; }
        private readonly NamedPipeServerStream _pipe;
        private readonly CancellationTokenSource _stop = new(TimeSpan.FromSeconds(8));
        private readonly Task _task;
        internal LocalServer(string name, string reply, string mode = "normal")
        {
            Name = name;
            _pipe = new(name, PipeDirection.InOut, 1, PipeTransmissionMode.Message, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
            _task = RunAsync(reply, mode);
        }
        private async Task RunAsync(string reply, string mode)
        {
            try
            {
                await _pipe.WaitForConnectionAsync(_stop.Token);
                if (mode == "stall") { await Task.Delay(Timeout.Infinite, _stop.Token); return; }
                byte[] nonce = RandomNumberGenerator.GetBytes(mode == "short-challenge" ? 31 : 32);
                await _pipe.WriteAsync(nonce, _stop.Token);
                byte[] token = await ReadAsync();
                byte[] key = File.ReadAllBytes(Secret);
                byte[] proof = HMACSHA256.HashData(key, nonce); CryptographicOperations.ZeroMemory(key);
                bool accepted = CryptographicOperations.FixedTimeEquals(token, proof);
                CryptographicOperations.ZeroMemory(token); CryptographicOperations.ZeroMemory(proof);
                if (!accepted) return;
                await _pipe.WriteAsync(Encoding.ASCII.GetBytes(mode == "bad-ack" ? "BAD_ACK" : "AUTH_OK"), _stop.Token);
                string request = Encoding.UTF8.GetString(await ReadAsync());
                StatusOnly = request == "{\"command\":\"status\"}";
                if (mode == "stall-response")
                { await Task.Delay(Timeout.Infinite, _stop.Token); return; }
                if (StatusOnly) await _pipe.WriteAsync(Encoding.UTF8.GetBytes(reply), _stop.Token);
            }
            catch (Exception error) when (error is IOException or OperationCanceledException or ObjectDisposedException) { }
            finally { _pipe.Dispose(); }
        }
        private async Task<byte[]> ReadAsync()
        {
            byte[] buffer = new byte[1024];
            int count = await _pipe.ReadAsync(buffer, _stop.Token);
            if (count == 0 || !_pipe.IsMessageComplete) throw new IOException();
            return buffer[..count];
        }
        public async ValueTask DisposeAsync() { _stop.Cancel(); _pipe.Dispose(); await _task; _stop.Dispose(); }
    }

    private sealed class PythonServer : IAsyncDisposable
    {
        internal string Name { get; }
        private readonly Process _process;
        private readonly DateTime _created;
        private readonly string _executable;
        private readonly Task<string> _errors;
        private PythonServer(string name, Process process)
        {
            Name = name; _process = process; _created = process.StartTime.ToUniversalTime();
            _executable = Path.GetFileNameWithoutExtension(process.StartInfo.FileName); _errors = process.StandardError.ReadToEndAsync();
            Console.WriteLine($"OWNED fixture {name}; PID {process.Id}; created {_created:O}; command class Python IPC fixture");
        }
        internal static async Task<PythonServer> StartAsync(string name, string mode = "status", bool saturate = false)
        {
            string script = Path.Combine(Directory.GetCurrentDirectory(), "PLUMA.UI", "CoreIpc.Tests", "fixture_server.py");
            var info = new ProcessStartInfo(Environment.GetEnvironmentVariable("PLUMA_TEST_PYTHON") ?? "python")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (string argument in new[] { "-u", script, name, Root, mode, saturate ? "saturate" : "normal" }) info.ArgumentList.Add(argument);
            var fixture = new PythonServer(name, Process.Start(info) ?? throw new InvalidOperationException("Fixture process did not start."));
            try
            {
                string? ready = await fixture._process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(8));
                if (ready != "READY") throw new InvalidOperationException("Python IPC fixture did not become ready.");
                return fixture;
            }
            catch { await fixture.DisposeAsync(); throw; }
        }
        internal async Task WaitForLineAsync(string expected)
        {
            string? line = await _process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(8));
            if (line != expected) throw new InvalidOperationException($"Expected fixture event {expected}, received {line ?? "<eof>"}.");
        }
        public async ValueTask DisposeAsync()
        {
            try
            {
                if (!_process.HasExited)
                {
                    await _process.StandardInput.WriteLineAsync("stop"); await _process.StandardInput.FlushAsync();
                    // The fixture's IpcServer.stop owns a four-second shutdown
                    // budget; let that cleanup finish before considering a kill.
                    try { await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(6)); }
                    catch (TimeoutException)
                    {
                        using Process current = Process.GetProcessById(_process.Id);
                        string? image = current.MainModule?.FileName;
                        if (current.StartTime.ToUniversalTime() != _created ||
                            image is null || !string.Equals(Path.GetFileNameWithoutExtension(image), _executable, StringComparison.OrdinalIgnoreCase))
                            throw new InvalidOperationException("Owned fixture identity changed; cleanup refused.");
                        _process.Kill(true); await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(3));
                    }
                }
                string errors = await _errors;
                if (_process.ExitCode != 0) throw new InvalidOperationException("Python IPC fixture exited unsuccessfully: " + errors);
            }
            finally { _process.Dispose(); }
        }
    }
}
