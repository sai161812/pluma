using System;
using System.Diagnostics;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests;

internal static class NativeP22HealthChecks
{
    private static string Id()=>Guid.NewGuid().ToString("D");
    private static async Task Until(Func<bool> ready)
    {var timer=Stopwatch.StartNew();while(!ready()&&timer.Elapsed.TotalSeconds<6)await Task.Delay(15);if(!ready())throw new TimeoutException("Owned native health UI condition was not observed.");}
    private static void Invoke(Button button)=>((IInvokeProvider)FrameworkElementAutomationPeer.CreatePeerForElement(button).GetPattern(PatternInterface.Invoke)).Invoke();
    private static Button Find(DependencyObject root,string text)
    {
        if(root is Button button&&button.Content?.ToString()==text)return button;
        for(int i=0;i<VisualTreeHelper.GetChildrenCount(root);i++)
        {try{return Find(VisualTreeHelper.GetChild(root,i),text);}catch(InvalidOperationException){}}
        throw new InvalidOperationException("Owned dialog button is not ready.");
    }
    internal static async Task RunAsync(Action<bool,string> check)
    {
        await using var fixture=await NativeConfirmationChecks.Fixture.StartAsync("health");
        await using var client=new CoreIpcClient(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        var shell=new MainWindow(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        shell.Activate();
        try
        {
            await Until(()=>shell.Dashboard is {IsLoaded:true} dashboard&&((Button)dashboard.FindName("CommandRunButton")).IsEnabled);
            var initial=(await client.GetHealthAsync(Id(),default)).Response!;
            check(initial is {State:"READY",HotkeysRegistered:true,SetupReady:false}&&initial.Checks.Length==0,
                "native managed Core starts with actual hotkeys and cold unverified setup, not fabricated capability success");
            Invoke((Button)shell.Dashboard!.FindName("SetupButton"));
            await Until(()=>shell.Setup is {IsLoaded:true} setup&&((Button)setup.FindName("RecheckButton")).IsEnabled);
            var page=shell.Setup!;
            check(!((CheckBox)page.FindName("MicrophoneConsent")).IsChecked!.Value&&!((Button)page.FindName("NextButton")).IsEnabled,
                "native setup requires explicit microphone consent and evidence before navigation");
            Invoke((Button)page.FindName("RecheckButton"));
            await Until(()=>!shell.CurrentCommandForAcceptance.Pending&&((Button)page.FindName("RecheckButton")).IsEnabled);
            var observed=(await client.GetHealthAsync(Id(),default)).Response!;
            check(observed.Checks.Length==5&&observed.NativeVerified&&!observed.SetupReady&&
                Array.Exists(observed.Checks,c=>c.Id=="microphone"&&c.State=="UNVERIFIED"),
                "actual owned native probes report unavailable runtimes and unconsented microphone without enabling Continue");
            check(!((Button)page.FindName("NextButton")).IsEnabled,"native unavailable dependency results keep setup blocked");
            shell.NavigateForAcceptance(true);
            await Until(()=>shell.Dashboard is {IsLoaded:true});
            foreach(bool corrupt in new[]{false,true,false})
            {
                if(corrupt)await fixture.ControlHistoryAsync("health_corrupt");
                else await fixture.ControlHistoryAsync("health_repair");
                var before=(await client.GetHealthAsync(Id(),default)).Response!;
                Invoke((Button)shell.Dashboard!.FindName("RecoveryButton"));
                await Until(()=>shell.CriticalForAcceptance is {IsLoaded:true,CanRestart:true});
                Invoke(Find(shell.CriticalForAcceptance!,"Restart core"));
                await Until(()=>shell.ApprovalForAcceptance is {IsLoaded:true});
                check(((PopupMessageText)shell.ApprovalForAcceptance!.FindName("MaterialEffectText")).DisplayText.Contains("owned Core"),
                    "native recovery uses the exact existing material-approval boundary");
                Invoke(Find(shell.ApprovalForAcceptance!,"Approve"));
                CoreHealthProtocol.Snapshot? after=null;
                var clock=Stopwatch.StartNew();
                while(clock.Elapsed.TotalSeconds<8)
                {
                    after=(await client.GetHealthAsync(Id(),default)).Response;
                    if(after is not null&&after.InstanceId!=before.InstanceId&&after.State is "READY" or "CONFIGURATION_ERROR")break;
                    await Task.Delay(25);
                }
                check(after is not null&&after.InstanceId!=before.InstanceId&&after.Pid==before.Pid&&after.CreationTime==before.CreationTime&&
                    after.State==(corrupt?"CONFIGURATION_ERROR":"READY")&&!after.SetupReady,
                    "owned restart drains old graph, preserves process identity and reports actual configuration failure/readiness: "+corrupt);
                if(corrupt)
                {
                    await Until(()=>shell.CriticalForAcceptance is {IsLoaded:true});
                    check(!((Button)shell.Dashboard.FindName("CommandRunButton")).IsEnabled,
                        "configuration failure leaves normal dashboard actions disabled while recovery remains available");
                    Invoke(Find(shell.CriticalForAcceptance!,"Close"));
                    await Until(()=>shell.CriticalForAcceptance is null);
                }
                await Until(()=>!shell.CurrentCommandForAcceptance.Pending);
            }
        }
        finally{shell.Close();await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(5));}
        check(shell.ObservationLifetime.IsCompleted,"native health/setup/recovery close joins all UI-owned reads, dialogs and observers");
    }
}
