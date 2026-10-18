using System;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;

namespace PLUMA.UI
{
    public enum SetupCheckId { OcrRuntime, UiAutomation, LocalModel, Microphone, Hotkeys }
    public enum SetupCheckState { Pending, Passed, Failed }

    public sealed class SetupCheck : INotifyPropertyChanged
    {
        public SetupCheckId Id { get; }
        public string Name { get; }
        public int Step { get; }
        public SetupCheckState State { get; private set; }
        public string Detail { get; private set; } = string.Empty;
        public string StatusText => State switch
        {
            SetupCheckState.Passed => "Available",
            SetupCheckState.Failed => "Unavailable",
            _ => "Not checked"
        };
        public event PropertyChangedEventHandler? PropertyChanged;

        internal SetupCheck(SetupCheckId id, string name, int step) { Id = id; Name = name; Step = step; }

        internal void Update(SetupCheckState state, string sanitizedDetail)
        {
            State = state;
            Detail = sanitizedDetail ?? string.Empty;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(State)));
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(StatusText)));
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Detail)));
        }
    }

    /// <summary>Readiness from host-supplied capability results, never simulated checks.</summary>
    public sealed class SetupChecklist
    {
        public ReadOnlyCollection<SetupCheck> Checks { get; } = Array.AsReadOnly(new[]
        {
            new SetupCheck(SetupCheckId.OcrRuntime, "OCR runtime", 0),
            new SetupCheck(SetupCheckId.UiAutomation, "Windows UI Automation", 0),
            new SetupCheck(SetupCheckId.LocalModel, "Local model path", 0),
            new SetupCheck(SetupCheckId.Microphone, "Microphone access", 1),
            new SetupCheck(SetupCheckId.Hotkeys, "Command and STOP hotkeys", 1)
        });

        public int CurrentStep { get; private set; }
        public bool IsReady => Checks.All(check => check.State == SetupCheckState.Passed);
        public bool CanAdvance => CurrentStep < 2 && Checks.Where(check => check.Step <= CurrentStep)
            .All(check => check.State == SetupCheckState.Passed);
        public bool CanComplete => CurrentStep == 2 && IsReady;
        public event EventHandler? Changed;

        public void Update(SetupCheckId id, SetupCheckState state, string sanitizedDetail)
        {
            if (!Enum.IsDefined(state)) throw new ArgumentOutOfRangeException(nameof(state));
            SetupCheck check = Checks.Single(check => check.Id == id);
            check.Update(state, sanitizedDetail);
            Changed?.Invoke(this, EventArgs.Empty);
        }

        public bool MoveNext()
        {
            if (!CanAdvance) return false;
            CurrentStep++;
            Changed?.Invoke(this, EventArgs.Empty);
            return true;
        }

        public void MoveBack()
        {
            if (CurrentStep == 0) return;
            CurrentStep--;
            Changed?.Invoke(this, EventArgs.Empty);
        }

        public void Reset()
        {
            CurrentStep = 0;
            foreach (SetupCheck check in Checks) check.Update(SetupCheckState.Pending, string.Empty);
            Changed?.Invoke(this, EventArgs.Empty);
        }
    }
}
