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
