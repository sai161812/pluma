using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Interop;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length != 1)
            return 2;

        var markerPath = args[0];
        var app = new Application { ShutdownMode = ShutdownMode.OnMainWindowClose };
        var button = new Button
        {
            Content = "Submit",
            Width = 150,
            Height = 36,
            Margin = new Thickness(24, 28, 0, 0),
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        AutomationProperties.SetAutomationId(button, "btn_submit");

        var status = new TextBlock
        {
            Text = "Ready",
            Margin = new Thickness(24, 18, 0, 0),
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        AutomationProperties.SetAutomationId(status, "txt_status");

        button.Click += (_, _) =>
        {
            button.IsEnabled = false;
            status.Text = "Submitted";
        };

        var panel = new StackPanel();
        panel.Children.Add(button);
        panel.Children.Add(status);

        var window = new Window
        {
            Title = "PLUMA P12 WPF fixture",
            Width = 420,
            Height = 240,
            Content = panel,
            ShowActivated = false,
            ShowInTaskbar = false,
            WindowStartupLocation = WindowStartupLocation.Manual,
            Left = 180,
            Top = 160,
        };

        window.SourceInitialized += (_, _) =>
        {
            var hwnd = new WindowInteropHelper(window).Handle;
            var marker = new
            {
                pid = Environment.ProcessId,
                hwnd = hwnd.ToInt64(),
            };
            var temporary = markerPath + ".partial";
            File.WriteAllText(temporary, JsonSerializer.Serialize(marker));
            File.Move(temporary, markerPath, overwrite: true);
        };

        app.Run(window);
        return 0;
    }
}
