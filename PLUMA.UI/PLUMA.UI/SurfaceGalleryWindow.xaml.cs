using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Foundation;
using Windows.Graphics.Imaging;
using Windows.Storage;

namespace PLUMA.UI
{
    /// <summary>Opt-in component catalogue. Never connects to the resident core or captures audio.</summary>
    public sealed partial class SurfaceGalleryWindow : Window
    {
        private ContentDialog? _dialog;
        private Func<ContentDialog>? _dialogFactory;
        private ScreenCaptureFlash? _flashPreview;
        private readonly CancellationTokenSource _lifetime = new();
        private Task? _exportTask;
        private bool _closed;
        private bool _exporting;

        public SurfaceGalleryWindow(string? exportDirectory = null)
        {
            InitializeComponent();
            AppWindow.Resize(new Windows.Graphics.SizeInt32(1200, 900));
            SurfacePicker.ItemsSource = SurfaceGalleryCatalog.Items;
            SurfacePicker.SelectedIndex = 15;
            bool exportStarted = false;
            GalleryRoot.Loaded += async (_, _) =>
            {
                if (exportStarted || string.IsNullOrWhiteSpace(exportDirectory)) return;
                exportStarted = true;
                _exportTask = ExportPreviewsAsync(exportDirectory, _lifetime.Token);
                try { await _exportTask; }
                catch (OperationCanceledException) { }
                catch (Exception error)
                {
                    try { File.WriteAllText(Path.Combine(exportDirectory, "export-error.txt"), error.ToString()); }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                    if (!_closed) PreviewActions.Children.Add(new TextBlock { Text = "Preview export failed. See export-error.txt." });
                }
            };
            Closed += async (_, _) =>
            {
                _closed = true;
                _lifetime.Cancel();
                _dialog?.Hide();
                PreviewHost.Children.Clear();
                if (_exportTask != null)
                {
                    try { await _exportTask; } catch (Exception) { /* Export failure is reported by its owner above. */ }
                }
                _lifetime.Dispose();
            };
        }

        private void OnSurfaceChanged(object sender, SelectionChangedEventArgs args)
        {
            if (SurfacePicker.SelectedItem is SurfaceGalleryItem surface) ShowSurface(surface.Id);
        }

        private void AddAction(string text, Action action)
        {
            var button = new Button { Content = text, IsEnabled = !_exporting };
            button.Click += (_, _) => action();
            PreviewActions.Children.Add(button);
        }

        private void ShowSurface(int id)
        {
            _dialog?.Hide();
            _dialogFactory = null;
            _flashPreview = null;
            PreviewActions.Children.Clear();
            PreviewHost.Children.Clear();
            FrameworkElement preview;
            switch (id)
            {
                case 1: preview = new DashboardPage(); break;
                case 2: preview = new SettingsPage(); break;
                case 3: preview = new HistoryPage(); break;
                case 4: preview = new TaskRunningPopup(); break;
                case 5: preview = new StepProgressPopup(); break;
                case 6: preview = new RouteBadgePopup(); break;
                case 7: preview = new ToolCallCard(); break;
                case 8: preview = new ToolResultCard(); break;
                case 9: preview = new RollbackPopup(); break;
                case 10:
                    preview = new TextBlock { Text = "Open the native conflict dialog. File actions remain preview requests." };
                    AddDialogAction("Open conflict dialog", () => new ConflictAlertPopup());
                    break;
                case 11:
                    var voice = new VoiceOverlay { VoiceState = VoiceOverlayState.ListeningSilence,
                        IsAnimating = true, FinalTranscript = "Preview: no microphone capture" };
                    voice.SetPreviewStatus("Preview");
                    preview = voice;
                    break;
                case 12:
                    preview = new LiveTranscriptionOverlay { FinalTranscript = "Move the PDF", PartialTranscript = "to my college folder", MaxWidth = 640 };
                    break;
                case 13: preview = new VoiceCommittedBanner(); break;
                case 14:
                    var silence = new VoiceSilenceTimeoutIndicator { Width = 420, Progress = 0.65 };
                    // The production voice host reveals this bar in its SilenceTimeout state.
                    ((ProgressBar)silence.FindName("TimeoutBar")).Opacity = 1;
                    preview = silence;
                    AddAction("25%", () => silence.Progress = 0.25);
                    AddAction("75%", () => silence.Progress = 0.75);
                    break;
                case 15:
                    var flashArea = CreateDemoArea();
                    var flash = new ScreenCaptureFlash();
                    _flashPreview = flash;
                    flashArea.Children.Add(new TextBlock { Text = "Preview target window", Margin = new Thickness(24) });
                    flashArea.Children.Add(flash);
                    AddAction("Play capture flash", flash.Play);
                    preview = flashArea;
                    break;
                case 16:
                    var matchArea = CreateDemoArea();
                    var marker = new OcrMatchIndicator();
                    matchArea.Children.Add(new Button { Content = "Submit", Width = 100, Height = 32,
                        HorizontalAlignment = HorizontalAlignment.Left, VerticalAlignment = VerticalAlignment.Top,
                        Margin = new Thickness(30, 30, 0, 0), IsHitTestVisible = false });
                    matchArea.Children.Add(marker);
                    void ShowMatch() => marker.ShowMatch("Submit", 0.95, new Rect(30, 30, 100, 32),
                        new Point(1200, 300), DateTimeOffset.UtcNow.AddSeconds(3));
                    matchArea.Loaded += (_, _) => ShowMatch();
                    AddAction("Show OCR match (3 seconds)", ShowMatch);
                    preview = matchArea;
                    break;
                case 17:
                    var verification = new PostClickVerifyIndicator();
                    verification.ShowResult(false, "ocr_rescan", "Expected transition not observed");
                    AddAction("Verified", () => verification.ShowResult(true, "ocr_rescan", "Expected label appeared"));
                    AddAction("Unverified", () => verification.ShowResult(false, "ocr_rescan", "Expected transition not observed"));
                    preview = verification;
                    break;
                case 18:
                    preview = new TextBlock { Text = "Open the native approval dialog to inspect its appearance." };
                    AddDialogAction("Open approval dialog", () => new RiskApprovalDialog
                    { ToolName = "restart_request", RiskClass = "HIGH", SanitizedArguments = "Preview operation only" });
                    break;
                case 19:
                    var policy = new PolicyBlockNotice { ToolName = "invoke_control", MatchedRule = "Target changed", IsNoticeOpen = true };
                    AddAction("Show notice", policy.ShowNotice);
                    preview = policy;
                    break;
                case 20:
                    var cancellation = new CancellationAnimation { IsActive = true };
                    AddAction("Replay", cancellation.Show);
                    preview = cancellation;
                    break;
                case 21:
                    var termination = new WorkerTerminationFlash { IsOpen = true };
                    AddAction("Replay", termination.Show);
                    preview = termination;
                    break;
                case 22:
                    var feed = new LiveMessageFeed();
                    feed.AppendMessage("Opened Notepad", DateTimeOffset.Now);
                    feed.AppendMessage("Could not verify Submit action", DateTimeOffset.Now);
                    AddAction("Add preview message", () => feed.AppendMessage("Stopped task", DateTimeOffset.Now));
                    AddAction("Empty state", feed.ClearMessages);
                    preview = feed;
                    break;
                case 23:
                    var health = new CoreHealthIndicator { IsConnected = true, PingLatencyMs = 12 };
                    AddAction("Connected", () => { health.IsConnected = true; health.PingLatencyMs = 12; });
                    AddAction("Disconnected", () => health.IsConnected = false);
                    preview = health;
                    break;
                case 24:
                    var toast = new ToastNotification();
                    void ShowToast(InfoBarSeverity severity) => toast.Show("Preview notification", severity);
                    toast.Loaded += (_, _) => ShowToast(InfoBarSeverity.Informational);
                    AddAction("Info", () => ShowToast(InfoBarSeverity.Informational));
                    AddAction("Warning", () => ShowToast(InfoBarSeverity.Warning));
                    AddAction("Error", () => ShowToast(InfoBarSeverity.Error));
                    preview = toast;
                    break;
                case 25:
                    preview = new TextBlock { Text = "Open the native critical-error dialog. Restart remains a preview-only request." };
                    AddDialogAction("Open critical-error dialog", () =>
                    {
                        var error = new CriticalErrorDialog { ErrorMessage = "The resident core disconnected.",
                            SanitizedDetails = "Preview: IPC connection closed.", CanRestart = true };
                        error.RestartRequested += (_, _) => error.ErrorMessage = "Preview request received. No core was restarted.";
                        return error;
                    });
                    break;
                case 26:
                    var wizard = new SetupWizard();
                    AddAction("All checks available", () =>
                    {
                        foreach (SetupCheckId check in Enum.GetValues<SetupCheckId>())
                            wizard.SetCheckResult(check, SetupCheckState.Passed, "Preview result");
                    });
                    AddAction("Microphone unavailable", () => wizard.SetCheckResult(SetupCheckId.Microphone, SetupCheckState.Failed, "Preview: access denied"));
                    preview = wizard;
                    break;
                default: throw new ArgumentOutOfRangeException(nameof(id));
            }
            preview.HorizontalAlignment = HorizontalAlignment.Left;
            if (id is 1 or 2 or 3 or 22 or 24 or 26) preview.HorizontalAlignment = HorizontalAlignment.Stretch;
            PreviewHost.Children.Add(preview);
        }

        private void AddDialogAction(string label, Func<ContentDialog> factory)
        {
            _dialogFactory = factory;
            var button = new Button { Content = label, IsEnabled = !_exporting };
            button.Click += async (_, _) => await ShowDialogAsync(factory, button);
            PreviewActions.Children.Add(button);
        }

        private async Task ShowDialogAsync(Func<ContentDialog> factory, Button button)
        {
            if (_dialog != null) return;
            button.IsEnabled = false;
            try
            {
                _dialog = factory();
                _dialog.XamlRoot = GalleryRoot.XamlRoot;
                _dialog.RequestedTheme = GalleryRoot.RequestedTheme;
                await _dialog.ShowAsync();
            }
            finally { _dialog = null; button.IsEnabled = true; }
        }

        private static Grid CreateDemoArea() => (Grid)Microsoft.UI.Xaml.Markup.XamlReader.Load(
            "<Grid xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation' Width='640' Height='320' Background='{ThemeResource CardBackgroundFillColorDefaultBrush}'/>");

        private async Task ExportPreviewsAsync(string outputDirectory, CancellationToken token)
        {
            Directory.CreateDirectory(outputDirectory);
            _exporting = true;
            foreach (var child in PreviewActions.Children)
                if (child is Control control) control.IsEnabled = false;
            SurfacePicker.IsEnabled = false;
            PreviewHost.IsHitTestVisible = false;
            PreviewActions.IsHitTestVisible = false;
            try
            {
                using var report = new StreamWriter(Path.Combine(outputDirectory, "gallery-report.txt")) { AutoFlush = true };
                report.WriteLine("Actual WinUI component previews. Fixture data only; no backend or microphone.");
                report.WriteLine($"Started {DateTimeOffset.Now:O}");
                const ElementTheme theme = ElementTheme.Dark;
                GalleryRoot.RequestedTheme = theme;
                foreach (SurfaceGalleryItem item in SurfaceGalleryCatalog.Items)
                {
                    token.ThrowIfCancellationRequested();
                    if (SurfacePicker.SelectedIndex == item.Id - 1) ShowSurface(item.Id);
                    else SurfacePicker.SelectedIndex = item.Id - 1;
                    PreviewScroll.ChangeView(0, 0, null, true);
                    await Task.Delay(250, token);
                    FrameworkElement renderTarget = GalleryRoot;
                    Windows.Foundation.IAsyncOperation<ContentDialogResult>? showing = null;
                    if (_dialogFactory != null)
                    {
                        _dialog = _dialogFactory();
                        _dialog.XamlRoot = GalleryRoot.XamlRoot;
                        _dialog.RequestedTheme = theme;
                        showing = _dialog.ShowAsync();
                        await Task.Delay(200, token);
                        renderTarget = _dialog;
                    }
                    if (_flashPreview != null)
                    {
                        // A still of the existing animation's documented peak, for inspection.
                        _flashPreview.Visibility = Visibility.Visible;
                        ((FrameworkElement)_flashPreview.FindName("FlashLayer")).Opacity = 0.15;
                    }
                    string filename = $"surface-{item.Id:00}-{theme.ToString().ToLowerInvariant()}.png";
                    await ExportElementAsync(renderTarget, Path.Combine(outputDirectory, filename), token);
                    if (showing != null)
                    {
                        _dialog?.Hide();
                        await showing;
                        _dialog = null;
                    }
                    await report.WriteLineAsync($"PASS {filename}: {item.Name}");
                }
                await AuditFormattingAsync(outputDirectory, token);
                await report.WriteLineAsync("26 dark component renders exported. Formatting audit passed; see formatting-checks.txt. Bottom-right placement is specified; desktop stack hosting and backend wiring remain pending.");
                WritePreviewIndex(outputDirectory);
            }
            finally
            {
                _exporting = false;
                if (!_closed)
                {
                    SurfacePicker.IsEnabled = true;
                    PreviewHost.IsHitTestVisible = true;
                    PreviewActions.IsHitTestVisible = true;
                    GalleryRoot.RequestedTheme = ElementTheme.Dark;
                    if (SurfacePicker.SelectedIndex == 15) ShowSurface(16);
                    else SurfacePicker.SelectedIndex = 15;
                }
            }
        }

        private static async Task ExportElementAsync(FrameworkElement element, string path, CancellationToken token)
        {
            token.ThrowIfCancellationRequested();
            element.UpdateLayout();
            var bitmap = new RenderTargetBitmap();
            await bitmap.RenderAsync(element);
            if (bitmap.PixelWidth == 0 || bitmap.PixelHeight == 0) throw new InvalidOperationException("Empty preview render");
            var buffer = await bitmap.GetPixelsAsync();
            token.ThrowIfCancellationRequested();
            using (File.Create(path)) { }
            StorageFile file = await StorageFile.GetFileFromPathAsync(Path.GetFullPath(path));
            using var stream = await file.OpenAsync(FileAccessMode.ReadWrite);
            var encoder = await BitmapEncoder.CreateAsync(BitmapEncoder.PngEncoderId, stream);
            using var reader = Windows.Storage.Streams.DataReader.FromBuffer(buffer);
            var pixels = new byte[buffer.Length];
            reader.ReadBytes(pixels);
            encoder.SetPixelData(BitmapPixelFormat.Bgra8, BitmapAlphaMode.Premultiplied,
                (uint)bitmap.PixelWidth, (uint)bitmap.PixelHeight, 96, 96, pixels);
            await encoder.FlushAsync();
        }

        private static void WritePreviewIndex(string outputDirectory)
        {
            var options = new System.Text.StringBuilder();
            foreach (SurfaceGalleryItem item in SurfaceGalleryCatalog.Items)
                options.Append($"<option value='{item.Id:00}'{(item.Id == 16 ? " selected" : "")}>{System.Net.WebUtility.HtmlEncode(item.Label)}</option>");
            string html = """
                <!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
                <title>PLUMA UI surface previews</title>
                <style>body{font:16px system-ui;margin:24px;color-scheme:dark;background:#202020;color:#fff}header{display:flex;gap:16px;align-items:center;flex-wrap:wrap}select{font:inherit;padding:8px;max-width:100%}img{display:block;max-width:100%;height:auto;margin-top:20px;border:1px solid #888}p{max-width:80ch}</style>
                <h1>PLUMA UI surface previews</h1><p>Actual WinUI renders with preview data. Floating surfaces are specified to share a bottom-right stack. This catalogue shows individual components; desktop stack hosting and backend wiring are pending. Animation previews are still frames; the native gallery includes replay buttons.</p>
                <header><label>Surface <select id="surface">OPTIONS</select></label><a id="full" href="surface-16-dark.png" target="_blank">Open full-size image</a></header>
                <img id="preview" src="surface-16-dark.png" alt="OCR Match Indicator native WinUI preview">
                <script>const surface=document.getElementById('surface'),preview=document.getElementById('preview'),full=document.getElementById('full');function update(){const path='surface-'+surface.value+'-dark.png';preview.src=path;full.href=path;preview.alt=surface.selectedOptions[0].text+' dark preview'}surface.addEventListener('change',update);</script></html>
                """;
            File.WriteAllText(Path.Combine(outputDirectory, "index.html"), html.Replace("OPTIONS", options.ToString()));
        }
    }
}
