using System;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;

namespace PLUMA.UI
{
    /// <summary>Readable, bounded notification text with native wrapping and keyboard scrolling.</summary>
    public sealed partial class PopupMessageText : UserControl
    {
        public static readonly DependencyProperty TextProperty = DependencyProperty.Register(
            nameof(Text), typeof(string), typeof(PopupMessageText), new PropertyMetadata(string.Empty, OnTextChanged));
        public static readonly DependencyProperty FollowTailProperty = DependencyProperty.Register(
            nameof(FollowTail), typeof(bool), typeof(PopupMessageText), new PropertyMetadata(false));
        public static readonly DependencyProperty IsTextSelectionEnabledProperty = DependencyProperty.Register(
            nameof(IsTextSelectionEnabled), typeof(bool), typeof(PopupMessageText), new PropertyMetadata(false,
                (sender, args) => ((PopupMessageText)sender)._message.IsTextSelectionEnabled = (bool)args.NewValue));

        private readonly TextBlock _message;
        private readonly ScrollViewer _scroll;
        private bool _followPending;

        public PopupMessageText()
        {
            InitializeComponent();
            MinWidth = 0;
            MaxHeight = 96;
            HorizontalContentAlignment = HorizontalAlignment.Stretch;
            VerticalContentAlignment = VerticalAlignment.Stretch;
            IsTabStop = false;
            FontSize = 14;
            _message = new TextBlock { TextWrapping = TextWrapping.Wrap, TextTrimming = TextTrimming.None };
            foreach (string property in new[] { "FontSize", "FontFamily", "FontWeight", "Foreground" })
            {
                DependencyProperty target = property switch
                {
                    "FontSize" => TextBlock.FontSizeProperty, "FontFamily" => TextBlock.FontFamilyProperty,
                    "FontWeight" => TextBlock.FontWeightProperty, _ => TextBlock.ForegroundProperty
                };
                _message.SetBinding(target, new Binding { Source = this, Path = new PropertyPath(property) });
            }
            _scroll = new ScrollViewer
            {
                Content = _message, HorizontalScrollMode = ScrollMode.Disabled,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                VerticalScrollMode = ScrollMode.Auto, VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalContentAlignment = HorizontalAlignment.Stretch,
                ZoomMode = ZoomMode.Disabled, IsTabStop = true
            };
            Content = _scroll;
            Loaded += (_, _) => _followPending = FollowTail;
            LayoutUpdated += (_, _) =>
            {
                if (!_followPending || !IsLoaded || _scroll.ViewportWidth <= 0) return;
                _followPending = false;
                _scroll.ChangeView(null, _scroll.ScrollableHeight, null, true);
            };
        }

        public string Text { get => (string)GetValue(TextProperty); set => SetValue(TextProperty, value); }
        public bool FollowTail { get => (bool)GetValue(FollowTailProperty); set => SetValue(FollowTailProperty, value); }
        public bool IsTextSelectionEnabled { get => (bool)GetValue(IsTextSelectionEnabledProperty); set => SetValue(IsTextSelectionEnabledProperty, value); }
        public string DisplayText => _message.Text;
        internal ScrollViewer MessageScroll => _scroll;
        internal TextBlock MessageBlock => _message;

        private static void OnTextChanged(DependencyObject sender, DependencyPropertyChangedEventArgs args)
        {
            var control = (PopupMessageText)sender;
            bool atEnd = control._scroll.ScrollableHeight - control._scroll.VerticalOffset < 2;
            control._followPending = control.FollowTail && (control._followPending || atEnd);
            control._message.Text = PopupText.Message(args.NewValue as string);
            AutomationProperties.SetName(control._scroll, control._message.Text);
            // Native layout coalesces rapid partial transcripts; scrolling waits for the new extent.
        }
    }
}
