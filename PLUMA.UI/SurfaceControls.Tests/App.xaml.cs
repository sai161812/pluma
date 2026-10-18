using System;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI.Tests
{
    public partial class App : Application
    {
        private Window? _window;
        private int _checks;

        public App() => InitializeComponent();

        protected override async void OnLaunched(LaunchActivatedEventArgs args)
        {
            int exitCode = 0;
            try
            {
                var root = new StackPanel { Spacing = 12 };
                _window = new Window { Title = "PLUMA UI contract checks", Content = root };
                _window.Activate();
                await RunChecks(root);
                Console.WriteLine($"{_checks} UI checks passed.");
                if (Array.IndexOf(Environment.GetCommandLineArgs(), "--visual-review") >= 0)
                    await VisualReview.RenderAsync(_window);
            }
            catch (Exception error)
            {
                Console.Error.WriteLine(error);
                exitCode = 1;
            }
            finally
            {
                _window?.Close();
                Environment.Exit(exitCode);
            }
        }

        private void Check(bool condition, string name)
        {
            if (!condition) throw new InvalidOperationException(name);
            _checks++;
            Console.WriteLine($"PASS {name}");
        }

        private static async Task Click(Button button)
        {
            var peer = FrameworkElementAutomationPeer.CreatePeerForElement(button);
            ((IInvokeProvider)peer.GetPattern(PatternInterface.Invoke)).Invoke();
            await Task.Delay(100);
        }

        private async Task RunChecks(StackPanel root)
        {
            var marker = new OcrMatchIndicator { Width = 600, Height = 240 };
            root.Children.Add(marker);
            await Task.Delay(100);
            Check(!marker.IsMatchVisible && !marker.IsHitTestVisible, "OCR marker starts hidden and cannot intercept input");
            var bounds = new Windows.Foundation.Rect(30, 30, 100, 24);
            var desktop = new Windows.Foundation.Point(-120, 200);
            marker.ShowMatch("Submit", 0.95, bounds, desktop, DateTimeOffset.UtcNow.AddSeconds(1));
            Check(marker.IsMatchVisible && ((PopupMessageText)marker.FindName("MatchText")).Text == "Submit", "OCR marker displays supplied match");
            Check(((PopupMessageText)marker.FindName("MetadataText")).Text.Contains("-120"), "OCR metadata supports negative desktop coordinates");
            marker.ShowMatch("Submit", double.NaN, bounds, desktop, DateTimeOffset.UtcNow.AddSeconds(1));
            Check(!marker.IsMatchVisible, "invalid OCR confidence clears marker");
            marker.ShowMatch("Submit", 0.9, bounds, desktop, DateTimeOffset.UtcNow.AddSeconds(-1));
            Check(!marker.IsMatchVisible, "expired OCR snapshot is not shown");
            marker.ShowMatch("Submit", 0.9, new Windows.Foundation.Rect(590, 20, 100, 24), desktop, DateTimeOffset.UtcNow.AddSeconds(1));
            Check(!marker.IsMatchVisible, "OCR target outside host geometry is rejected");
            marker.ShowMatch("Submit", 0.9, bounds, desktop, DateTimeOffset.UtcNow.AddMilliseconds(100));
            await Task.Delay(200);
            Check(!marker.IsMatchVisible && ((PopupMessageText)marker.FindName("MatchText")).Text == "", "OCR expiry clears visual evidence");
            marker.ShowMatch("Submit", 0.9, bounds, desktop, DateTimeOffset.UtcNow.AddSeconds(1));
            root.Children.Remove(marker);
            await Task.Delay(100);
            Check(!marker.IsMatchVisible, "unloading clears OCR marker and timer");

            var verification = new PostClickVerifyIndicator();
            root.Children.Add(verification);
            Check(!verification.IsOpen, "verification starts without a result");
            verification.ShowResult(true, "ocr_rescan", "Expected label appeared");
            Check(verification.IsOpen && verification.Title == "Verified" && verification.Severity == InfoBarSeverity.Success,
                "positive verifier evidence displays success");
            verification.ShowResult(false, "ocr_rescan", "Expected transition not observed");
            Check(verification.Title == "Unverified" && verification.Severity == InfoBarSeverity.Error && ((PopupMessageText)verification.FindName("NoticeText")).DisplayText.Contains("not observed"),
                "failed verification replaces prior success with factual failure");
            verification.ShowResult(true, "", "");
            Check(!verification.IsOpen, "missing verification method cannot display success");
            root.Children.Remove(verification);

            var feed = new LiveMessageFeed();
            root.Children.Add(feed);
            Check(((TextBlock)feed.FindName("EmptyText")).Visibility == Visibility.Visible, "feed empty state visible");
            feed.AppendMessage("Opened Notepad", DateTimeOffset.UtcNow);
            Check(((ListView)feed.FindName("MessageList")).Items.Count == 1, "feed displays supplied event");
            feed.ClearMessages();
            Check(((ListView)feed.FindName("MessageList")).Visibility == Visibility.Collapsed, "feed clear restores empty state");

            var health = new CoreHealthIndicator();
            root.Children.Add(health);
            Check(!health.IsConnected && ((TextBlock)health.FindName("StatusText")).Text == "Disconnected", "health defaults disconnected");
            health.IsConnected = true;
            health.PingLatencyMs = 12;
            Check(((TextBlock)health.FindName("LatencyText")).Text == "12 ms", "connected health displays measured latency");
            health.IsConnected = false;
            Check(((TextBlock)health.FindName("LatencyText")).Visibility == Visibility.Collapsed, "disconnect hides stale latency");
            health.IsConnected = true;
            Check(double.IsNaN(health.PingLatencyMs), "reconnection requires a fresh latency measurement");
            health.PingLatencyMs = double.PositiveInfinity;
            Check(((TextBlock)health.FindName("LatencyText")).Visibility == Visibility.Collapsed, "invalid latency hidden");
            health.Resources.ThemeDictionaries["Dark"] = new ResourceDictionary
            {
                ["SystemFillColorSuccessBrush"] = new SolidColorBrush(Windows.UI.Color.FromArgb(255, 40, 50, 60))
            };
            root.RequestedTheme = ElementTheme.Dark;
            await Task.Delay(100);
            Check(((SolidColorBrush)((InfoBadge)health.FindName("StatusBadge")).Background).Color.R == 40,
                "status brush follows dark theme resources");

            var notice = new ToastNotification();
            root.Children.Add(notice);
            await Task.Delay(100);
            Check(!notice.IsOpen, "notice starts closed");
            notice.Show("Could not verify action", InfoBarSeverity.Warning, TimeSpan.FromMilliseconds(100));
            Check(notice.IsOpen && ((InfoBar)notice.FindName("Notice")).Severity == InfoBarSeverity.Warning, "notice displays supplied severity");
            await Task.Delay(250);
            Check(!notice.IsOpen && notice.Visibility == Visibility.Collapsed, "notice auto-dismisses");
            notice.Show("First", duration: TimeSpan.FromMilliseconds(100));
            notice.Show("Replacement", duration: TimeSpan.FromSeconds(1));
            await Task.Delay(250);
            Check(notice.IsOpen && ((PopupMessageText)notice.FindName("NoticeText")).DisplayText == "Replacement", "replacement resets dismissal timer");
            await Click(FindButton(notice, "Close"));
            Check(!notice.IsOpen, "manual close stops notice");
            notice.Show("Transient");
            root.Children.Remove(notice);
            await Task.Delay(100);
            Check(!notice.IsOpen, "unloading closes notice and stops its timer");

            var wizard = new SetupWizard();
            root.Children.Add(wizard);
            var next = (Button)wizard.FindName("NextButton");
            Check(!next.IsEnabled, "setup cannot advance with unchecked capabilities");
            wizard.SetCheckResult(SetupCheckId.OcrRuntime, SetupCheckState.Passed, "Verified");
            wizard.SetCheckResult(SetupCheckId.UiAutomation, SetupCheckState.Passed, "Verified");
            wizard.SetCheckResult(SetupCheckId.LocalModel, SetupCheckState.Passed, "Verified");
            await Click(next);
            Check(!next.IsEnabled, "setup requires voice and hotkey results");
            wizard.SetCheckResult(SetupCheckId.Microphone, SetupCheckState.Passed, "Verified");
            wizard.SetCheckResult(SetupCheckId.Hotkeys, SetupCheckState.Passed, "Verified");
            await Click(next);
            int continueRequests = 0;
            wizard.ContinueRequested += (_, _) => continueRequests++;
            await Click(next);
            Check(continueRequests == 1, "Continue requests host transition after all checks pass");
            wizard.SetCheckResult(SetupCheckId.Microphone, SetupCheckState.Failed, "Access revoked");
            Check(!next.IsEnabled, "revoked capability disables Continue");

            var dialog = new CriticalErrorDialog { XamlRoot = root.XamlRoot, ErrorMessage = "Core disconnected" };
            Check(!dialog.CanRestart && !dialog.IsPrimaryButtonEnabled, "recovery starts disabled");
            dialog.SanitizedDetails = "IPC unavailable";
            dialog.CanRestart = true;
            int restartRequests = 0;
            dialog.RestartRequested += (_, _) => restartRequests++;
            var showing = dialog.ShowAsync();
            await Task.Delay(200);
            Check(((Expander)dialog.FindName("DetailsExpander")).Visibility == Visibility.Visible, "provided recovery details available");
            await Click(FindButton(dialog, "Restart core"));
            Check(restartRequests == 1 && !dialog.CanRestart, "restart requests once and disables duplicate request");
            Check(showing.Status == Windows.Foundation.AsyncStatus.Started, "failure stays visible while host verifies recovery");
            dialog.Hide();
            await showing;
        }

        private static Button FindButton(DependencyObject root, string content)
        {
            if (root is Button button && (button.Content?.ToString() == content ||
                Microsoft.UI.Xaml.Automation.AutomationProperties.GetName(button) == content)) return button;
            for (int index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
            {
                try { return FindButton(VisualTreeHelper.GetChild(root, index), content); }
                catch (InvalidOperationException) { }
            }
            throw new InvalidOperationException($"Button not found: {content}");
        }
    }
}
