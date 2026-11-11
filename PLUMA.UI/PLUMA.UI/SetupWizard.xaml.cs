using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class SetupWizard : Page
    {
        private readonly SetupChecklist _checklist = new();
        private HealthController? _health;
        private CommandController? _commands;
        private CancellationToken _owner;
        private bool _trusted;
        internal void AttachHealth(HealthController health,CommandController commands,CancellationToken owner)
        { _health=health;_commands=commands;_owner=owner;health.Changed+=ApplyHealth;ApplyHealth(health.View); }
        private void ApplyHealth(HealthView view)
        {
            if(!DispatcherQueue.HasThreadAccess){DispatcherQueue.TryEnqueue(()=>{if(IsLoaded&&_health is not null)ApplyHealth(_health.View);});return;}
            _trusted=view.CanContinue;
            foreach(var check in _checklist.Checks)
            {
                string? id=check.Id switch {SetupCheckId.OcrRuntime=>"ocr",SetupCheckId.LocalModel=>"planner",SetupCheckId.SpeechModel=>"speech",
                    SetupCheckId.UiAutomation=>"uia",SetupCheckId.Microphone=>"microphone",_=>null};
                var evidence=view.Snapshot?.Checks.SingleOrDefault(c=>c.Id==id);
                var state=check.Id==SetupCheckId.Hotkeys
                    ? view.Snapshot?.HotkeysRegistered==true?SetupCheckState.Passed:SetupCheckState.Pending
                    : evidence?.State switch {"PASSED"=>SetupCheckState.Passed,"FAILED"=>SetupCheckState.Failed,_=>SetupCheckState.Pending};
                _checklist.Update(check.Id,state,evidence?.Code??"Native check required.");
            }
            SetupStatus.Text=PopupText.Message(view.Message);
            RecheckButton.IsEnabled=view.CanCheck;
            MicrophoneConsent.IsEnabled=!view.Busy;
            SetupStop.IsEnabled=_commands is not null&&!_commands.View.StopPending;
            ApplyStep();
        }

        public SetupWizard()
        {
            InitializeComponent();
            _checklist.Changed += (_, _) => ApplyStep();
            Unloaded+=(_,_)=>{if(_health is not null)_health.Changed-=ApplyHealth;};
            ApplyStep();
        }

        public event EventHandler? RecheckRequested;
        public event EventHandler? ContinueRequested;

        // Fixture display updates never grant production Continue; the host rechecks native proof.
        public void SetCheckResult(SetupCheckId id, SetupCheckState state, string sanitizedDetail) =>
            _checklist.Update(id, state, sanitizedDetail);

        private void ApplyStep()
        {
            int step = _checklist.CurrentStep;
            StepText.Text = $"Step {step + 1} of 3";
            StepProgress.Value = step;
            StepHeading.Text = step switch { 0 => "Local dependencies", 1 => "Voice and hotkeys", _ => "Review checks" };
            CheckList.ItemsSource = _checklist.Checks.Where(check => step == 2 || check.Step == step).ToArray();
            BackButton.IsEnabled = step > 0;
            NextButton.Content = step == 2 ? "Continue" : "Next";
            NextButton.IsEnabled = step == 2 ? _checklist.CanComplete && _trusted : _checklist.CanAdvance;
        }

        private async void OnStopClick(object sender,RoutedEventArgs args){if(_commands is not null)await _commands.StopAsync();}

        private void OnBackClick(object sender, RoutedEventArgs e) => _checklist.MoveBack();

        private async void OnRecheckClick(object sender, RoutedEventArgs e)
        {
            _checklist.Reset();
            RecheckRequested?.Invoke(this, EventArgs.Empty);
            if(_health is not null)await _health.CheckAsync(MicrophoneConsent.IsChecked==true,_owner);
        }

        private void OnNextClick(object sender, RoutedEventArgs e)
        {
            if (_checklist.CurrentStep < 2) _checklist.MoveNext();
            else if (_checklist.CanComplete && _trusted) ContinueRequested?.Invoke(this, EventArgs.Empty);
        }
    }
}
