using System;
using System.Collections.Generic;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI;

/// <summary>Readback-only mappings; disappearance dismisses a view, never claims completion.</summary>
internal static class RuntimePresentation
{
    internal static string Elapsed(long? milliseconds) => milliseconds is null ? "Unavailable" :
        $"{milliseconds.Value / 3600000:D2}:{milliseconds.Value / 60000 % 60:D2}:{milliseconds.Value / 1000 % 60:D2}";
    internal static string Phase(CoreRequestProtocol.RuntimeTask task) => task.State is "STOPPING" or "ROLLING_BACK"
        ? PopupText.Label(task.State) : task.Phase switch { "EXECUTING" => "Executing", "VERIFYING" => "Verifying",
            "RECORDING" => "Recording outcome", "DISPATCHING" => "Dispatching", _ => "Awaiting task phase" };

    internal static IReadOnlyList<(string Key, int Surface)> Keys(CoreRequestProtocol.RuntimeTask task)
    {
        var keys = new List<(string, int)> { ("runtime-task-" + task.TaskId, 4) };
        if (task.Step is not null) keys.Add(("runtime-step-" + task.TaskId, 5));
        if (task.Tool is not null && task.State == "RUNNING") keys.Add(("runtime-tool-" + task.TaskId, 7));
        if (task.State == "ROLLING_BACK" || (task.State == "RUNNING" && task.Tool == "undo_last" && task.Phase is "EXECUTING" or "VERIFYING" or "RECORDING")) keys.Add(("runtime-rollback-" + task.TaskId, 9));
        return keys;
    }

    internal static FrameworkElement Create(int surface, CoreRequestProtocol.RuntimeTask task)
    {
        FrameworkElement control = surface switch { 4 => new TaskRunningPopup(), 5 => new StepProgressPopup(),
            7 => new ToolCallCard(), 9 => new RollbackPopup(), _ => throw new ArgumentException("Unsupported runtime surface.") };
        Apply(control, surface, task); return control;
    }

    internal static void Apply(FrameworkElement control, int surface, CoreRequestProtocol.RuntimeTask task)
    {
        void Text(string name, string value)
        {
            object field = control.FindName(name);
            if (field is PopupMessageText message) message.Text = value;
            else ((TextBlock)field).Text = value;
        }
        void State(string name, string label)
        { var state = (PopupStatusIndicator)control.FindName(name); state.Label = label; state.Kind = PopupStatusKind.Progress; }
        if (surface == 4)
        {
            State("TaskStatus", PopupText.Label(task.State));
            Text("TaskMessage", Phase(task)); Text("TaskIdentity", task.TaskId);
            Text("ElapsedText", Elapsed(task.ElapsedMs));
        }
        else if (surface == 5)
        {
            State("StepStatus", Phase(task));
            Text("StepText", $"Step {task.Step} of {task.Total}"); Text("StepTool", PopupText.Label(task.Tool ?? "Unavailable"));
            Text("StepDetail", $"Validated plan revision {task.PlanRevision}");
        }
        else if (surface == 7)
        {
            State("CallStatus", Phase(task)); Text("CallTool", PopupText.Label(task.Tool ?? "Unavailable"));
            Text("CallArguments", task.Arguments ?? "Arguments unavailable"); Text("CallElapsed", "Elapsed " + Elapsed(task.ToolElapsedMs));
            Text("CallRisk", "Risk: " + PopupText.Label(task.Risk ?? "Unavailable"));
        }
        else if (surface == 9)
        {
            State("RollbackStatus", task.State == "ROLLING_BACK" ? "Rolling back" : "Restoring selected action"); Text("RollbackHeading", "Undoing reversible actions");
            Text("RollbackStep", task.RollbackStep is null ? "Waiting for saved inverse verification" : $"Inverse {task.RollbackStep} of {task.RollbackTotal}");
            var progress = (ProgressBar)control.FindName("RollbackProgress"); progress.IsIndeterminate = true;
            Text("RollbackRecipe", PopupText.Label(task.RollbackRecipe ?? "Recipe unavailable"));
            Text("RollbackCompleted", "Completed inverses require saved verification."); Text("RollbackPending", "Rollback outcome pending");
            ((ProgressRing)control.FindName("RollbackRing")).IsActive = true;
        }
    }
}
