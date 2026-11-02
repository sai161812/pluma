using System;
using Microsoft.UI.Xaml.Controls;

namespace PLUMA.UI
{
    /// <summary>The host supplies XamlRoot and handles requests; this dialog never changes files.</summary>
    public sealed partial class ConflictAlertPopup : ContentDialog
    {
        public ConflictAlertPopup() => InitializeComponent();
        public event EventHandler? ViewConflictRequested;
        public event EventHandler? OpenFolderRequested;

        internal void BindSavedConflict(string? current, string? target)
        {
            CurrentPathText.PreserveLiteralText = ConflictPathText.PreserveLiteralText = true;
            CurrentPathText.IsTextSelectionEnabled = ConflictPathText.IsTextSelectionEnabled = true;
            CurrentPathText.Text = current ?? "No recorded file path";
            ConflictPathText.Text = target ?? "No recorded file path";
            IsSecondaryButtonEnabled = current is not null || target is not null;
        }

        private void OnViewConflict(ContentDialog sender, ContentDialogButtonClickEventArgs args)
        {
            args.Cancel = true;
            ViewConflictRequested?.Invoke(this, EventArgs.Empty);
        }

        private void OnOpenFolder(ContentDialog sender, ContentDialogButtonClickEventArgs args)
        {
            args.Cancel = true;
            OpenFolderRequested?.Invoke(this, EventArgs.Empty);
        }
    }
}
