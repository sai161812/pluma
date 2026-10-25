using System;
using System.IO;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Markup;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Graphics.Imaging;
using Windows.Storage;

namespace PLUMA.UI.Tests
{
    /// <summary>Opt-in rendering of test-owned controls; no desktop or user-window capture.</summary>
    internal static class VisualReview
    {
        public static async Task RenderAsync(Window window)
        {
            string output = Path.Combine(AppContext.BaseDirectory, "visual-review");
            Directory.CreateDirectory(output);
            window.AppWindow.Resize(new Windows.Graphics.SizeInt32(1460, 980));

            const ElementTheme theme = ElementTheme.Dark;
            string suffix = theme.ToString().ToLowerInvariant();
            Grid root = CreateRoot(theme);
            var feed = new LiveMessageFeed();
            feed.AppendMessage("Opened Notepad", new DateTimeOffset(2026, 10, 18, 12, 0, 0, TimeSpan.Zero));
            feed.AppendMessage("Could not verify Submit action", new DateTimeOffset(2026, 10, 18, 12, 0, 1, TimeSpan.Zero));
            var health = new CoreHealthIndicator { IsConnected = true, PingLatencyMs = 12 };
            var notice = new ToastNotification();
            notice.Show("Could not verify Submit action", InfoBarSeverity.Warning, TimeSpan.FromMinutes(1));
            var policy = new PolicyBlockNotice { ToolName = "invoke_control", MatchedRule = "Target changed", IsNoticeOpen = true };
            var newStack = new StackPanel { Spacing = 20, Margin = new Thickness(28, 24, 28, 32) };
            newStack.Children.Add(health);
            newStack.Children.Add(feed);
            newStack.Children.Add(notice);
            newStack.Children.Add(new TextBlock { Text = "Existing notice for comparison", Margin = new Thickness(0, 20, 0, 0) });
            newStack.Children.Add(policy);
            AddColumn(root, new DashboardPage(), "Existing Dashboard", 0);
            AddColumn(root, newStack, "New status components", 1);
            window.Content = root;
            await CaptureAsync(root, Path.Combine(output, $"status-{suffix}.png"));

            root = CreateRoot(theme);
            AddColumn(root, new SettingsPage(), "Existing Settings", 0);
            AddColumn(root, new SetupWizard(), "New setup wizard", 1);
            window.Content = root;
            await CaptureAsync(root, Path.Combine(output, $"setup-{suffix}.png"));

            root = CreateRoot(theme);
            var perceptionPanel = new Grid { Margin = new Thickness(28, 24, 28, 32) };
            var target = new Button { Content = "Submit", Width = 100, Height = 32,
                HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top,
                Margin = new Thickness(30, 30, 0, 0) };
            var marker = new OcrMatchIndicator();
            perceptionPanel.Children.Add(target);
            perceptionPanel.Children.Add(marker);
            var verification = new PostClickVerifyIndicator { VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 220, 0, 0) };
            verification.ShowResult(false, "ocr_rescan", "Expected transition not observed");
            perceptionPanel.Children.Add(verification);
            AddColumn(root, new PolicyBlockNotice { IsNoticeOpen = true, ToolName = "invoke_control", MatchedRule = "Target changed" }, "Existing policy notice", 0);
            AddColumn(root, perceptionPanel, "OCR match and verification", 1);
            window.Content = root;
            await Task.Delay(100);
            marker.ShowMatch("Submit", 0.95, new Windows.Foundation.Rect(30, 30, 100, 32),
                new Windows.Foundation.Point(1200, 300), DateTimeOffset.UtcNow.AddSeconds(3));
            await CaptureAsync(root, Path.Combine(output, $"perception-{suffix}.png"));

            root = CreateRoot(theme);
            window.Content = root;
            await Task.Delay(100);
            var approval = new RiskApprovalDialog
            {
                XamlRoot = root.XamlRoot,
                RequestedTheme = theme,
                ToolName = "restart_request",
                RiskClass = "HIGH",
                SanitizedArguments = "Requested system restart"
            };
            var showingApproval = approval.ShowAsync();
            await CaptureAsync(approval, Path.Combine(output, $"approval-{suffix}.png"));
            approval.Hide();
            await showingApproval;

            var error = new CriticalErrorDialog
            {
                XamlRoot = root.XamlRoot,
                RequestedTheme = theme,
                ErrorMessage = "The resident core disconnected. Restart the core to continue.",
                SanitizedDetails = "IPC connection closed.",
                CanRestart = true
            };
            var showingError = error.ShowAsync();
            await CaptureAsync(error, Path.Combine(output, $"critical-{suffix}.png"));
            error.Hide();
            await showingError;
            Console.WriteLine($"Visual review renders: {output}");
        }

        private static Grid CreateRoot(ElementTheme theme)
        {
            var grid = (Grid)XamlReader.Load("<Grid xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' Background='{ThemeResource ApplicationPageBackgroundThemeBrush}' Width='1400' Height='900' Padding='16' ColumnSpacing='16'><Grid.ColumnDefinitions><ColumnDefinition Width='*'/><ColumnDefinition Width='*'/></Grid.ColumnDefinitions></Grid>");
            grid.RequestedTheme = theme;
            return grid;
        }

        private static void AddColumn(Grid grid, FrameworkElement content, string label, int column)
        {
            var panel = new Grid();
            panel.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            panel.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
            panel.Children.Add(new TextBlock { Text = label, Margin = new Thickness(0, 0, 0, 12), FontSize = 14 });
            Grid.SetRow(content, 1);
            panel.Children.Add(content);
            Grid.SetColumn(panel, column);
            grid.Children.Add(panel);
        }

        private static async Task CaptureAsync(FrameworkElement element, string path)
        {
            await Task.Delay(250);
            element.UpdateLayout();
            var bitmap = new RenderTargetBitmap();
            await bitmap.RenderAsync(element);
            if (bitmap.PixelWidth == 0 || bitmap.PixelHeight == 0)
                throw new InvalidOperationException("Empty visual review render");
            var pixels = await bitmap.GetPixelsAsync();
            StorageFile file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(CreateFile(path)));
            using var stream = await file.OpenAsync(FileAccessMode.ReadWrite);
            BitmapEncoder encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
            using var reader = Windows.Storage.Streams.DataReader.FromBuffer(pixels);
            byte[] data = new byte[pixels.Length];
            reader.ReadBytes(data);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied,
                (uint)bitmap.PixelWidth, (uint)bitmap.PixelHeight, 96, 96, data);
            await encoder.FlushAsync();
        }

        private static string CreateFile(string path)
        {
            using (File.Create(path)) { }
            return path;
        }
    }
}
