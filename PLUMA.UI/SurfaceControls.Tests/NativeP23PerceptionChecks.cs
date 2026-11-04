using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Text;
using System.Security.Cryptography;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI.Tests;

internal static class NativeP23PerceptionChecks
{
    private static async Task Until(Func<bool> ready, double seconds=4)
    {
        var clock=Stopwatch.StartNew();
        while(!ready() && clock.Elapsed.TotalSeconds<seconds)await Task.Delay(10);
        if(!ready())throw new TimeoutException("Owned P23 native condition was not observed.");
    }
    internal static async Task RunAsync(Action<bool,string> check)
    {
        if(Environment.GetEnvironmentVariable("GITHUB_ACTIONS")!="true")
            throw new InvalidOperationException("P23 foreground/render acceptance requires the disposable Windows test host.");
        await using var fixture=await NativeConfirmationChecks.Fixture.StartAsync("perception");
        await using var client=new CoreIpcClient(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        using var identity=JsonDocument.Parse(File.ReadAllText(Path.Combine(fixture.OwnedRoot,"perception-target.json")));
        nint target=(nint)identity.RootElement.GetProperty("hwnd").GetInt64();
        uint pid=(uint)identity.RootElement.GetProperty("pid").GetInt32();
        CheckTarget(target,pid);
        var shell=new MainWindow(new(fixture.Pipe,fixture.Key,TimeSpan.FromSeconds(3)));
        shell.Activate();
        var host=shell.FeedbackForAcceptance;
        int presented=0;
        int sampleX=0,sampleY=0,outsideX=0;
        uint baseline=0,outsideBaseline=0;
        string? currentTask=null;
        host.Presented+=(_,_)=>presented++;
        string Id()=>Guid.NewGuid().ToString("D");
        async Task<string> Start(string text)
        {
            CheckTarget(target,pid);
            if(!SetForegroundWindow(target))throw new InvalidOperationException("Owned target foreground request was refused.");
            await Until(()=>GetForegroundWindow()==target);
            await Task.Delay(30);
            if(!PopupDesktopPlacement.Native.GetWindowRect(target,out var actualBounds))throw new InvalidOperationException("Owned target bounds unavailable.");
            sampleX=actualBounds.Right-30;sampleY=actualBounds.Bottom-30;outsideX=actualBounds.Right+8;
            baseline=Pixel(sampleX,sampleY);outsideBaseline=Pixel(outsideX,sampleY);
            var reply=await client.SubmitTextAsync(Id(),text,default);
            if(!reply.IsSuccess||reply.Response?.TaskId is null)throw new InvalidOperationException("Owned P23 task was not admitted.");
            currentTask=reply.Response.TaskId;return currentTask;
        }
        async Task Stop(string task)
        {
            var reply=await client.StopAsync(Id(),task,default);
            if(!reply.IsSuccess)throw new InvalidOperationException("Owned STOP was not acknowledged.");
            await Until(()=>host.Handle==0);
        }
        try
        {
            await Until(()=>shell.Dashboard is {IsLoaded:true} page&&((Button)page.FindName("CommandRunButton")).IsEnabled);
            var self=NativePerceptionTarget.Read(WinRT.Interop.WindowNative.GetWindowHandle(shell));
            check(self is not null && self.TitleHash=="sha256:"+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(shell.Title))).ToLowerInvariant(),
                "native own-window title cache agrees with the actual caption without synchronous UI messages");
            string task=await Start("fixture:capture");
            await Until(()=>host.Handle!=0 && LayerVisible(host.Handle),2);
            nint layer=host.Handle;
            check(GetForegroundWindow()==target,"capture feedback does not activate or steal focus from the actual owned target");
            nint style=PopupDesktopPlacement.Native.GetWindowLongPtr(layer,-20);
            check((style & (0x20|0x80|0x08000000))==(0x20|0x80|0x08000000),"native feedback HWND is input-transparent, a tool window and nonactivating");
            GetWindowThreadProcessId(WindowFromPoint(new NativePoint{X=sampleX,Y=sampleY}),out uint hitPid);
            check(hitPid==pid,"native hit testing reaches the owned target through the displayed feedback layer");
            var observation=host.ObservationForAcceptance!;
            var pixels=NativePerceptionTarget.Map(observation,1)!;
            check(PopupDesktopPlacement.Native.GetWindowRect(layer,out var bounds)&&bounds.Left==pixels.DesktopX&&bounds.Top==pixels.DesktopY&&
                bounds.Right-bounds.Left==pixels.Width&&bounds.Bottom-bounds.Top==pixels.Height,
                "real capture flash native bounds equal the actual target ROI after Windows legacy DPI conversion");
            check(observation.Hwnd==(long)target&&observation.Pid==pid&&observation.Match is null,
                "actual capture receipt identifies the fixture target and invents no OCR match");
            await Task.Delay(45);
            uint lit=Pixel(sampleX,sampleY);
            int red=(int)(lit&255)-(int)(baseline&255),green=(int)((lit>>8)&255)-(int)((baseline>>8)&255);
            check(lit!=baseline && red>0 && red<=128 && green>=0 && green<=128,
                "actual composed capture flash brightens an owned target pixel rather than showing an opaque background");
            check(Pixel(outsideX,sampleY)==outsideBaseline,"capture feedback changes no pixel outside the target ROI or its owned input-transparent layer");
            await Until(()=>host.Handle==0,1);
            int count=presented;await Task.Delay(350);
            check(presented==count&&!host.TimerRunning,"capture flash completes once; repeated observations do not replay or keep an idle timer");
            await Stop(task);

            task=await Start("fixture:match");
            await Until(()=>host.MatchVisible,15);
            layer=host.Handle;observation=host.ObservationForAcceptance!;
            check(observation.MatchState=="UNIQUE"&&observation.Match is {Confidence:>=.6}&&observation.Region.Contains(observation.Match.Bounds),
                "native PaddleOCR/ONNX unique Submit evidence supplies actual match bounds and confidence through authenticated IPC");
            var detail=await client.GetTaskDetailAsync(Id(),task,0,default);
            check(detail.IsSuccess&&detail.Response!.Actions.Single().Verified&&detail.Response.Actions.Single().Tool=="find_visible_text",
                "independent saved action readback agrees with the native screen tool result");
            await fixture.ControlHistoryAsync("perception_move");
            await Until(()=>host.Handle==0,.6);
            check(!IsWindow(layer)&&IsWindow(target),"moving the owned target closes only the feedback HWND and preserves the target window");
            await Stop(task);

            task=await Start("fixture:match");await Until(()=>host.MatchVisible,15);
            await shell.StopForAcceptance();await Until(()=>host.Handle==0,.6);
            check(IsWindow(target)&&!host.TimerRunning,"priority UI STOP revokes feedback immediately and never closes the pre-existing target fixture");
            var stopDeadline=Stopwatch.StartNew();
            while(stopDeadline.Elapsed.TotalSeconds<3)
            {
                var state=await client.GetTerminalReadbackAsync(Id(),task,default);
                if(state.IsSuccess&&state.Response!.Terminal)break;
                await Task.Delay(20);
            }
            await fixture.ControlHistoryAsync("perception_assert_cleanup");

            task=await Start("fixture:match");await Until(()=>host.MatchVisible,15);
            await fixture.ControlHistoryAsync("perception_hide");await Until(()=>host.Handle==0,.6);
            check(!host.MatchVisible,"hidden targets cannot retain a stale OCR indicator");
            await Stop(task);await fixture.ControlHistoryAsync("perception_show");

            task=await Start("fixture:match");await Until(()=>host.MatchVisible,15);
            await Until(()=>host.Handle==0,3.2);
            check(!host.TimerRunning,"native host honors original observation TTL without renewing it on repeated IPC reads");
            await Stop(task);

            task=await Start("fixture:match");await Until(()=>host.MatchVisible,15);
            await fixture.ControlHistoryAsync("perception_disconnect");await Until(()=>host.Handle==0,4);
            check(!host.MatchVisible,"failed authenticated observation readback clears the native target layer");
            await fixture.ControlHistoryAsync("perception_reconnect");await Stop(task);
            task=await Start("fixture:match");await Until(()=>host.MatchVisible,15);
            layer=host.Handle;
            await fixture.ControlHistoryAsync("perception_close");await Until(()=>host.Handle==0,.6);
            check(!IsWindow(layer)&&!IsWindow(target),"a closed owned target cannot retain a feedback layer after reconnect");
            await Stop(task);
        }
        catch(Exception error)
        {
            Console.Error.WriteLine("P23 native state: "+host.LastFailure+"; HWND "+host.Handle+"; frames "+presented+"; "+error);
            if(currentTask is not null)
            {
                var evidence=await client.GetTaskDetailAsync(Id(),currentTask,0,default);
                Console.Error.WriteLine("Owned P23 saved evidence: "+JsonSerializer.Serialize(evidence));
            }
            throw;
        }
        finally{shell.Close();await shell.ObservationLifetime.WaitAsync(TimeSpan.FromSeconds(6));}
        check(host.IsDisposed&&host.Handle==0&&!host.TimerRunning,"shell shutdown joins observation work and destroys its own feedback windows/timer");
    }
    private static void CheckTarget(nint hwnd,uint expected)
    {GetWindowThreadProcessId(hwnd,out uint pid);if(pid!=expected||!IsWindow(hwnd))throw new InvalidOperationException("Owned target identity changed.");}
    private static bool LayerVisible(nint hwnd)=>PopupDesktopPlacement.Native.GetLayeredWindowAttributes(hwnd,out _,out byte alpha,out _)&&alpha==255;
    private static uint Pixel(int x,int y)
    {
        nint dc=GetDC(0);if(dc==0)throw new InvalidOperationException("Owned display pixel unavailable.");
        try{uint color=GetPixel(dc,x,y);if(color==0xffffffff)throw new InvalidOperationException("Owned display pixel read failed.");return color;}
        finally{ReleaseDC(0,dc);}
    }
    [DllImport("user32.dll")] private static extern nint GetDC(nint hwnd);
    [DllImport("user32.dll")] private static extern int ReleaseDC(nint hwnd,nint dc);
    [DllImport("gdi32.dll")] private static extern uint GetPixel(nint dc,int x,int y);
    [DllImport("user32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool SetForegroundWindow(nint hwnd);
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd,out uint pid);
    [DllImport("user32.dll")] [return:MarshalAs(UnmanagedType.Bool)] private static extern bool IsWindow(nint hwnd);
    [StructLayout(LayoutKind.Sequential)] private struct NativePoint{public int X,Y;}
    [DllImport("user32.dll")] private static extern nint WindowFromPoint(NativePoint point);
}
