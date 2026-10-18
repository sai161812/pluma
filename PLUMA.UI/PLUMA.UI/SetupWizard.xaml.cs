using System;
using System.Linq;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    public sealed partial class SetupWizard : Page
    {
        private readonly SetupChecklist _checklist = new();

        public SetupWizard()
        {
            InitializeComponent();
            _checklist.Changed += (_, _) => ApplyStep();
            ApplyStep();
        }

        public event EventHandler? RecheckRequested;
        public event EventHandler? ContinueRequested;

        // Only the host performs capability checks and persists first-run completion.
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
            NextButton.IsEnabled = step == 2 ? _checklist.CanComplete : _checklist.CanAdvance;
        }

        private void OnBackClick(object sender, RoutedEventArgs e) => _checklist.MoveBack();

        private void OnRecheckClick(object sender, RoutedEventArgs e)
        {
            _checklist.Reset();
            RecheckRequested?.Invoke(this, EventArgs.Empty);
        }

        private void OnNextClick(object sender, RoutedEventArgs e)
        {
            if (_checklist.CurrentStep < 2) _checklist.MoveNext();
            else if (_checklist.CanComplete) ContinueRequested?.Invoke(this, EventArgs.Empty);
        }
    }
}
