using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.Foundation;
using Windows.Foundation.Collections;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace PLUMA.UI
{
    /// <summary>
    /// An empty window that can be used on its own or navigated to within a Frame.
    /// </summary>
    public sealed partial class MainWindow : Window
    {
        private PopupStackHost? _popups;
        private readonly CoreIpcClient _coreStatus = new();
        private readonly CancellationTokenSource _healthLifetime = new();
        private bool _closed;
        public PopupStackHost Popups
        {
            get
            {
                ObjectDisposedException.ThrowIf(_closed, this);
                return _popups ??= new PopupStackHost(this);
            }
        }

        public MainWindow()
        {
            InitializeComponent();

            // Extend content into the title bar so we can show a subtle app title
            // while retaining the native caption buttons. Register the AppTitleBar
            // element as the draggable title region.
            ExtendsContentIntoTitleBar = true;
            SetTitleBar(AppTitleBar);

            // Navigate to the default page (Dashboard)
            NavigateDashboard();
            Closed += async (_, _) =>
            {
                _closed = true; _healthLifetime.Cancel(); _popups?.Dispose();
                await _coreStatus.DisposeAsync(); _healthLifetime.Dispose();
            };
        }

        private void NavigateDashboard()
        {
            ContentFrame.Navigate(typeof(DashboardPage));
            if (ContentFrame.Content is DashboardPage dashboard) dashboard.AttachCoreClient(_coreStatus, _healthLifetime.Token);
        }

        private void NavView_ItemInvoked(NavigationView sender, NavigationViewItemInvokedEventArgs args)
        {
            if (args.IsSettingsInvoked)
            {
                ContentFrame.Navigate(typeof(SettingsPage));
                return;
            }

            if (args.InvokedItemContainer is NavigationViewItem invokedItem && invokedItem.Tag is string tag)
            {
                switch (tag)
                {
                    case "dashboard":
                        NavigateDashboard();
                        break;
                    case "history":
                        ContentFrame.Navigate(typeof(HistoryPage));
                        break;
                }
            }
        }
    }
}
