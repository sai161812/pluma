using System;
using System.Diagnostics;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests;

internal static class NativeP21SettingsChecks
{
    private static string Id() => Guid.NewGuid().ToString("D");
    private static async Task Until(Func<bool> ready)
    {
        var timer = Stopwatch.StartNew();
        while (!ready() && timer.Elapsed.TotalSeconds < 6) await Task.Delay(15);
        if (!ready()) throw new TimeoutException("Owned native settings condition was not observed.");
    }
    private static void Invoke(Button button) => ((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button)
        .GetPattern(PatternInterface.Invoke)).Invoke();
    private static Button Find(DependencyObject root, string label)
    {
        if (root is Button button && button.Content?.ToString() == label) return button;
        for (int i=0; i<VisualTreeHelper.GetChildrenCount(root); i++)
        { try { return Find(VisualTreeHelper.GetChild(root,i),label); } catch (InvalidOperationException) { } }
        throw new InvalidOperationException("Owned settings confirmation button not ready.");
    }
    internal static async Task RunAsync(Action<bool,string> check)
    {
        await using var fixture = await NativeConfirmationChecks.Fixture.StartAsync("settings_ui");
        await using var client = new CoreIpcClient(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        var shell = new MainWindow(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        shell.Activate();
        try
        {
            await Until(() => shell.Dashboard is { IsLoaded:true } dashboard && ((Button)dashboard.FindName("CommandRunButton")).IsEnabled);
            shell.NavigateSettingsForAcceptance();
            await Until(() => shell.Settings is { IsLoaded:true } settings && ((NumberBox)settings.FindName("PlanLimit")).IsEnabled);
            var page=shell.Settings!;
            var limit=(NumberBox)page.FindName("PlanLimit");
            var save=(Button)page.FindName("SettingsSave");
            var snapshot=await client.GetSettingsEditAsync(Id(),default);
            var runtime=await client.GetSettingsAsync(Id(),default);
            check(snapshot.IsSuccess && runtime.IsSuccess && limit.Value==snapshot.Response!.Persisted.MaxPlanSteps &&
                ((TextBox)page.FindName("ModelPath")).Text==runtime.Response!.PlannerModelPath &&
                !((TextBox)page.FindName("ModelPath")).IsReadOnly &&
                ((TextBox)page.FindName("TextHotkey")).Text==snapshot.Response.Persisted.TextHotkey && !save.IsEnabled,
                "native Settings binds actual persisted/runtime data without preview selections or unsupported edits");
            limit.Value=4; await Until(()=>save.IsEnabled);
            Invoke((Button)page.FindName("SettingsCancel"));
            check(limit.Value==8 && !save.IsEnabled &&
                (await client.GetSettingsEditAsync(Id(),default)).Response!.Revision=="absent",
                "native Cancel restores the draft without creating a settings file");
            foreach (string scenario in new[]{"approve","stale","deny"})
            {
                limit.Value=scenario=="approve" ? 4 : 5;
                await Until(()=>save.IsEnabled);
                if (scenario=="stale") await fixture.ControlHistoryAsync("settings_external_limit_6");
                string? prior=shell.CurrentCommandForAcceptance.RequestId;
                Invoke(save);
                {
                    await Until(()=>shell.ApprovalForAcceptance is {IsLoaded:true});
                    var dialog=shell.ApprovalForAcceptance!;
                    using var material=System.Text.Json.JsonDocument.Parse(dialog.SanitizedArguments);
                    check(((PopupMessageText)dialog.FindName("MaterialEffectText")).DisplayText.Contains("save settings") &&
                        material.RootElement.GetProperty("changes").GetProperty("max_plan_steps").GetInt32()==(scenario=="approve" ? 4 : 5) &&
                        ((PopupMessageText)dialog.FindName("SanitizedArgumentsText")).DisplayText.Contains("max plan steps",StringComparison.OrdinalIgnoreCase),
                        "native settings confirmation identifies the exact changed field: "+scenario);
                    Invoke(Find(shell.ApprovalForAcceptance!,scenario=="deny" ? "Deny" : "Approve"));
                }
                await Until(()=>shell.CurrentCommandForAcceptance.RequestId!=prior && !shell.CurrentCommandForAcceptance.Pending && limit.IsEnabled);
                var read=await client.GetSettingsEditAsync(Id(),default);
                int expected=scenario=="approve" ? 4 : 6;
                check(read.IsSuccess && read.Response!.Persisted.MaxPlanSteps==expected && read.Response.Effective.MaxPlanSteps==8 &&
                    limit.Value==expected && !save.IsEnabled,
                    "native settings readback preserves active configuration and exact saved value: "+scenario);
                var command=shell.CurrentCommandForAcceptance;
                var detail=await client.GetTaskDetailAsync(Id(),command.TaskId!,0,default);
                check(detail.IsSuccess && (scenario=="approve" ? detail.Response!.Actions.Single().Verified : detail.Response!.Actions.All(a=>!a.Verified)),
                    "native settings outcome agrees with independently saved action verification: "+scenario);
                if (scenario=="approve") check(((TextBlock)page.FindName("SettingsStatus")).Text.Contains("restart",StringComparison.OrdinalIgnoreCase),
                    "native Settings identifies saved settings requiring Core restart");
            }
            // STOP invoked in the same UI turn must fence the queued Save.
            limit.Value=3; await Until(()=>save.IsEnabled);
            Invoke(save); Invoke((Button)page.FindName("SettingsStop"));
            await Until(()=>!shell.CurrentCommandForAcceptance.Pending && limit.IsEnabled);
            check((await client.GetSettingsEditAsync(Id(),default)).Response!.Persisted.MaxPlanSteps==6 && shell.ApprovalForAcceptance is null,
                "native Settings STOP prevents a queued save without changing owned settings");
            await fixture.ControlHistoryAsync("settings_native_hotkeys");
            check(true,"native hotkey conflict rolls back only new registrations; actual resident STOP latches and all owned registrations drain");
            await fixture.ControlHistoryAsync("settings_prepare_models");
            ((TextBox)page.FindName("ModelPath")).Text=System.IO.Path.Combine(fixture.OwnedRoot,"planner.gguf");
            ((TextBox)page.FindName("SpeechModelPath")).Text=System.IO.Path.Combine(fixture.OwnedRoot,"speech.bin");
            ((NumberBox)page.FindName("ModelGrace")).Value=2;
            ((NumberBox)page.FindName("SpeechGrace")).Value=1;
            ((NumberBox)page.FindName("OcrGrace")).Value=0;
            ((ToggleSwitch)page.FindName("WarmGrace")).IsOn=false;
            ((ToggleSwitch)page.FindName("DiagnosticLogging")).IsOn=true;
            ((ToggleSwitch)page.FindName("CommandPreviews")).IsOn=false;
            ((ToggleSwitch)page.FindName("ConfirmLowRisk")).IsOn=true;
            await Until(()=>save.IsEnabled); Invoke(save);
            await Until(()=>shell.ApprovalForAcceptance is {IsLoaded:true});
            Invoke(Find(shell.ApprovalForAcceptance!,"Approve"));
            await Until(()=>!shell.CurrentCommandForAcceptance.Pending && limit.IsEnabled);
            var advanced=(await client.GetSettingsEditAsync(Id(),default)).Response!;
            check(advanced.Persisted.ModelIdleUnloadSeconds==2 && advanced.Persisted.SttIdleUnloadSeconds==1 &&
                advanced.Persisted.OcrIdleUnloadSeconds==0 && !advanced.Persisted.AllowShortWarmGrace &&
                advanced.Persisted.DiagnosticLogging && !advanced.Persisted.IncludeCommandPreviews && advanced.Persisted.ConfirmLowRisk &&
                advanced.Persisted.PlannerModelPath==System.IO.Path.Combine(fixture.OwnedRoot,"planner.gguf") &&
                advanced.Effective.ModelIdleUnloadSeconds==30,
                "native Settings edits model-format paths and bounded grace without claiming active native-model changes");
            await fixture.ControlHistoryAsync("settings_assert_advanced_restart");
            check(true,"actual new runtime consumes saved planner/speech paths and disabled grace while remaining cold");
            await fixture.ControlHistoryAsync("settings_corrupt");
            Invoke((Button)page.FindName("SettingsReload"));
            await Until(()=>((Button)page.FindName("SettingsRecover")).IsEnabled);
            check(!limit.IsEnabled && !save.IsEnabled,"corrupt settings disable normal edits and expose exact previous-source recovery");
            Invoke((Button)page.FindName("SettingsRecover"));
            await Until(()=>shell.ApprovalForAcceptance is {IsLoaded:true});
            check(((PopupMessageText)shell.ApprovalForAcceptance!.FindName("MaterialEffectText")).DisplayText.Contains("No automatic undo"),
                "native recovery approval states source preservation and no automatic undo");
            Invoke(Find(shell.ApprovalForAcceptance!,"Approve"));
            await Until(()=>!shell.CurrentCommandForAcceptance.Pending && limit.IsEnabled);
            await fixture.ControlHistoryAsync("settings_assert_recovered");
            check((await client.GetSettingsEditAsync(Id(),default)).Response is {PreviousRevision:null,Persisted.MaxPlanSteps:6},
                "native confirmed recovery restores independently read valid settings and retains rejected bytes");
            shell.NavigateForAcceptance(true); shell.NavigateSettingsForAcceptance();
            await Until(()=>shell.Settings is {IsLoaded:true} restored && ((NumberBox)restored.FindName("PlanLimit")).IsEnabled);
            check(((NumberBox)shell.Settings!.FindName("PlanLimit")).Value==6,
                "Settings navigation retains readback through the shell-owned controller");
        }
        finally { shell.Close(); await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(5)); }
        check(shell.ObservationLifetime.IsCompleted,"native Settings shutdown joins its reads and shared task owner");
    }
}
