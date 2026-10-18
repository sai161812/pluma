using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;
using Windows.UI.ViewManagement;
using WinRT.Interop;

namespace PLUMA.UI
{
    public sealed record PopupWindowSnapshot(string Key, PopupRect Bounds, double Opacity, bool Exiting, bool Reading);

    /// <summary>One UI-thread coordinator for the desktop stack. No IPC, microphone, or execution ownership.</summary>
    public sealed class PopupStackHost : IDisposable
    {
        private sealed class Entry
        {
            internal required string Key;
            internal required FrameworkElement Content;
            internal required int Surface;
            internal PopupCardWindow? Window;
            internal PopupRect Target, From;
            internal double FromAlpha, ToAlpha, Start, Duration;
            internal bool Moving, Closing, Waiting;
            internal EventHandler? Dismiss;
            internal readonly List<(InfoBar Bar, Windows.Foundation.TypedEventHandler<InfoBar, InfoBarClosingEventArgs> Handler)> Closings = new();
        }

        private readonly Window _owner;
        private readonly nint _ownerHandle;
        private readonly DispatcherQueue _dispatcher;
        private readonly DispatcherQueueTimer _timer;
        private readonly IPopupDesktopPlacement _placement;
        private readonly PopupStackState _state = new();
        private readonly Dictionary<string, Entry> _entries = new(StringComparer.Ordinal);
        private readonly UISettings _settings = new();
        private double _lastTick = Now;
        private bool _disposed, _refreshQueued, _reconciling;
        private nint _reference;
        private PopupDesktop? _desktop;
        private double _chromeWidth, _chromeHeight;
        public string? LastError { get; private set; }
        public bool SuppressAnimations { get; set; }
        public int Count => _entries.Count;
        public bool IsDisposed => _disposed;
        public bool IsAnimating => _refreshQueued || _entries.Values.Any(e => e.Moving || e.Waiting);
        public PopupDesktop? Desktop => _desktop;
        internal bool TimerRunning => _timer.IsRunning;
        internal bool MotionEnabled => Animate;
        internal event Action<IReadOnlyList<PopupWindowSnapshot>>? FramePresented;
        internal nint HandleFor(string key) => _entries.TryGetValue(key,out var entry) ? entry.Window?.Handle ?? 0 : 0;
        internal IEnumerable<PopupCardWindow> Windows => _entries.Values.Select(e=>e.Window).OfType<PopupCardWindow>();
        private static double Now => Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency;
        private bool Animate => !SuppressAnimations && _settings.AnimationsEnabled;

        public PopupStackHost(Window owner, IPopupDesktopPlacement? placement = null)
        {
            _owner = owner; _ownerHandle = WindowNative.GetWindowHandle(owner);
            _dispatcher = owner.DispatcherQueue;
            _placement = placement ?? new PopupDesktopPlacement(_ownerHandle, _dispatcher);
            _placement.Changed += OnDesktopChanged;
            _timer = _dispatcher.CreateTimer();
            _timer.Tick += OnTick;
            owner.Closed += OnOwnerClosed;
        }

        public bool Present(string key, int surface, FrameworkElement content, bool? persistent = null, TimeSpan? lifetime = null, nint referenceWindow = default)
        {
            CheckThread(); ObjectDisposedException.ThrowIf(_disposed, this);
            if (!(surface is >=4 and <=9 or >=11 and <=14 or 17 or >=19 and <=21 or 24))
                throw new ArgumentOutOfRangeException(nameof(surface));
            if (surface is >=11 and <=14)
            {
                if (content is not VoiceOverlay) throw new ArgumentException("Voice surfaces must share a VoiceOverlay.");
                key = "voice";
                if (((VoiceOverlay)content).VoiceState == VoiceOverlayState.Hidden) { Dismiss(key); return true; }
            }
            if (string.IsNullOrWhiteSpace(key) || content.Parent != null) throw new ArgumentException("A detached popup and stable key are required.");
            if (lifetime is { } supplied && (supplied <= TimeSpan.Zero || supplied > TimeSpan.FromMinutes(1))) throw new ArgumentOutOfRangeException(nameof(lifetime));
            if (!_entries.ContainsKey(key) && _entries.Count >= PopupStackState.Capacity) return false;
            AdvanceClock();
            bool pinned = persistent ?? surface is 4 or 5 or 7 or 9 or 11 or 12 or 14 or 20;
            if (_entries.Count == 0) _reference = referenceWindow == 0 ? _ownerHandle : referenceWindow;
            try
            {
                _placement.Watch(true);
                PopupDesktop desktop = _placement.Read(_reference);
                Entry entry;
                if (_entries.TryGetValue(key, out Entry? existing))
                {
                    entry = existing;
                    Detach(entry);
                    entry.Content = content; entry.Surface = surface;
                    entry.Closing = false;
                    entry.Window?.SetContent(content);
                    entry.Target = default;
                }
                else
                {
                    entry = new Entry { Key = key, Content = content, Surface = surface };
                    _entries[key] = entry;
                }
                Attach(entry);
                var size = Measure(entry, desktop);
                _state.Upsert(key, size.Width, size.Height, pinned, pinned ? null : lifetime ?? TimeSpan.FromSeconds(surface==6?2:4), surface==20?1:0);
                LastError = null;
                Reconcile(force: false);
                return true;
            }
            catch (Exception error) when (error is System.ComponentModel.Win32Exception or System.Runtime.InteropServices.COMException or ArgumentException or InvalidOperationException)
            {
                LastError = PopupText.Message(error.Message);
                if (error is System.ComponentModel.Win32Exception or System.Runtime.InteropServices.COMException)
                    foreach (var failed in _entries.Values.ToArray()) RemoveEntry(failed);
                else if (_entries.TryGetValue(key,out Entry? failed)) RemoveEntry(failed);
                StopIfEmpty();
                return false;
            }
        }

        public bool Update(string key, Action<FrameworkElement> update)
        {
            CheckThread();
            if (_disposed || !_entries.TryGetValue(key,out Entry? entry) || entry.Closing) return false;
            update(entry.Content);
            QueueRefresh();
            return true;
        }

        public void Dismiss(string key)
        {
            CheckThread();
            if (_disposed || !_entries.TryGetValue(key,out Entry? entry) || entry.Closing) return;
            _state.Remove(key);
            if (entry.Window == null || !entry.Window.WasShown || !Animate) { RemoveEntry(entry); QueueRefresh(); return; }
            // Keep the current spacing while an entry fades; survivors reflow after its window is removed.
            double pausedAt=Now;
            foreach(Entry moving in _entries.Values.Where(other=>other.Moving && other.Window?.WasShown==true).ToArray())
                StartMotion(moving,moving.Window!.Bounds,moving.ToAlpha,Math.Max(1,moving.Start+moving.Duration-pausedAt),pausedAt);
            entry.Closing = true; entry.Waiting = false;
            StartMotion(entry, entry.Window.Bounds, 0,160);
            ArmTimer();
        }

        public void Clear()
        {
            CheckThread();
            foreach (string key in _entries.Keys.ToArray()) Dismiss(key);
        }

        public IReadOnlyList<PopupWindowSnapshot> Snapshot() => _entries.Values.Where(e=>e.Window?.WasShown==true && !e.Window.IsClosed)
            .OrderBy(e=>e.Window!.Bounds.Y).Select(e=>new PopupWindowSnapshot(e.Key,e.Window!.ReadBounds(),e.Window.ReadAlpha()/255.0,e.Closing,_state.Find(e.Key)?.Held==true)).ToArray();

        internal void Hold(string key,bool held) { AdvanceClock(); _state.Hold(key,held); ArmTimer(); }
        private void CheckThread() { if (!_dispatcher.HasThreadAccess) throw new InvalidOperationException("Popup presentation must run on the UI thread."); }
        private void OnOwnerClosed(object sender,WindowEventArgs args) => Dispose();
        private void OnDesktopChanged(object? sender,EventArgs args) => QueueRefresh();

        private Size Measure(Entry entry,PopupDesktop desktop)
        {
            PopupRect area = PopupStackLayout.ContentArea(desktop);
            var chrome = entry.Window?.ChromePixels;
            double chromeWidth = chrome?.Width / desktop.Scale ?? _chromeWidth;
            double chromeHeight = chrome?.Height / desktop.Scale ?? _chromeHeight;
            PopupClassSize profile = PopupSizing.ForSurface(entry.Surface);
            double width = Math.Max(1,Math.Min(profile.WidthDips,area.Width/desktop.Scale-chromeWidth));
            entry.Content.MinWidth = 0;
            entry.Content.MinHeight = profile.HeightDips;
            entry.Content.Width = width;
            entry.Content.HorizontalAlignment = HorizontalAlignment.Stretch;
            entry.Content.VerticalAlignment = VerticalAlignment.Stretch;
            entry.Content.Measure(new Size(width,double.PositiveInfinity));
            double height = Math.Max(1,Math.Min(profile.HeightDips+chromeHeight,Math.Max(1,area.Height/desktop.Scale)));
            return new Size(width+chromeWidth,height);
        }

        private void Attach(Entry entry)
        {
            if (entry.Content is IHostedPopup hosted)
            {
                hosted.IsHosted = true;
                entry.Dismiss = (_,_)=>Dismiss(entry.Key);
                hosted.DismissRequested += entry.Dismiss;
            }
            foreach (InfoBar bar in Descendants(entry.Content).OfType<InfoBar>())
            {
                Windows.Foundation.TypedEventHandler<InfoBar,InfoBarClosingEventArgs> handler = (_,args)=>
                { if (!entry.Closing && !_disposed) { args.Cancel=true; Dismiss(entry.Key); } };
                bar.Closing += handler;
                entry.Closings.Add((bar,handler));
            }
        }

        private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
        {
            yield return root;
            for(int i=0;i<Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChildrenCount(root);i++)
                foreach(var child in Descendants(Microsoft.UI.Xaml.Media.VisualTreeHelper.GetChild(root,i))) yield return child;
        }

        private void QueueRefresh()
        {
            if (_disposed || _refreshQueued) return;
            _refreshQueued=true;
            if (!_dispatcher.TryEnqueue(()=>{_refreshQueued=false; if(!_disposed) SafeReconcile();})) _refreshQueued=false;
        }

        private void SafeReconcile()
        {
            try { Reconcile(false); }
            catch(Exception error) when(error is System.ComponentModel.Win32Exception or System.Runtime.InteropServices.COMException or ArgumentException or InvalidOperationException)
            {
                LastError=PopupText.Message(error.Message);
                foreach(var entry in _entries.Values.ToArray()) RemoveEntry(entry);
                StopIfEmpty();
            }
        }

        private void Reconcile(bool force)
        {
            if(_disposed || _reconciling) return;
            _reconciling=true;
            try
            {
                if(_entries.Count==0) { StopIfEmpty(); return; }
                PopupDesktop next=_placement.Read(_reference);
                bool geometryChanged=_desktop==null || PopupStackLayout.ContentArea(next)!=PopupStackLayout.ContentArea(_desktop) || next.Scale!=_desktop.Scale;
                bool taskbarGlide=geometryChanged && _desktop!=null && PopupStackLayout.CanGlideForTaskbar(_desktop,next);
                PopupDesktop? previous=_desktop;
                _desktop=next;
                bool resized=false;
                foreach(Entry entry in _entries.Values.Where(e=>!e.Closing))
                {
                    var item=_state.Find(entry.Key);
                    if(item==null) continue;
                    Size size=Measure(entry,next);
                    if(Math.Abs(size.Width-item.WidthDips)>0.5 || Math.Abs(size.Height-item.HeightDips)>0.5)
                    { item.WidthDips=size.Width; item.HeightDips=size.Height; resized=true; }
                }
                bool snap=force || (geometryChanged && !taskbarGlide) || resized || !Animate;
                if(taskbarGlide && !snap && _entries.Values.Any(e=>e.Closing) && GlideClosingStack(previous!,next))
                { ArmTimer(); return; }
                if(geometryChanged || force)
                    foreach(Entry closing in _entries.Values.Where(e=>e.Closing).ToArray()) RemoveEntry(closing);
                if(_entries.Values.Any(e=>e.Closing)) { ArmTimer(); return; }
                PopupStackPlan plan=_state.Plan(next);
                foreach(string key in plan.Retire)
                    if((snap || geometryChanged) && _entries.TryGetValue(key,out var retired)) RemoveEntry(retired); else Dismiss(key);
                if(_entries.Values.Any(e=>e.Closing)) { ArmTimer(); return; }
                var selected=plan.Placements.Select(p=>p.Key).ToHashSet(StringComparer.Ordinal);
                foreach(Entry entry in _entries.Values.Where(e=>!selected.Contains(e.Key)).ToArray())
                {
                    // Protected entries remain queued; no content extends outside the safe desktop.
                    if(entry.Window!=null) { CloseWindow(entry); _state.SetDisplayed(entry.Key,false); }
                }
                double motionStart=Now;
                foreach(PopupPlacement place in plan.Placements)
                {
                    Entry entry=_entries[place.Key];
                    if(entry.Window==null)
                    {
                        entry.Window=new PopupCardWindow(QueueRefresh, held=>Hold(entry.Key,held));
                        entry.Window.SetContent(entry.Content);
                        PopupCardWindow owned = entry.Window;
                        entry.Window.Closed+=(_,_)=>
                        {
                            if(!_disposed && ReferenceEquals(entry.Window,owned) && _entries.TryGetValue(entry.Key,out var current) && ReferenceEquals(current,entry))
                            { RemoveEntry(entry); QueueRefresh(); }
                        };
                        var chrome = entry.Window.ChromePixels;
                        double frameWidth = chrome.Width / next.Scale, frameHeight = chrome.Height / next.Scale;
                        if(Math.Abs(frameWidth-_chromeWidth)>0.1 || Math.Abs(frameHeight-_chromeHeight)>0.1)
                        {
                            _chromeWidth=frameWidth; _chromeHeight=frameHeight;
                            Size measured=Measure(entry,next);
                            PopupStackItem? item=_state.Find(entry.Key);
                            if(item!=null) { item.WidthDips=measured.Width; item.HeightDips=measured.Height; }
                            entry.Waiting=true;
                            QueueRefresh();
                            return; // Finish frame-aware layout before showing the new native window.
                        }
                        entry.Window.Place(place.Bounds);
                        entry.Target=place.Bounds; entry.Waiting=true;
                    }
                    else if(entry.Target!=place.Bounds)
                    {
                        if(snap || !entry.Window.WasShown)
                        {
                            entry.Window.Place(place.Bounds); entry.Target=place.Bounds; entry.Moving=false;
                            if(entry.Window.WasShown) { entry.Window.SetAlpha(1); _state.SetDisplayed(entry.Key,true); }
                        }
                        else StartMotion(entry,place.Bounds,1,200,motionStart);
                    }
                }
                RevealWaiting(snap);
                ArmTimer();
            }
            finally { _reconciling=false; }
        }

        private bool GlideClosingStack(PopupDesktop previous,PopupDesktop next)
        {
            PopupRect before=PopupStackLayout.ContentArea(previous),after=PopupStackLayout.ContentArea(next);
            double dx=after.Right-before.Right,dy=after.Bottom-before.Bottom;
            PopupRect Shift(PopupRect rect)=>rect with {X=rect.X+dx,Y=rect.Y+dy};
            var windows=_entries.Values.Where(entry=>entry.Window!=null).ToArray();
            if(windows.Any(entry=>!after.Contains(Shift(entry.Target)))) return false;
            var targets=windows.Select(entry=>Shift(entry.Target)).OrderBy(rect=>rect.Y).ToArray();
            if(targets.Zip(targets.Skip(1),(upper,lower)=>upper.Overlaps(lower)).Any(overlap=>overlap)) return false;
            double motionStart=Now;
            foreach(var entry in windows)
            {
                PopupRect target=Shift(entry.Target);
                // Move every card on the same clock; differing exit/reflow durations can narrow the gap.
                if(entry.Window!.WasShown) StartMotion(entry,target,entry.Closing?0:1,160,motionStart);
                else { entry.Target=target;entry.Window.Place(target); }
            }
            return true;
        }

        private void RevealWaiting(bool snap)
        {
            if(_entries.Values.Any(e=>e.Moving)) return;
            foreach(Entry entry in _entries.Values.Where(e=>e.Waiting).ToArray())
            {
                if(entry.Window==null) continue;
                // A non-activating show starts WinUI layout while the owned window is transparent.
                // Loaded/SizeChanged queue a frame-aware remeasure before the first visible frame.
                entry.Window.Reveal();
                if(!entry.Window.IsLayoutReady || _refreshQueued) continue;
                entry.Waiting=false;
                if(snap || !Animate)
                { entry.Window.Place(entry.Target); entry.Window.SetAlpha(1); entry.Window.Reveal(); _state.SetDisplayed(entry.Key,true); }
                else
                {
                    PopupRect destination=entry.Target;
                    entry.Window.Place(destination);
                    entry.Window.SetAlpha(0); entry.Window.Reveal();
                    StartMotion(entry,destination,1,200);
                }
            }
        }

        private void StartMotion(Entry entry,PopupRect target,double alpha,double milliseconds,double? startedAt=null)
        {
            if(entry.Window==null) return;
            entry.From=entry.Window.Bounds; entry.FromAlpha=entry.Window.Alpha; entry.Target=target; entry.ToAlpha=alpha;
            entry.Start=startedAt??Now; entry.Duration=milliseconds; entry.Moving=true;
        }

        private void AdvanceClock()
        {
            double now=Now,elapsed=Math.Max(0,now-_lastTick); _lastTick=now;
            foreach(string key in _state.Advance(TimeSpan.FromMilliseconds(elapsed))) Dismiss(key);
        }

        private void OnTick(DispatcherQueueTimer sender,object args)
        {
            if(_disposed) return;
            try
            {
                AdvanceClock();
                double frameTime=Now;
                foreach(Entry entry in _entries.Values.Where(e=>e.Moving).ToArray())
                {
                    if(entry.Window==null) continue;
                    double progress=Animate?PopupStackLayout.Ease(frameTime-entry.Start,entry.Duration):1;
                    double Lerp(double a,double b)=>a+(b-a)*progress;
                    // Round the translation, rather than absolute coordinates, to keep equal gaps on half-pixel frames.
                    entry.Window.Place(new(entry.From.X+Math.Round((entry.Target.X-entry.From.X)*progress),
                        entry.From.Y+Math.Round((entry.Target.Y-entry.From.Y)*progress),entry.Target.Width,entry.Target.Height));
                    entry.Window.SetAlpha(Lerp(entry.FromAlpha,entry.ToAlpha));
                    if(progress>=1)
                    {
                        entry.Moving=false;
                        if(entry.Closing) { RemoveEntry(entry); QueueRefresh(); }
                        else _state.SetDisplayed(entry.Key,true);
                    }
                }
                RevealWaiting(false); ArmTimer();
                FramePresented?.Invoke(Snapshot());
            }
            catch(Exception error) when(error is System.ComponentModel.Win32Exception or System.Runtime.InteropServices.COMException or ArgumentException or InvalidOperationException)
            { LastError=PopupText.Message(error.Message); foreach(var entry in _entries.Values.ToArray()) RemoveEntry(entry); StopIfEmpty(); }
        }

        private void ArmTimer()
        {
            if(_disposed) return;
            bool moving=IsAnimating;
            bool expires=_state.Items.Any(e=>e.Displayed && !e.Persistent && !e.Held && double.IsFinite(e.RemainingMilliseconds));
            if(!moving && !expires) { _timer.Stop(); _lastTick=Now; return; }
            _timer.Interval=TimeSpan.FromMilliseconds(moving?16:100);
            if(!_timer.IsRunning) { _lastTick=Now; _timer.Start(); }
        }

        private void CloseWindow(Entry entry)
        {
            var window=entry.Window; entry.Window=null;
            entry.Moving=entry.Waiting=false;
            _state.Hold(entry.Key,false);
            if(window!=null && !window.IsClosed) { window.SetContent(new Grid()); window.Close(); }
        }

        private void RemoveEntry(Entry entry,bool removeState=true)
        {
            _entries.Remove(entry.Key);
            Detach(entry);
            CloseWindow(entry);
            if(removeState) _state.Remove(entry.Key);
        }

        private static void Detach(Entry entry)
        {
            foreach(var closing in entry.Closings) closing.Bar.Closing-=closing.Handler;
            entry.Closings.Clear();
            if(entry.Content is IHostedPopup hosted) { if(entry.Dismiss!=null) hosted.DismissRequested-=entry.Dismiss; hosted.IsHosted=false; }
            entry.Dismiss=null;
            if(entry.Content is VoiceOverlay voice) voice.IsAnimating=false;
        }

        private void StopIfEmpty() { if(_entries.Count!=0) return; _timer.Stop(); _placement.Watch(false); _lastTick=Now; }
        public void Dispose()
        {
            CheckThread(); if(_disposed) return;
            _disposed=true; _timer.Stop(); _timer.Tick-=OnTick;
            _owner.Closed-=OnOwnerClosed; _placement.Changed-=OnDesktopChanged;
            foreach(var entry in _entries.Values.ToArray()) RemoveEntry(entry);
            _state.Clear(); _placement.Dispose();
            FramePresented=null;
        }
    }
}
