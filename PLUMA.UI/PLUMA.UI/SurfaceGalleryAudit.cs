using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Foundation;

namespace PLUMA.UI
{
    // Runs only during an explicitly requested fixture export, on the gallery's UI thread.
    public sealed partial class SurfaceGalleryWindow
    {
        private async Task AuditFormattingAsync(string outputDirectory, CancellationToken token)
        {
            using var report = new StreamWriter(Path.Combine(outputDirectory, "formatting-checks.txt")) { AutoFlush = true };
            int checks = 0;
            void Check(bool condition, string description)
            {
                report.WriteLine($"{(condition ? "PASS" : "FAIL")} {description}");
                if (!condition) throw new InvalidOperationException(description);
                checks++;
            }
            string longMessage = string.Join(" ", Enumerable.Repeat(
                "Please open quarterly_report.pdf \u2014 keep the existing destination and wait for verification. " +
                new string('W', 180) + " \u65e5\u672c\u8a9e \ud83d\udcc4", 8));
            report.WriteLine($"WinUI fixture audit; scale {GalleryRoot.XamlRoot.RasterizationScale:0.##}; {DateTimeOffset.Now:O}");
            const ElementTheme theme = ElementTheme.Dark;
            GalleryRoot.RequestedTheme = theme;
            foreach (SurfaceGalleryItem item in SurfaceGalleryCatalog.Items)
            {
                token.ThrowIfCancellationRequested();
                if (SurfacePicker.SelectedIndex == item.Id - 1) ShowSurface(item.Id);
                else SurfacePicker.SelectedIndex = item.Id - 1;
                await Task.Delay(80, token);
                FrameworkElement root = (FrameworkElement)PreviewHost.Children[0];
                Windows.Foundation.IAsyncOperation<ContentDialogResult>? showing = null;
                try
                {
                    if (_dialogFactory != null)
                    {
                        _dialog = _dialogFactory();
                        _dialog.XamlRoot = GalleryRoot.XamlRoot;
                        _dialog.RequestedTheme = theme;
                        showing = _dialog.ShowAsync();
                        await Task.Delay(200, token);
                        root = _dialog;
                    }
                    root.UpdateLayout();
                    string prefix = $"{theme} surface {item.Id:00}";
                    var visibleText = Descendants(root).OfType<TextBlock>().Where(IsVisible).ToArray();
                    Check(visibleText.All(text => !text.Text.Contains('_') && !text.Text.Contains('\u2014')),
                        $"{prefix}: visible messages contain no machine separators");
                    foreach (var status in Descendants(root).OfType<PopupStatusIndicator>().Where(IsVisible))
                    {
                        status.LabelBlock.FontSize = 18; // 150% text-size stress, without changing OS settings.
                        status.UpdateLayout();
                        if (status.Indicator is not FrameworkElement indicator) continue;
                        double glyphCenter = indicator.TransformToVisual(status).TransformPoint(new Point(0, indicator.ActualHeight / 2)).Y;
                        double textCenter = status.LabelBlock.TransformToVisual(status).TransformPoint(new Point(0, status.LabelBlock.ActualHeight / 2)).Y;
                        Check(indicator.ActualHeight > 0 && Math.Abs(glyphCenter - textCenter) <= 1,
                            $"{prefix}: {status.Label} indicator and caption centers align ({glyphCenter:0.##}/{textCenter:0.##})");
                    }
                    var messages = Descendants(root).OfType<PopupMessageText>().Where(IsVisible).ToArray();
                    foreach (PopupMessageText message in messages)
                    {
                        message.FontSize *= 1.5;
                        message.Text = longMessage;
                    }
                    if (root is CriticalErrorDialog error)
                    {
                        error.ErrorMessage = longMessage;
                        error.SanitizedDetails = longMessage;
                        ((Expander)error.FindName("DetailsExpander")).IsExpanded = true;
                    }
                    root.UpdateLayout();
                    await Task.Delay(80, token);
                    messages = Descendants(root).OfType<PopupMessageText>().Where(IsVisible).ToArray();
                    foreach (PopupMessageText message in messages)
                    {
                        string label = string.IsNullOrEmpty(message.Name) ? "message" : message.Name;
                        var scroll = message.MessageScroll;
                        Check(message.Foreground is SolidColorBrush foreground &&
                              message.ActualTheme == ElementTheme.Dark && foreground.Color.R > 128,
                            $"{prefix} {label}: foreground follows the dark theme");
                        string expectedText = message.PreserveLiteralText ? longMessage : PopupText.Message(longMessage);
                        Check(message.DisplayText == expectedText && message.FontSize >= 12,
                            $"{prefix} {label}: full readable content retained at {message.FontSize}px");
                        Check(message.ActualWidth > 0 && message.ActualWidth <= Math.Min(message.MaxWidth, GalleryRoot.ActualWidth) + 1 &&
                              message.ActualHeight <= message.MaxHeight + 1 &&
                              scroll.ScrollableWidth <= 1 && message.MessageBlock.ActualWidth <= scroll.ViewportWidth + 1 &&
                              message.MessageBlock.TextWrapping == TextWrapping.Wrap && message.MessageBlock.MaxLines == 0 &&
                              message.MessageBlock.TextTrimming == TextTrimming.None,
                            $"{prefix} {label}: long words wrap inside bounded {message.ActualWidth:0}x{message.ActualHeight:0} space");
                        Check(scroll.ScrollableHeight > 0 && AutomationProperties.GetName(scroll) == message.DisplayText,
                            $"{prefix} {label}: overflow is scrollable and accessible");
                        scroll.ChangeView(null, scroll.ScrollableHeight, null, true);
                        // ChangeView is asynchronous even with animation disabled. Read back the
                        // actual native offset within a bound instead of assuming one frame is enough.
                        var scrolling = Stopwatch.StartNew();
                        while (Math.Abs(scroll.VerticalOffset - scroll.ScrollableHeight) > 1 &&
                               scrolling.Elapsed < TimeSpan.FromSeconds(2))
                            await Task.Delay(20, token);
                        report.WriteLine($"SCROLL {prefix} {label}: offset {scroll.VerticalOffset:0.###}; end {scroll.ScrollableHeight:0.###}; waited {scrolling.Elapsed.TotalMilliseconds:0}ms");
                        Check(Math.Abs(scroll.VerticalOffset - scroll.ScrollableHeight) <= 1,
                            $"{prefix} {label}: last line can be reached");
                    }
                    if (messages.Length > 0)
                    {
                        PreviewScroll.ChangeView(0, 0, null, true);
                        await ExportElementAsync(showing == null ? GalleryRoot : root,
                            Path.Combine(outputDirectory, $"stress-{item.Id:00}-{theme.ToString().ToLowerInvariant()}.png"), token);
                    }
                }
                finally
                {
                    if (showing != null) { _dialog?.Hide(); await showing; _dialog = null; }
                }
            }

            if (SurfacePicker.SelectedIndex == 10) ShowSurface(11);
            else SurfacePicker.SelectedIndex = 10;
            var voice = (VoiceOverlay)PreviewHost.Children[0];
            voice.IsAnimating = false;
            voice.FinalTranscript = longMessage;
            await Task.Delay(60, token);
            var transcript = (PopupMessageText)((LiveTranscriptionOverlay)voice.FindName("LiveTranscriptHost")).FindName("LiveTranscript");
            var transcriptScroll = transcript.MessageScroll;
            transcriptScroll.ChangeView(null, transcriptScroll.ScrollableHeight, null, true);
            await Task.Delay(40, token);
            voice.PartialTranscript = "and then wait for the next result";
            await Task.Delay(60, token);
            Check(voice.FinalTranscript == longMessage && transcript.DisplayText.EndsWith(voice.PartialTranscript),
                $"{theme} voice: raw transcript retained while formatted final and partial text are shown");
            Check(Math.Abs(transcriptScroll.VerticalOffset - transcriptScroll.ScrollableHeight) <= 1,
                $"{theme} voice: new speech follows the last line");
            transcriptScroll.ChangeView(null, 0, null, true);
            await Task.Delay(40, token);
            voice.PartialTranscript += " without changing the earlier words";
            await Task.Delay(60, token);
            Check(transcriptScroll.VerticalOffset <= 1, $"{theme} voice: reading earlier text is not interrupted");
            voice.FinalTranscript = "Open the report";
            voice.PartialTranscript = string.Empty;
            await Task.Delay(60, token);
            Check(transcriptScroll.ScrollableHeight <= 1 && transcript.DisplayText == "Open the report" && voice.ActualHeight == 276,
                $"{theme} voice: short text restores compact overlay without stale scrolling");
            voice.VoiceState = VoiceOverlayState.Committed;
            await Task.Delay(60, token);
            var committed = (VoiceCommittedBanner)voice.FindName("CommittedPanel");
            Check(committed.ActualHeight <= 70 && Descendants(committed).OfType<InfoBar>().Any(bar => bar.IsOpen),
                $"{theme} voice: native committed banner fits the existing overlay");
            await ExportElementAsync(GalleryRoot, Path.Combine(outputDirectory, $"voice-committed-{theme.ToString().ToLowerInvariant()}.png"), token);
            report.WriteLine($"{checks} formatting checks passed. No backend or microphone was started.");
        }

        private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
        {
            yield return root;
            for (int index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
                foreach (DependencyObject item in Descendants(VisualTreeHelper.GetChild(root, index))) yield return item;
        }

        private static bool IsVisible(FrameworkElement element)
        {
            if (element.ActualWidth <= 0 || element.ActualHeight <= 0) return false;
            for (DependencyObject? current = element; current != null; current = VisualTreeHelper.GetParent(current))
                if (current is UIElement ui && ui.Visibility != Visibility.Visible) return false;
            return true;
        }
    }
}
