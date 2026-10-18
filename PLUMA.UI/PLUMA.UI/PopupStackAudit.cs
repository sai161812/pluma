using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics.Imaging;
using Windows.Storage;

namespace PLUMA.UI
{
    public sealed partial class PopupStackPreviewWindow
    {
        private async Task RunAuditAsync(string directory,CancellationToken lifetime)
        {
            Directory.CreateDirectory(directory);
            using var bounded=CancellationTokenSource.CreateLinkedTokenSource(lifetime);
            bounded.CancelAfter(TimeSpan.FromSeconds(90));
            CancellationToken token=bounded.Token;
            using var report=new StreamWriter(Path.Combine(directory,"popup-stack-audit.txt")) {AutoFlush=true};
            report.WriteLine($"Windows animation preference: {_host.MotionEnabled}. This explicit owned-fixture audit enables motion without changing Windows settings.");
            _host.AnimationPreferenceOverride=true;
            int checks=0;
            var frames=new System.Collections.Generic.List<PopupWindowSnapshot[]>();
            bool visibleLayoutsReady=true;
            _host.FramePresented+=snapshot=>
            {
                frames.Add(snapshot.ToArray());
                visibleLayoutsReady &= _host.Windows.Where(window=>window.Alpha>0.01).All(window=>window.IsLayoutReady);
            };
            void Check(bool result,string label)
            {
                report.WriteLine($"{(result?"PASS":"FAIL")} {label}");
                if(!result) throw new InvalidOperationException(label+". "+_host.LastError);
                checks++;
            }
            async Task Settle()
            {
                DateTimeOffset until=DateTimeOffset.UtcNow.AddSeconds(5);
                do { await Task.Delay(25,token); } while(_host.IsAnimating && DateTimeOffset.UtcNow<until);
                Check(!_host.IsAnimating && _host.LastError==null,"owned animations settle without error");
            }
            void Bounds()
            {
                var cards=_host.Snapshot().Where(p=>!p.Exiting && p.Opacity>0.01).ToArray();
                PopupRect area=PopupStackLayout.ContentArea(_host.Desktop!);
                Check(cards.All(p=>area.Contains(p.Bounds,1)),"actual native window rectangles remain in the safe area");
                foreach(var window in _host.Windows.Where(w=>w.WasShown && w.Alpha>0.01))
                {
                    Check(window.IsLayoutReady,"visible popup has loaded its native client layout");
                    report.WriteLine($"CLIENT content {window.HostedContent?.ActualWidth:0.##}x{window.HostedContent?.ActualHeight:0.##}; root {window.Root.ActualWidth:0.##}x{window.Root.ActualHeight:0.##}; frame {window.ChromePixels}; raster {window.Root.XamlRoot?.RasterizationScale}; monitor scale {_host.Desktop!.Scale}; native DPI {PopupDesktopPlacement.Native.GetDpiForWindow(window.Handle)}; loaded {window.Root.IsLoaded}; bounds {window.ReadBounds()}");
                    Check(window.HostedContent==null || window.HostedContent.ActualWidth<=window.Root.ActualWidth+1,
                        "component width fits the actual native client area");
                }
                Check(cards.Select(p=>p.Bounds.Right).Distinct().Count()<=1,"actual native windows have a common right edge");
                for(int i=1;i<cards.Length;i++) Check(!cards[i-1].Bounds.Overlaps(cards[i].Bounds),"visible native windows do not overlap");
            }
            report.WriteLine($"Started {DateTimeOffset.Now:O}; Windows {Environment.OSVersion}; runtime {Environment.Version}");
            nint foreground=PopupDesktopPlacement.Native.GetForegroundWindow();
            var a=new ToastNotification(); a.Show("First preview notice");
            Check(_host.Present("A",24,a,lifetime:TimeSpan.FromSeconds(30)),"first presentation admitted");
            await Settle(); Bounds();
            Check(visibleLayoutsReady,"native client layout is ready before sampled visible frames");
            Check(PopupDesktopPlacement.Native.GetForegroundWindow()==foreground,"routine presentation does not steal foreground focus");
            report.WriteLine($"DISPLAY {_host.Desktop}");
            foreach(var bar in _host.Desktop!.AutoHideBars) report.WriteLine($"AUTOHIDE {bar.Edge}: full height {bar.ThicknessPixels:0.##} physical pixels; revealed {bar.IsRevealed}");
            var b=new ToastNotification(); b.Show("Second preview notice");
            double oldY=_host.Snapshot().Single(p=>p.Key=="A").Bounds.Y;
            Check(_host.Present("B",24,b,lifetime:TimeSpan.FromSeconds(30)),"second presentation admitted");
            await Task.Delay(50,token);
            Check(_host.Snapshot().Where(p=>p.Opacity>0.01).All(p=>PopupStackLayout.ContentArea(_host.Desktop!).Contains(p.Bounds,1)),"entry/reflow path stays inside usable bounds");
            await Settle(); Bounds();
            var visible=_host.Snapshot();
            Check(visible[0].Bounds.Width==visible[1].Bounds.Width && visible[0].Bounds.Height==visible[1].Bounds.Height,"same-class notices have identical native sizes");
            Check(visible.Select(p=>p.Key).SequenceEqual(new[]{"A","B"}) && visible[0].Bounds.Y<oldY,"newest is below and the earlier card moved up");
            var replacement=new ToastNotification(); replacement.Show("Updated second notice");
            nint originalHandle=_host.HandleFor("B");
            Check(_host.Present("B",24,replacement,lifetime:TimeSpan.FromSeconds(30)),"stable entry updates");
            await Settle();
            Check(_host.Count==2 && _host.Snapshot().Select(p=>p.Key).SequenceEqual(new[]{"A","B"}),"updates do not duplicate or reorder entries");
            Check(_host.HandleFor("B")==originalHandle,"updates reuse the existing native window");
            replacement.Hide();
            Check(replacement.Visibility==Visibility.Visible,"hosted dismissal preserves content for its exit animation");
            await Settle();
            Check(_host.Snapshot().All(p=>p.Key!="B"),"dismissed native window is removed after exit");
            _host.Clear(); await Settle();
            Check(_host.Count==0 && !_host.TimerRunning,"empty stack releases its timer");
            if(_host.MotionEnabled)
            {
                Check(frames.SelectMany(frame=>frame).Any(card=>card.Opacity>0 && card.Opacity<1),"native opacity readback includes intermediate fade frames");
                Check(frames.SelectMany(frame=>frame).Where(card=>card.Key=="A").Select(card=>card.Bounds.Y).Distinct().Count()>2,
                    "native position readback includes intermediate reflow frames");
            }
            Check(frames.All(frame=>frame.Where(card=>card.Opacity>0.01).SelectMany((a,i)=>frame.Where(card=>card.Opacity>0.01).Skip(i+1).Select(b=>!a.Bounds.Overlaps(b.Bounds))).All(ok=>ok)),
                "no visible overlap in sampled animation frames");

            var closeNotice=new PolicyBlockNotice {ToolName="invoke_control",MatchedRule="The window changed.",IsNoticeOpen=true};
            Check(_host.Present("close",19,closeNotice,persistent:true),"native InfoBar close fixture admitted");
            await Settle();
            closeNotice.IsOpen=false;
            Check(!_host.MotionEnabled || closeNotice.IsOpen,"native InfoBar close preserves its content during host exit");
            await Settle();
            Check(_host.Count==0,"native InfoBar close is coordinated by the host");

            var emptyNotice=new ToastNotification(); emptyNotice.Show("Before an empty update");
            Check(_host.Present("empty",24,emptyNotice,persistent:true),"empty update fixture admitted");
            await Settle();
            emptyNotice.Show("_ \u2014");
            Check(emptyNotice.Visibility==Visibility.Visible,"empty hosted notice preserves its previous content through exit");
            await Settle(); Check(_host.Count==0,"empty hosted notice is dismissed by the coordinator");

            frames.Clear();
            Check(_host.Present("moving-A",24,CreateFixture(24),persistent:true) &&
                _host.Present("moving-B",24,CreateFixture(24),persistent:true),"dismissal reflow fixtures admitted");
            await Settle();
            Check(_host.Present("moving-C",24,CreateFixture(24),persistent:true),"arrival starts the dismissal reflow fixture");
            await Task.Delay(40,token);
            _host.Dismiss("moving-A");
            await Settle(); Bounds();
            Check(frames.All(frame=>frame.Where(card=>card.Opacity>0.01).SelectMany((a,i)=>frame.Where(card=>card.Opacity>0.01).Skip(i+1).Select(b=>!a.Bounds.Overlaps(b.Bounds))).All(ok=>ok)),
                "dismissal during upward reflow preserves non-overlap in every sampled native frame");
            _host.Clear(); await Settle();

            foreach(int surface in new[]{4,5,6,7,8,9,11,12,13,14,17,19,20,21,24})
            {
                Check(_host.Present("sample",surface,CreateFixture(surface),persistent:true),$"surface {surface} admitted with existing dark component");
                await Settle(); Bounds();
                Check(_host.Windows.All(w=>w.Root.ActualTheme==ElementTheme.Dark),$"surface {surface} uses Dark");
                PopupClassSize profile=PopupSizing.ForSurface(surface);
                Check(_host.Windows.All(window=>Math.Abs(window.Root.ActualWidth-profile.WidthDips)<=1 && Math.Abs(window.Root.ActualHeight-profile.HeightDips)<=1),
                    $"surface {surface} matches its stable class client dimensions");
                if(surface is 17 or 19 or 24)
                    Check(_host.Windows.All(window=>NoticeBackgroundHeight(window.HostedContent!)>=profile.HeightDips-1),
                        $"surface {surface} native InfoBar background fills its class viewport");
                foreach(var window in _host.Windows) await CaptureCardAsync(window,Path.Combine(directory,$"surface-{surface:00}-dark.png"),token);
                _host.Clear(); await Settle();
            }
            var reading=new ToastNotification(); reading.Show("Read this message before it disappears");
            Check(_host.Present("reading",24,reading,lifetime:TimeSpan.FromMilliseconds(150)),"reading fixture admitted");
            await Settle();
            _host.Hold("reading",true); await Task.Delay(250,token);
            Check(_host.Count==1,"reading hold pauses automatic dismissal");
            _host.Hold("reading",false); await Task.Delay(400,token); await Settle();
            Check(_host.Count==0,"reading release resumes automatic dismissal");

            var longNotice=new ToastNotification(); longNotice.Show(string.Join(" ",Enumerable.Repeat(new string('W',180)+" quarterly_report.pdf \u2014 check this first",15)));
            Check(_host.Present("long",24,longNotice,persistent:true),"long Unicode and word fixture admitted");
            await Settle(); Bounds();
            var message=(PopupMessageText)longNotice.FindName("NoticeText");
            Check(!message.DisplayText.Contains('_') && !message.DisplayText.Contains('\u2014') && message.MessageScroll.ScrollableWidth<=1,"long popup copy is readable and horizontally bounded");
            var longBounds=_host.Snapshot().Single().Bounds;
            Check(Math.Abs(longBounds.Width-visible[1].Bounds.Width)<=1 && Math.Abs(longBounds.Height-visible[1].Bounds.Height)<=1,"long content retains the same notice footprint");
            _host.Clear(); await Settle();
            Check(_host.Present("task",4,new TaskRunningPopup()),"active task fixture admitted before burst");
            await Settle();
            for(int i=0;i<12;i++) { var notice=new ToastNotification(); notice.Show($"Burst notice {i}"); Check(_host.Present($"burst-{i}",24,notice,lifetime:TimeSpan.FromSeconds(30)),"burst entry admission"); }
            await Settle(); Bounds();
            Check(_host.Snapshot().Last().Key=="burst-11","latest burst notice remains at bottom");
            nint runningHandle=_host.HandleFor("task");
            Check(_host.Present("task",20,new CancellationAnimation {IsActive=true}),"STOP feedback admitted during crowded stack");
            await Settle(); Bounds();
            Check(_host.Snapshot().Any(p=>p.Key=="task"),"STOP presentation is not left in routine overflow");
            Check(_host.HandleFor("task")==runningHandle,"STOP replaces existing progress without creating another window");
            _host.Clear(); await Settle();

            // Change only this fixture's reported work area; never alter Windows display/taskbar settings.
            Check(visibleLayoutsReady,"every sampled visible native frame has a ready client layout");
            _host.Dispose();
            var placement=new AuditPlacement(new PopupDesktopPlacement(WinRT.Interop.WindowNative.GetWindowHandle(this),DispatcherQueue));
            _host=new PopupStackHost(this,placement) {AnimationPreferenceOverride=true};
            placement.ForceTaskbar(false);
            Check(_host.Present("taskbar",24,CreateFixture(24),persistent:true),"taskbar glide fixture admitted");
            await Settle();
            PopupRect lowered=_host.Snapshot().Single().Bounds;
            Check(Math.Abs(lowered.Bottom-PopupStackLayout.ContentArea(_host.Desktop!).Bottom)<=1,"hidden taskbar uses the lower screen-edge anchor");
            placement.ForceTaskbar(true);
            await Task.Delay(50,token);
            PopupRect rising=_host.Snapshot().Single().Bounds;
            await Settle(); Bounds();
            PopupRect raised=_host.Snapshot().Single().Bounds;
            Check(raised.Y<lowered.Y && (!_host.MotionEnabled || rising.Y<lowered.Y && rising.Y>raised.Y),"taskbar reveal has intermediate native glide positions rather than a jump");
            Check(raised.Width==lowered.Width && raised.Height==lowered.Height,"taskbar movement preserves the notification size");
            placement.ForceTaskbar(false);
            await Task.Delay(50,token);
            PopupRect falling=_host.Snapshot().Single().Bounds;
            await Settle(); Bounds();
            Check(_host.Snapshot().Single().Bounds==lowered && (!_host.MotionEnabled || falling.Y>raised.Y && falling.Y<lowered.Y),"taskbar hide glides back to the same lower anchor");
            _host.Dismiss("taskbar");
            placement.ForceTaskbar(true);
            await Settle();
            Check(_host.Count==0,"taskbar reveal during dismissal leaves no orphan card");
            placement.ForceTaskbar(null);
            Check(_host.Present("geometry-task",4,new TaskRunningPopup()),"native geometry fixture admitted");
            await Settle();
            Check(_host.Present("geometry-notice",24,CreateFixture(24),persistent:true),"native geometry second entry admitted");
            await Settle();
            placement.SetArea(0.8,0.8,notify:false);
            Check(_host.Present("geometry-third",24,CreateFixture(24),persistent:true),"arrival detects a changed work area before animation");
            Bounds(); await Settle();
            _host.Dismiss("geometry-notice");
            placement.SetArea(0.7,0.65);
            await Task.Delay(30,token); Bounds(); await Settle();
            Check(_host.Snapshot().All(card=>card.Key!="geometry-notice"),"work-area change safely finishes an in-flight exit");
            placement.SetArea(0.05,0.15);
            await Task.Delay(60,token);
            Check(!_host.Windows.Any() && _host.Count==2 && !_host.TimerRunning,"unshowable protected entries stay queued without offscreen windows or a timer");
            placement.SetArea(1,1);
            await Settle(); Bounds();
            Check(_host.Snapshot().Count==2,"queued protected entries return when the work area fits");
            nint[] beforeFault=_host.Windows.Select(window=>window.Handle).ToArray();
            placement.Fail=true;
            Check(!_host.Present("failure",24,CreateFixture(24),persistent:true),"native geometry failure is reported without false admission");
            Check(_host.LastError!=null && _host.Count==0 && !_host.TimerRunning && beforeFault.All(handle=>!PopupDesktopPlacement.Native.IsWindow(handle)),
                "unverifiable native geometry releases owned cards and timers");
            _host.Dispose();
            Check(placement.Disposed,"native geometry fixture releases its event adapter");
            _host=new PopupStackHost(this) {AnimationPreferenceOverride=true};

            _host.SuppressAnimations=true;
            report.WriteLine("Motion-disabled fixture: 50 native creation/layout/disposal lifecycles.");
            for(int cycle=0;cycle<50;cycle++)
            {
                var notice=new ToastNotification(); notice.Show($"Lifecycle {cycle}");
                Check(_host.Present("cycle",24,notice,persistent:true),"repeat lifecycle admission");
                await Settle();
                Bounds();
                _host.Clear(); await Task.Delay(15,token);
                Check(_host.Count==0 && !_host.TimerRunning,"repeat lifecycle has no orphan window or timer");
            }
            Check(_host.Windows.Count()==0,"all native popup windows released");
            _host.SuppressAnimations=false;
            Check(_host.Present("closing",4,new TaskRunningPopup()),"shutdown fixture admitted");
            await Task.Delay(20,token);
            nint[] ownedHandles=_host.Windows.Select(w=>w.Handle).ToArray();
            _host.Dispose();
            Check(_host.IsDisposed && !_host.TimerRunning && ownedHandles.All(handle=>!PopupDesktopPlacement.Native.IsWindow(handle)),
                "host disposal during motion closes native windows, subscriptions and owned timers");
            _host=new PopupStackHost(this);
            report.WriteLine($"{checks} native popup checks passed.");
            report.WriteLine("Physical taskbar hover/reveal, other real monitor DPI settings, and subjective motion still require interactive review; pure simulations are separate evidence.");
            if(!_closed) _status.Text=$"{checks} native popup checks passed. Audit output is saved.";
        }

        private static double NoticeBackgroundHeight(DependencyObject root)
        {
            if(root is InfoBar bar && VisualTreeHelper.GetChildrenCount(bar)>0 && VisualTreeHelper.GetChild(bar,0) is FrameworkElement background)
                return background.ActualHeight;
            for(int index=0;index<VisualTreeHelper.GetChildrenCount(root);index++)
            {
                double height=NoticeBackgroundHeight(VisualTreeHelper.GetChild(root,index));
                if(height>0) return height;
            }
            return 0;
        }

        private sealed class AuditPlacement : IPopupDesktopPlacement
        {
            private readonly IPopupDesktopPlacement _native;
            private double _width=1,_height=1;
            private bool? _taskbar;
            public bool Disposed {get;private set;}
            public bool Fail {get;set;}
            public event EventHandler? Changed;
            public AuditPlacement(IPopupDesktopPlacement native) { _native=native; _native.Changed+=Forward; }
            private void Forward(object? sender,EventArgs args)=>Changed?.Invoke(this,args);
            public PopupDesktop Read(nint referenceWindow)
            {
                if(Fail) throw new System.Runtime.InteropServices.COMException("Preview placement is unavailable.");
                var desktop=_native.Read(referenceWindow);
                var work=desktop.WorkArea;
                if(_taskbar.HasValue)
                    desktop=desktop with {WorkArea=desktop.Monitor, AutoHideBars=new[]{new PopupAppBar(PopupScreenEdge.Bottom,60*desktop.Scale,_taskbar.Value)}};
                work=desktop.WorkArea;
                return desktop with {WorkArea=new(work.X,work.Y,Math.Floor(work.Width*_width),Math.Floor(work.Height*_height))};
            }
            public void ForceTaskbar(bool? revealed) { _taskbar=revealed;Changed?.Invoke(this,EventArgs.Empty); }
            public void SetArea(double width,double height,bool notify=true)
            { _width=width;_height=height;if(notify)Changed?.Invoke(this,EventArgs.Empty); }
            public void Watch(bool enabled)=>_native.Watch(enabled);
            public void Dispose() { _native.Changed-=Forward;_native.Dispose();Changed=null;Disposed=true; }
        }

        private static async Task CaptureCardAsync(PopupCardWindow window,string path,CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            var bitmap=new RenderTargetBitmap(); await bitmap.RenderAsync(window.Root);
            if(bitmap.PixelWidth==0 || bitmap.PixelHeight==0) throw new InvalidOperationException("Empty popup capture.");
            var buffer=await bitmap.GetPixelsAsync();
            using(File.Create(path)) { }
            StorageFile file=await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path));
            using var stream=await file.OpenAsync(FileAccessMode.ReadWrite);
            var encoder=await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId,stream);
            using var reader=Windows.Storage.Streams.DataReader.FromBuffer(buffer);
            var pixels=new byte[buffer.Length]; reader.ReadBytes(pixels);
            // Native InfoBar backgrounds may be transparent. The host must supply an opaque dark base.
            int darkOpaque=0;
            for(int pixel=0;pixel<pixels.Length;pixel+=4)
                if(pixels[pixel+3]>=240 && pixels[pixel]<160 && pixels[pixel+1]<160 && pixels[pixel+2]<160) darkOpaque++;
            if(darkOpaque<pixels.Length/8) throw new InvalidOperationException("The popup background is not predominantly opaque and dark.");
            encoder.SetPixelData(BitmapPixelFormat.Bgra8,BitmapAlphaMode.Premultiplied,(uint)bitmap.PixelWidth,(uint)bitmap.PixelHeight,96,96,pixels);
            await encoder.FlushAsync();
        }
    }
}
