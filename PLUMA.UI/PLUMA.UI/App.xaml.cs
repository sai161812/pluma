using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Navigation;
using Microsoft.UI.Xaml.Shapes;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices.WindowsRuntime;
using Windows.ApplicationModel;
using Windows.ApplicationModel.Activation;
using Windows.Foundation;
using Windows.Foundation.Collections;

// To learn more about WinUI, the WinUI project structure,
// and more about our project templates, see: http://aka.ms/winui-project-info.

namespace PLUMA.UI
{
    /// <summary>
    /// Provides application-specific behavior to supplement the default Application class.
    /// </summary>
    public partial class App : Application
    {
        private Window? _window;
        private Window? _voicePreviewWindow;

        /// <summary>
        /// Initializes the singleton application object.  This is the first line of authored code
        /// executed, and as such is the logical equivalent of main() or WinMain().
        /// </summary>
        public App()
        {
            InitializeComponent();
        }

        /// <summary>
        /// Invoked when the application is launched.
        /// </summary>
        /// <param name="args">Details about the launch request and process.</param>
        protected override void OnLaunched(Microsoft.UI.Xaml.LaunchActivatedEventArgs args)
        {
            string[] commandLine = Environment.GetCommandLineArgs();
            int stackAudit = Array.IndexOf(commandLine, "--popup-stack-audit");
            if (Array.IndexOf(commandLine, "--popup-stack-preview") >= 0 || stackAudit >= 0)
            {
                string? directory = stackAudit >= 0 && stackAudit + 1 < commandLine.Length ? commandLine[stackAudit + 1] : null;
                if (stackAudit >= 0 && string.IsNullOrWhiteSpace(directory)) throw new ArgumentException("An audit output directory is required.");
                _window = new PopupStackPreviewWindow(directory);
                _window.Activate();
                return;
            }
            if (Array.IndexOf(Environment.GetCommandLineArgs(), "--surface-gallery") >= 0)
            {
                string[] launchArgs = Environment.GetCommandLineArgs();
                int exportIndex = Array.IndexOf(launchArgs, "--surface-gallery-export");
                string? exportDirectory = exportIndex >= 0 && exportIndex + 1 < launchArgs.Length ? launchArgs[exportIndex + 1] : null;
                _window = new SurfaceGalleryWindow(exportDirectory);
                _window.Activate();
                return;
            }

            _window = new MainWindow();
            _window.Activate();

            // The legacy microphone fixture is opt-in. Production overlays belong to MainWindow.Popups.
            if (Array.IndexOf(commandLine, "--voice-preview") >= 0)
            {
                _voicePreviewWindow = new VoiceOverlayPreviewWindow();
                _voicePreviewWindow.Activate();
            }

        }
    }
}
