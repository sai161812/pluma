using System;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace PLUMA.UI
{
    /// <summary>Explicit, owned fixture producer. Never starts the core or microphone.</summary>
    public sealed partial class PopupStackPreviewWindow : Window
    {
        private readonly Grid _root;
        private readonly ComboBox _picker;
        private readonly TextBlock _status;
        private PopupStackHost _host;
        private readonly CancellationTokenSource _lifetime = new();
        private Task? _auditTask;
        private int _sequence;
        private bool _closed;

        public PopupStackPreviewWindow(string? auditDirectory = null)
        {
            Title = "PLUMA popup stack preview";
            SystemBackdrop = new MicaBackdrop();
            AppWindow.Resize(new Windows.Graphics.SizeInt32(740,600));
            _root = new Grid { RequestedTheme=ElementTheme.Dark, Padding=new Thickness(28,24,28,24), RowSpacing=16 };
            Content=_root;
            _host=new PopupStackHost(this);
            for(int i=0;i<5;i++) _root.RowDefinitions.Add(new RowDefinition { Height=i==4?new GridLength(1,GridUnitType.Star):GridLength.Auto });
            _root.Children.Add(new TextBlock { Text="Desktop popup stack", FontSize=28, FontWeight=Microsoft.UI.Text.FontWeights.SemiBold });
            var explanation=new TextBlock { Text="Preview fixtures only. All popups share the bottom-right lane. No microphone or core connection is started.", TextWrapping=TextWrapping.Wrap };
            Grid.SetRow(explanation,1); _root.Children.Add(explanation);
            _picker=new ComboBox { Header="Surface", HorizontalAlignment=HorizontalAlignment.Stretch, DisplayMemberPath="Label",
                ItemsSource=SurfaceGalleryCatalog.Items.Where(s=>s.Id is >=4 and <=9 or >=11 and <=14 or 17 or >=19 and <=21 or 24).ToArray(), SelectedIndex=0 };
            Grid.SetRow(_picker,2); _root.Children.Add(_picker);
            var actions=new StackPanel { Spacing=8 };
            var first=new StackPanel { Orientation=Orientation.Horizontal, Spacing=8 };
            var second=new StackPanel { Orientation=Orientation.Horizontal, Spacing=8 };
            AddButton(first,"Show selected",()=>ShowSelected());
            AddButton(first,"Add notice",()=>AddNotice());
            AddButton(first,"Burst",()=> { for(int i=0;i<8;i++) AddNotice(); });
            AddButton(first,"Long message",()=>AddNotice(true));
            AddButton(second,"Dismiss oldest",()=>DismissAt(0));
            AddButton(second,"Dismiss newest",()=>DismissAt(-1));
            AddButton(second,"Clear",()=>_host.Clear());
            var motion=new CheckBox { Content="Disable motion for this preview" };
            motion.Checked+=(_,_)=>{_host.SuppressAnimations=true; _host.Update("task",_=>{});};
            motion.Unchecked+=(_,_)=>_host.SuppressAnimations=false;
            actions.Children.Add(first); actions.Children.Add(second); actions.Children.Add(motion);
            Grid.SetRow(actions,3); _root.Children.Add(actions);
            _status=new TextBlock { Text="Ready. Move the pointer to the bottom edge to review taskbar clearance.", TextWrapping=TextWrapping.Wrap };
            Grid.SetRow(_status,4); _root.Children.Add(_status);
            void EnableActions(bool enabled)
            {
                _picker.IsEnabled=enabled;
                foreach(var control in first.Children.Concat(second.Children).OfType<Control>().Append(motion)) control.IsEnabled=enabled;
            }
            bool started=false;
            _root.Loaded+=async(_,_)=>
            {
                if(started || string.IsNullOrWhiteSpace(auditDirectory)) return;
                started=true;
                EnableActions(false);
                _auditTask=RunAuditAsync(auditDirectory,_lifetime.Token);
                try { await _auditTask; }
                catch(OperationCanceledException) { }
                catch(Exception error)
                {
                    try { Directory.CreateDirectory(auditDirectory); File.WriteAllText(Path.Combine(auditDirectory,"audit-error.txt"),error.ToString()); }
                    catch(IOException) { } catch(UnauthorizedAccessException) { }
                    if(!_closed) _status.Text="Popup audit failed. See audit-error.txt.";
                }
                finally { if(!_closed) EnableActions(true); }
            };
            Closed+=async(_,_)=>
            {
                _closed=true; _lifetime.Cancel(); _host.Dispose();
                if(_auditTask!=null) { try {await _auditTask;} catch(Exception) { } }
                _lifetime.Dispose();
            };
        }

        private static void AddButton(StackPanel row,string label,Action action)
        {
            var button=new Button { Content=label };
            button.Click+=(_,_)=>action(); row.Children.Add(button);
        }

        private void ShowSelected()
        {
            if(_picker.SelectedItem is not SurfaceGalleryItem item) return;
            FrameworkElement content=CreateFixture(item.Id);
            string key=item.Id switch { 4 or 5 or 9 or 20=>"task", 7 or 8=>"tool", >=11 and <=14=>"voice", _=>$"surface-{item.Id}" };
            if(!_host.Present(key,item.Id,content)) _status.Text=_host.LastError??"The popup queue is full.";
            else _status.Text="Preview added to the shared stack. New entries appear below older entries.";
        }

        private static FrameworkElement CreateFixture(int id)
        {
            switch(id)
            {
                case 4:return new TaskRunningPopup();
                case 5:return new StepProgressPopup();
                case 6:return new RouteBadgePopup();
                case 7:return new ToolCallCard();
                case 8:return new ToolResultCard();
                case 9:return new RollbackPopup();
                case >=11 and <=14:return new VoiceOverlay { VoiceState=id switch {13=>VoiceOverlayState.Committed,14=>VoiceOverlayState.SilenceTimeout,_=>VoiceOverlayState.ListeningSpeech},
                    FinalTranscript="Preview speech stays in the same voice card", PartialTranscript="while the next words arrive", SilenceProgress=0.65 };
                case 17:
                    var verification=new PostClickVerifyIndicator();
                    verification.ShowResult(false,"ocr_rescan","The expected change was not observed."); return verification;
                case 19:return new PolicyBlockNotice {ToolName="invoke_control",MatchedRule="The target window changed.",IsNoticeOpen=true};
                case 20:return new CancellationAnimation {IsActive=true};
                case 21:return new WorkerTerminationFlash {IsOpen=true};
                case 24:
                    var notice=new ToastNotification(); notice.Show("Preview notification"); return notice;
                default:throw new ArgumentOutOfRangeException(nameof(id));
            }
        }

        private void AddNotice(bool longText=false)
        {
            var notice=new ToastNotification();
            string text=longText?string.Join(" ",Enumerable.Repeat("Please check quarterly_report.pdf before continuing. "+new string('W',120),12)):$"Preview notification {++_sequence}";
            notice.Show(text);
            if(!_host.Present($"notice-{++_sequence}",24,notice,lifetime:TimeSpan.FromSeconds(longText?30:8)))
                _status.Text=_host.LastError??"The popup queue is full.";
        }

        private void DismissAt(int index)
        {
            var visible=_host.Snapshot();
            if(visible.Count>0) _host.Dismiss(visible[index<0?visible.Count-1:index].Key);
        }
    }
}
