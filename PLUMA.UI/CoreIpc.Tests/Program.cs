using System.Diagnostics;
using System.IO.Pipes;
using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
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
            Console.WriteLine($"{_checks} IPC checks passed. No production core, microphone or tool execution was started.");
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
            Task<CoreStatusResult>[] pending = Enumerable.Range(0, 4).Select(_ => client.GetStatusAsync(default)).ToArray();
            Check((await client.GetStatusAsync(default)).Failure == CoreConnectionFailure.Busy, "concurrent status checks are bounded");
            await client.DisposeAsync();
            foreach (var query in pending)
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
                StatusOnly = Encoding.UTF8.GetString(await ReadAsync()) == "{\"command\":\"status\"}";
                if (StatusOnly) await _pipe.WriteAsync(Encoding.UTF8.GetBytes(reply), _stop.Token);
            }
            catch (Exception error) when (error is IOException or OperationCanceledException or ObjectDisposedException) { }
            finally { _pipe.Dispose(); }
        }
        private async Task<byte[]> ReadAsync()
        {
            byte[] buffer = new byte[128];
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
            _executable = process.MainModule!.FileName; _errors = process.StandardError.ReadToEndAsync();
            Console.WriteLine($"OWNED fixture {name}; PID {process.Id}; created {_created:O}; command class Python IPC fixture");
        }
        internal static async Task<PythonServer> StartAsync(string name)
        {
            string script = Path.Combine(Directory.GetCurrentDirectory(), "PLUMA.UI", "CoreIpc.Tests", "fixture_server.py");
            var info = new ProcessStartInfo(Environment.GetEnvironmentVariable("PLUMA_TEST_PYTHON") ?? "python")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (string argument in new[] { "-u", script, name, Root }) info.ArgumentList.Add(argument);
            var fixture = new PythonServer(name, Process.Start(info) ?? throw new InvalidOperationException("Fixture process did not start."));
            try
            {
                string? ready = await fixture._process.StandardOutput.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(8));
                if (ready != "READY") throw new InvalidOperationException("Python IPC fixture did not become ready.");
                return fixture;
            }
            catch { await fixture.DisposeAsync(); throw; }
        }
        public async ValueTask DisposeAsync()
        {
            try
            {
                if (!_process.HasExited)
                {
                    await _process.StandardInput.WriteLineAsync("stop"); await _process.StandardInput.FlushAsync();
                    try { await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(3)); }
                    catch (TimeoutException)
                    {
                        using Process current = Process.GetProcessById(_process.Id);
                        if (current.StartTime.ToUniversalTime() != _created || current.MainModule?.FileName != _executable)
                            throw new InvalidOperationException("Owned fixture identity changed; cleanup refused.");
                        _process.Kill(true); await _process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(3));
                    }
                }
                await _errors;
                if (_process.ExitCode != 0) throw new InvalidOperationException("Python IPC fixture exited unsuccessfully.");
            }
            finally { _process.Dispose(); }
        }
    }
}
