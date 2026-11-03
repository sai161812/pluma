using System.Diagnostics;
using System.Text;
using System.Text.Json;
using PLUMA.UI;

internal static partial class Program
{
    private static async Task<CoreRequestProtocol.TerminalReadback?> SettingsTerminalAsync(
        CoreIpcClient client, CoreRequestProtocol.SubmissionAck ack)
    {
        var clock = Stopwatch.StartNew();
        while (clock.Elapsed < TimeSpan.FromSeconds(12))
        {
            var terminal = (await client.GetTerminalReadbackAsync(ack.RequestId, ack.TaskId!, default)).Response;
            if (terminal?.Terminal == true) return terminal;
            await Task.Delay(10);
        }
        throw new InvalidOperationException("Owned settings task did not complete within its tool/cleanup budget.");
    }

    private static async Task RunSettingsAsync()
    {
        static string Id() => Guid.NewGuid().ToString("D");
        bool rejected = false;
        try { _ = new CoreRequestProtocol.SettingsSaveRequest(Id(), "absent", new(MaxPlanSteps: 21)).ToMessage(); }
        catch (ArgumentException) { rejected = true; }
        Check(rejected, "settings writer refuses an excessive local plan limit");
        rejected = false;
        try { _ = new CoreRequestProtocol.SettingsSaveRequest(Id(), "absent", new()).ToMessage(); }
        catch (ArgumentException) { rejected = true; }
        Check(rejected, "settings writer refuses an empty edit");
        string snapshot = "{\"protocol_version\":1,\"message_type\":\"settings_edit_snapshot\",\"request_id\":\"" + Id()
            + "\",\"revision\":\"absent\",\"persisted\":{\"text_hotkey\":\"alt+space\",\"stop_hotkey\":\"ctrl+alt+esc\",\"voice_hotkey\":\"ctrl+alt+v\",\"max_plan_steps\":8},"
            + "\"effective\":{\"text_hotkey\":\"alt+space\",\"stop_hotkey\":\"ctrl+alt+esc\",\"voice_hotkey\":\"ctrl+alt+v\",\"max_plan_steps\":8},\"restart_fields\":[],\"editable_fields\":[\"max_plan_steps\"]}";
        Check(CoreRequestProtocol.SettingsEditSnapshot.Parse(Encoding.UTF8.GetBytes(snapshot)).RestartFields.Length == 0,
            "settings parser accepts consistent persisted and effective snapshots");
        foreach (string invalid in new[] { snapshot.Replace("\"restart_fields\":[]", "\"restart_fields\":[\"max_plan_steps\"]"),
            snapshot.Replace("\"revision\":\"absent\"", "\"revision\":\"bad\""), snapshot.Replace("\"protocol_version\":1", "\"protocol_version\":1,\"protocol_version\":1") })
        {
            rejected = false;
            try { _ = CoreRequestProtocol.SettingsEditSnapshot.Parse(Encoding.UTF8.GetBytes(invalid)); }
            catch (JsonException) { rejected = true; }
            Check(rejected, "settings parser rejects contradictory, malformed or duplicate data");
        }

        string clientId = Id();
        string pipe = PipeName();
        await using (var python = await PythonServer.StartAsync(pipe, "settings"))
        await using (var client = new CoreIpcClient(Options(pipe, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            var initial = await client.GetSettingsEditAsync(Id(), default);
            Check(initial.Response is { Revision: "absent", Persisted.MaxPlanSteps: 8, Effective.MaxPlanSteps: 8 },
                "native settings readback starts from isolated real defaults");
            Check((await client.GetConfirmationsAsync(Id(), clientId, default)).IsSuccess,
                "settings client connects the actual material-confirmation broker");
            foreach (bool approve in new[] { true, false })
            {
                var current = (await client.GetSettingsEditAsync(Id(), default)).Response!;
                var request = new CoreRequestProtocol.SettingsSaveRequest(Id(), current.Revision,
                    new(MaxPlanSteps: approve ? 4 : 5));
                var submission = await client.SaveSettingsAsync(request, default);
                Check(submission.Response is { Accepted: true }, "settings Save admits an owned typed task");
                CoreRequestProtocol.ConfirmationView? confirmation = null;
                var clock = Stopwatch.StartNew();
                while (clock.Elapsed < TimeSpan.FromSeconds(3))
                {
                    confirmation = (await client.GetConfirmationsAsync(Id(), clientId, default)).Response?.Confirmations
                        .SingleOrDefault(item => item.TaskId == submission.Response!.TaskId);
                    if (confirmation is not null) break;
                    await Task.Delay(10);
                }
                Check(confirmation is { Tool: "save_settings", Risk: "MEDIUM" },
                    "settings Save publishes the exact registered policy decision");
                var decision = new CoreRequestProtocol.ConfirmationDecisionRequest(Id(), clientId,
                    confirmation!.TaskId, confirmation.ConfirmationId, confirmation.Binding, approve);
                Check((await client.DecideConfirmationAsync(decision, default)).Response is { Accepted: true },
                    "settings material decision is correlated to its actual task");
                var terminal = await SettingsTerminalAsync(client, submission.Response!);
                Check(terminal is { TerminalPersisted: true } && (approve
                    ? terminal is { FinalState: "SUCCEEDED", CompletionVerified: true }
                    : terminal is { FinalState: "FAILED", CompletionVerified: false }),
                    "settings terminal/ledger readback reflects actual approval or denial");
                var observed = (await client.GetSettingsEditAsync(Id(), default)).Response!;
                Check(observed.Persisted.MaxPlanSteps == 4 && observed.Effective.MaxPlanSteps == 8
                    && observed.RestartFields.SequenceEqual(new[] { "max_plan_steps" }),
                    "native settings readback never claims saved values are already active");
                var history = await client.GetHistoryAsync(Id(), submission.Response!.TaskId, 10, default);
                Check(history.Response!.Actions.Single().Verified == approve,
                    "independent saved action agrees with settings verification and denial");
                Check((await client.SaveSettingsAsync(request, default)).Response?.TaskId == submission.Response.TaskId,
                    "duplicate settings request reads its accepted task without replaying the write");
            }
        }
        pipe = PipeName();
        await using (var python = await PythonServer.StartAsync(pipe, "settings_restart"))
        await using (var client = new CoreIpcClient(Options(pipe, Path.Combine(Root, "Pluma", "ipc_secret.key"))))
        {
            var restarted = await client.GetSettingsEditAsync(Id(), default);
            Check(restarted.Response is { Persisted.MaxPlanSteps: 4, Effective.MaxPlanSteps: 4, RestartFields.Length: 0 },
                "actual new Python runtime consumes saved settings after owned restart");
        }
    }
}
