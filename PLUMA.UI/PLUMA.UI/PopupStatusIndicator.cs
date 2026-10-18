using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Media;

namespace PLUMA.UI
{
    public enum PopupStatusKind { Progress, Success, Dot, None }

    /// <summary>One shared line box for popup status glyphs and captions.</summary>
    public sealed partial class PopupStatusIndicator : UserControl
    {
        public static readonly DependencyProperty LabelProperty = DependencyProperty.Register(
            nameof(Label), typeof(string), typeof(PopupStatusIndicator), new PropertyMetadata(string.Empty,
                (sender, args) => ((PopupStatusIndicator)sender)._label.Text = PopupText.Message(args.NewValue as string)));
        public static readonly DependencyProperty KindProperty = DependencyProperty.Register(
            nameof(Kind), typeof(PopupStatusKind), typeof(PopupStatusIndicator), new PropertyMetadata(PopupStatusKind.Progress,
                (sender, args) => ((PopupStatusIndicator)sender).ApplyKind()));

        private readonly TextBlock _label;
        private readonly ProgressRing _progress;
        private readonly FontIcon _success;
        private readonly InfoBadge _dot;

        public PopupStatusIndicator()
        {
            InitializeComponent();
            IsTabStop = false;
            VerticalAlignment = VerticalAlignment.Center;
            var row = new Grid { MinHeight = 20, ColumnSpacing = 7 };
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(16) });
            row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
            _progress = new ProgressRing { Width = 14, Height = 14, MinWidth = 0, MinHeight = 0,
                VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
            _success = new FontIcon { Glyph = "\uE73E", FontFamily = new FontFamily("Segoe Fluent Icons"), FontSize = 14,
                Width = 16, Height = 16, VerticalAlignment = VerticalAlignment.Center };
            _dot = new InfoBadge { Width = 6, Height = 6, MinWidth = 0, MinHeight = 0,
                VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
            _label = new TextBlock { FontSize = 12,
                VerticalAlignment = VerticalAlignment.Center };
            Grid.SetColumn(_label, 1);
            foreach (FrameworkElement element in new FrameworkElement[] { _progress, _success, _dot, _label }) row.Children.Add(element);
            _label.SetBinding(TextBlock.ForegroundProperty, new Binding { Source = this, Path = new PropertyPath("Foreground") });
            _success.SetBinding(FontIcon.ForegroundProperty, new Binding { Source = this, Path = new PropertyPath("Foreground") });
            _dot.SetBinding(InfoBadge.BackgroundProperty, new Binding { Source = this, Path = new PropertyPath("Foreground") });
            Content = row;
            ApplyKind();
        }

        public string Label { get => (string)GetValue(LabelProperty); set => SetValue(LabelProperty, value); }
        public PopupStatusKind Kind { get => (PopupStatusKind)GetValue(KindProperty); set => SetValue(KindProperty, value); }
        internal TextBlock LabelBlock => _label;
        internal FrameworkElement? Indicator => Kind switch
        { PopupStatusKind.Progress => _progress, PopupStatusKind.Success => _success, PopupStatusKind.Dot => _dot, _ => null };

        private void ApplyKind()
        {
            _progress.IsActive = Kind == PopupStatusKind.Progress;
            _progress.Visibility = Kind == PopupStatusKind.Progress ? Visibility.Visible : Visibility.Collapsed;
            _success.Visibility = Kind == PopupStatusKind.Success ? Visibility.Visible : Visibility.Collapsed;
            _dot.Visibility = Kind == PopupStatusKind.Dot ? Visibility.Visible : Visibility.Collapsed;
        }
    }
}
