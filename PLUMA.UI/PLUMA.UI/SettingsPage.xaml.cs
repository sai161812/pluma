using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class SettingsPage : Page
    {
        private SettingsController? _settings;
        private CommandController? _commands;
        private CancellationToken _owner;
        private bool _applying, _loaded;
        private Task _activation = Task.CompletedTask;
        public SettingsPage()
        {
            InitializeComponent();
            Loaded += OnLoaded;
            Unloaded += (_, _) => { _loaded = false; if (_settings is not null) _settings.Changed -= Apply; };
        }
        internal void AttachSettings(SettingsController settings, CommandController commands, CancellationToken owner)
        {
            if (_settings is not null) _settings.Changed -= Apply;
            _settings = settings; _commands = commands; _owner = owner;
            _loaded = IsLoaded;
            settings.Changed += Apply; Apply(settings.View);
            if (_loaded) _activation = settings.RefreshAsync(owner);
        }
        private async void OnLoaded(object sender, RoutedEventArgs args)
        {
            _loaded = true;
            if (_settings is null) return;
            _settings.Changed -= Apply; _settings.Changed += Apply; Apply(_settings.View);
            if (!_settings.View.Connected) { _activation = _settings.RefreshAsync(_owner); await _activation; }
        }
        private void Apply(SettingsView view)
        {
            if (!DispatcherQueue.HasThreadAccess)
            {
                DispatcherQueue.TryEnqueue(() => { if (_loaded && _settings is not null) Apply(_settings.View); }); return;
            }
            if (_owner.IsCancellationRequested) return;
            _applying = true;
            try
            {
                if (!PlanLimit.Value.Equals(view.DraftLimit)) PlanLimit.Value = view.DraftLimit;
                PlanLimit.IsEnabled = view.CanEdit;
                SettingsRecover.IsEnabled=view.CanRecover;
                SettingsSave.IsEnabled = view.CanSave; SettingsCancel.IsEnabled = view.CanCancel;
                SettingsReload.IsEnabled = !view.Busy;
                SettingsStop.IsEnabled = _commands is not null && !_commands.View.StopPending;
                ModelPath.Text = view.DraftValues?.PlannerModelPath ?? "Unavailable";
                ModelPath.IsEnabled=SpeechModelPath.IsEnabled=TextHotkey.IsEnabled=StopHotkey.IsEnabled=VoiceHotkey.IsEnabled=view.CanEdit;
                SpeechModelPath.Text = view.DraftValues?.SttModelPath ?? "Unavailable";
                TextHotkey.Text = view.DraftValues?.TextHotkey ?? "Unavailable";
                StopHotkey.Text = view.DraftValues?.StopHotkey ?? "Unavailable";
                HotkeyStatus.Text=view.Saved?.HotkeysRegistered==true ? "Registered by Core" : "Not verified";
                VoiceHotkey.Text=view.DraftValues?.VoiceHotkey ?? "Unavailable";
                ModelGrace.Value=view.DraftValues?.ModelIdleUnloadSeconds ?? double.NaN;
                SpeechGrace.Value=view.DraftValues?.SttIdleUnloadSeconds ?? double.NaN;
                OcrGrace.Value=view.DraftValues?.OcrIdleUnloadSeconds ?? double.NaN;
                WarmGrace.IsOn=view.DraftValues?.AllowShortWarmGrace ?? false;
                ModelGrace.IsEnabled=SpeechGrace.IsEnabled=OcrGrace.IsEnabled=WarmGrace.IsEnabled=view.CanEdit;
                VoiceMode.Text = view.Runtime is null ? "Unavailable" : !view.Runtime.VoiceRequired
                    ? "Disabled in configuration" : PopupText.Label(view.Runtime.ActivationDefault);
                PrivacyDefaults.Text = view.Runtime is null ? "Unavailable" :
                    view.Runtime.SaveAudio || view.Runtime.PersistScreenshots
                    ? "Debug privacy settings need verification. Editing is unavailable."
                    : "Raw audio and screenshots are off by default.";
                ReadPolicy.Text = WritePolicy.Text = view.Connected ? "Checked for each action" : "Unavailable";
                HighRiskPolicy.Text = view.Runtime is null ? "Unavailable" : view.Runtime.ConfirmHighRisk
                    ? "Required" : "Configuration needs verification. Policy remains enforced.";
                SettingsStatus.Text = PopupText.Message(view.Message);
                SettingsCommandStatus.Text = PopupText.Message(view.CommandMessage +
                    (_commands?.View.StopMessage is string stop ? "\n" + stop : ""));
            }
            finally { _applying = false; }
        }
        private void OnFieldsChanged(object sender, TextChangedEventArgs args) => UpdateFields();
        private void OnGraceChanged(NumberBox sender, NumberBoxValueChangedEventArgs args) => UpdateFields();
        private void OnWarmChanged(object sender, RoutedEventArgs args) => UpdateFields();
        private void UpdateFields()
        {
            if(_applying || _settings?.View.DraftValues is not {} values || ModelGrace is null || WarmGrace is null) return;
            int Delay(double value)=>double.IsFinite(value) && value==Math.Truncate(value) ? (int)value : -1;
            _settings.SetValues(values with {TextHotkey=TextHotkey.Text,StopHotkey=StopHotkey.Text,VoiceHotkey=VoiceHotkey.Text,
                PlannerModelPath=ModelPath.Text,SttModelPath=SpeechModelPath.Text,
                ModelIdleUnloadSeconds=Delay(ModelGrace.Value),SttIdleUnloadSeconds=Delay(SpeechGrace.Value),
                OcrIdleUnloadSeconds=Delay(OcrGrace.Value),AllowShortWarmGrace=WarmGrace.IsOn});
        }
        private void OnLimitChanged(NumberBox sender, NumberBoxValueChangedEventArgs args)
        { if (!_applying) _settings?.SetDraft(args.NewValue); }
        private async void OnRecover(object sender, RoutedEventArgs args)
        { if(_settings is not null)await _settings.RecoverAsync(_owner); }
        private async void OnSave(object sender, RoutedEventArgs args)
        { if (_settings is not null) await _settings.SaveAsync(_owner); }
        private void OnCancel(object sender, RoutedEventArgs args) => _settings?.CancelEdits();
        private async void OnReload(object sender, RoutedEventArgs args)
        { if (_settings is not null) await _settings.RefreshAsync(_owner); }
        private async void OnStop(object sender, RoutedEventArgs args)
        { if (_commands is not null) await _commands.StopAsync(); }
    }
}
